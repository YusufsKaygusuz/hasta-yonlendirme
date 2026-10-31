"""Deciding where a recognised patient should go."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from hasta_yonlendirme.identity import NationalIdHasher
from hasta_yonlendirme.models import Appointment, AppointmentStatus, RouteResult, RouteStatus
from hasta_yonlendirme.storage.base import Repository

Clock = Callable[[], datetime]


class RoutingService:
    """Finds the appointment a patient most likely came for.

    The kiosk shows one appointment, never a list: the next scheduled one that is not
    too far in the future (``early``) and has not started too long ago (``late``).
    Among those, an appointment that is still ahead wins over one that has already
    started, and the nearest wins among the rest.
    """

    def __init__(
        self,
        repository: Repository,
        hasher: NationalIdHasher | None = None,
        *,
        early: timedelta = timedelta(hours=4),
        late: timedelta = timedelta(hours=1),
        clock: Clock = datetime.now,
    ) -> None:
        self.repository = repository
        self.hasher = hasher
        self.early = early
        self.late = late
        self.clock = clock

    def route_patient(self, patient_id: int) -> RouteResult:
        patient = self.repository.get_patient(patient_id)
        if patient is None:
            return RouteResult(RouteStatus.UNKNOWN_PATIENT)
        now = self.clock()
        candidates = [
            a
            for a in self.repository.appointments_between(patient_id, now - self.late, now + self.early)
            if a.status is AppointmentStatus.SCHEDULED
        ]
        chosen = self._pick(candidates, now)
        if chosen is None:
            return RouteResult(RouteStatus.NO_APPOINTMENT, patient=patient)
        return RouteResult(RouteStatus.FOUND, patient=patient, appointment=chosen)

    def route_national_id(self, national_id: str) -> RouteResult:
        """Fallback path. Raises InvalidNationalIdError for malformed input."""
        if self.hasher is None:
            raise RuntimeError("ID-number lookup needs a NationalIdHasher")
        patient_id = self.repository.find_patient_id(self.hasher.hash(national_id))
        if patient_id is None:
            return RouteResult(RouteStatus.UNKNOWN_PATIENT)
        return self.route_patient(patient_id)

    @staticmethod
    def _pick(candidates: list[Appointment], now: datetime) -> Appointment | None:
        upcoming = [a for a in candidates if a.starts_at >= now]
        if upcoming:
            return min(upcoming, key=lambda a: a.starts_at)
        return max(candidates, key=lambda a: a.starts_at, default=None)
