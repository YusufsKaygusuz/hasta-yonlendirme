"""The kiosk's behaviour as a small state machine, independent of any GUI toolkit.

The controller receives events (recognition verdicts, key presses, clock ticks) and
exposes a single immutable :class:`ViewState` for the UI to draw. All the decisions
about what the patient sees, and for how long, live here and are unit tested.
"""

from __future__ import annotations

import enum
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, replace

from hasta_yonlendirme.announcer import Announcer
from hasta_yonlendirme.i18n import Messages
from hasta_yonlendirme.identity import InvalidNationalIdError, normalize_national_id
from hasta_yonlendirme.models import RouteResult, RouteStatus
from hasta_yonlendirme.recognition.pipeline import Observation, Verdict
from hasta_yonlendirme.routing import RoutingService

log = logging.getLogger(__name__)

MAX_ID_DIGITS = 11


class Screen(str, enum.Enum):
    IDLE = "idle"
    SCANNING = "scanning"
    ROUTE = "route"
    NO_APPOINTMENT = "no_appointment"
    UNRECOGNISED = "unrecognised"
    MANUAL_ENTRY = "manual_entry"
    CAMERA_ERROR = "camera_error"


RESULT_SCREENS = frozenset({Screen.ROUTE, Screen.NO_APPOINTMENT, Screen.UNRECOGNISED})


@dataclass(frozen=True, slots=True)
class ViewState:
    screen: Screen = Screen.IDLE
    result: RouteResult | None = None
    digits: str = ""
    error_key: str | None = None
    """i18n key of an inline error message, e.g. an invalid ID number."""


class KioskController:
    def __init__(
        self,
        routing: RoutingService,
        announcer: Announcer,
        messages: Messages,
        *,
        result_seconds: float = 12.0,
        manual_timeout_seconds: float = 45.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.routing = routing
        self.announcer = announcer
        self.messages = messages
        self.result_seconds = result_seconds
        self.manual_timeout_seconds = manual_timeout_seconds
        self.clock = clock
        self._state = ViewState()
        self._deadline: float | None = None
        self._camera_ok = True
        # Do not greet the same person again while they are still standing at the kiosk.
        self._last_patient: int | None = None
        self._last_patient_until = 0.0
        self.version = 0
        """Incremented on every state change, so a UI can redraw only when needed."""

    @property
    def state(self) -> ViewState:
        return self._state

    def _set(self, state: ViewState, timeout: float | None = None) -> None:
        if state != self._state:
            self._state = state
            self.version += 1
        self._deadline = None if timeout is None else self.clock() + timeout

    def _home(self) -> ViewState:
        return ViewState(Screen.IDLE if self._camera_ok else Screen.CAMERA_ERROR)

    # --- recognition events --------------------------------------------------------------
    def on_observation(self, observation: Observation) -> None:
        self._camera_ok = True  # any verdict means frames are arriving again
        screen = self._state.screen
        if screen is Screen.CAMERA_ERROR:
            self._set(ViewState(Screen.IDLE))
            screen = Screen.IDLE
        if screen not in (Screen.IDLE, Screen.SCANNING):
            return  # a result or the keypad is on screen; the camera waits

        verdict = observation.verdict
        if verdict is Verdict.NOBODY:
            self._set(ViewState(Screen.IDLE))
        elif verdict is Verdict.PENDING:
            self._set(ViewState(Screen.SCANNING))
        elif verdict is Verdict.UNRECOGNISED:
            self._unrecognised()
        elif verdict is Verdict.CONFIRMED and observation.patient_id is not None:
            self._recognised(observation.patient_id)

    def _recognised(self, patient_id: int) -> None:
        now = self.clock()
        if patient_id == self._last_patient and now < self._last_patient_until:
            self._set(ViewState(Screen.IDLE))
            return
        result = self.routing.route_patient(patient_id)
        if result.status is RouteStatus.UNKNOWN_PATIENT:
            # The face matched but the record is gone (e.g. erased); treat as not recognised.
            self._unrecognised()
            return
        self._last_patient = patient_id
        self._last_patient_until = now + 2 * self.result_seconds
        self._show(result)

    def _unrecognised(self) -> None:
        self._set(ViewState(Screen.UNRECOGNISED), self.result_seconds)
        self.announcer.say(self.messages("unknown.speech"))

    def on_camera_error(self) -> None:
        self._camera_ok = False
        if self._state.screen in (Screen.IDLE, Screen.SCANNING):
            self._set(ViewState(Screen.CAMERA_ERROR))

    # --- keypad events ---------------------------------------------------------------
    def open_manual_entry(self) -> None:
        self._set(ViewState(Screen.MANUAL_ENTRY), self.manual_timeout_seconds)

    def press_digit(self, digit: str) -> None:
        if self._state.screen is not Screen.MANUAL_ENTRY or not (len(digit) == 1 and digit.isdigit()):
            return
        digits = (self._state.digits + digit)[:MAX_ID_DIGITS]
        self._set(replace(self._state, digits=digits, error_key=None), self.manual_timeout_seconds)

    def delete_digit(self) -> None:
        if self._state.screen is Screen.MANUAL_ENTRY:
            self._set(replace(self._state, digits=self._state.digits[:-1], error_key=None), self.manual_timeout_seconds)

    def cancel_manual_entry(self) -> None:
        if self._state.screen is Screen.MANUAL_ENTRY:
            self._set(self._home())

    def submit_manual_entry(self, raw: str | None = None) -> None:
        """Look up the typed ID. ``raw`` lets a hardware keyboard or barcode reader submit directly."""
        if raw is None and self._state.screen is not Screen.MANUAL_ENTRY:
            return
        value = normalize_national_id(raw if raw is not None else self._state.digits)
        try:
            result = self.routing.route_national_id(value)
        except InvalidNationalIdError:
            self._set(ViewState(Screen.MANUAL_ENTRY, error_key="manual.invalid"), self.manual_timeout_seconds)
            return
        if result.status is not RouteStatus.FOUND:
            # Unknown ID and "no appointment" look identical, without a name: someone typing
            # another person's number must not learn whether that person is registered.
            result = RouteResult(RouteStatus.NO_APPOINTMENT)
        self._show(result)

    # --- time ----------------------------------------------------------------------------
    def tick(self) -> None:
        if self._deadline is not None and self.clock() >= self._deadline:
            self._set(self._home())

    # --- output ----------------------------------------------------------------------------
    def _show(self, result: RouteResult) -> None:
        if result.status is RouteStatus.FOUND and result.appointment and result.patient:
            appt = result.appointment
            log.info("Routed patient %s to clinic %s", result.patient.id, appt.clinic.id)
            self._set(ViewState(Screen.ROUTE, result), self.result_seconds)
            self.announcer.say(
                self.messages.speakable(
                    self.messages(
                        "found.speech",
                        name=result.patient.first_name,
                        clinic=appt.clinic.name,
                        block=appt.clinic.block,
                        floor=self.messages.spoken_floor(appt.clinic.floor),
                        doctor=appt.doctor.display_name,
                    )
                )
            )
        else:
            self._set(ViewState(Screen.NO_APPOINTMENT, result), self.result_seconds)
            self.announcer.say(self.messages("no_appointment.speech"))
