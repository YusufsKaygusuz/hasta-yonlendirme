"""Text-only kiosk for development machines and headless testing.

Prints every screen change; type an ID number and press Enter to use the fallback path.
"""

from __future__ import annotations

import queue
import sys
import threading
import time

from hasta_yonlendirme.i18n import Messages
from hasta_yonlendirme.kiosk.controller import RESULT_SCREENS, KioskController, Screen, ViewState
from hasta_yonlendirme.kiosk.worker import CameraFailure, Event, RecognitionWorker


def describe(state: ViewState, t: Messages) -> str:
    """One-line rendering of a screen, also used in tests."""
    if state.screen is Screen.ROUTE and state.result and state.result.appointment and state.result.patient:
        appt = state.result.appointment
        return " | ".join(
            [
                t("found.greeting", name=state.result.patient.public_name),
                t("location.block", block=appt.clinic.block),
                t("location.floor", floor=appt.clinic.floor),
                appt.clinic.name,
                appt.doctor.display_name,
                t("found.time", time=t.time(appt.starts_at)),
            ]
        )
    text = {
        Screen.IDLE: t("idle.body"),
        Screen.SCANNING: t("scanning"),
        Screen.NO_APPOINTMENT: f"{t('no_appointment.title')}. {t('no_appointment.body')}",
        Screen.UNRECOGNISED: f"{t('unknown.title')}. {t('unknown.body')}",
        Screen.MANUAL_ENTRY: t(state.error_key) if state.error_key else t("manual.title"),
        Screen.CAMERA_ERROR: t("error.camera"),
    }
    return text.get(state.screen, state.screen.value)


class ConsoleKiosk:
    def __init__(
        self,
        controller: KioskController,
        messages: Messages,
        events: queue.Queue[Event],
        worker: RecognitionWorker | None,
    ) -> None:
        self.controller = controller
        self.t = messages
        self.events = events
        self.worker = worker
        self._typed: queue.Queue[str] = queue.Queue()

    def _read_stdin(self) -> None:
        for line in sys.stdin:
            self._typed.put(line.strip())

    def run(self) -> None:
        if self.worker is not None:
            self.worker.start()
        threading.Thread(target=self._read_stdin, name="stdin", daemon=True).start()
        print("Ctrl+C to quit. Type a national ID number and press Enter to test the fallback.", flush=True)
        shown = -1
        try:
            while True:
                self._drain()
                self.controller.tick()
                if self.worker is not None:
                    state = self.controller.state.screen
                    self.worker.pause(state in RESULT_SCREENS or state is Screen.MANUAL_ENTRY)
                if self.controller.version != shown:
                    shown = self.controller.version
                    print(
                        f"[{self.controller.state.screen.value:>14}] {describe(self.controller.state, self.t)}",
                        flush=True,
                    )
                time.sleep(0.05)
        except KeyboardInterrupt:
            pass
        finally:
            if self.worker is not None:
                self.worker.stop()

    def _drain(self) -> None:
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            if isinstance(event, CameraFailure):
                self.controller.on_camera_error()
            else:
                self.controller.on_observation(event)
        while True:
            try:
                typed = self._typed.get_nowait()
            except queue.Empty:
                break
            if typed:
                self.controller.submit_manual_entry(typed)
