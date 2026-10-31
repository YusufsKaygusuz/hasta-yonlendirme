"""The storage contract the kiosk relies on.

Hospitals already have a hospital information system (HIS) with patients and
appointments. To connect the kiosk to it, implement :class:`Repository` on top of
that system (or a read replica of it); nothing else in the package needs to change.
The bundled SQLite and MySQL repositories are a complete reference implementation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from hasta_yonlendirme.models import Appointment, AppointmentStatus, Patient
from hasta_yonlendirme.recognition.base import Encoding


class Repository(Protocol):
    # --- read side: used by the running kiosk -------------------------------------------
    def get_patient(self, patient_id: int) -> Patient | None: ...

    def find_patient_id(self, national_id_hash: str) -> int | None: ...

    def load_encodings(self) -> list[tuple[int, Encoding]]:
        """Every registered face encoding, as (patient_id, encoding) pairs."""
        ...

    def appointments_between(self, patient_id: int, start: datetime, end: datetime) -> list[Appointment]:
        """The patient's appointments starting in [start, end), earliest first."""
        ...

    # --- write side: used by the admin CLI ---------------------------------------------
    def create_schema(self) -> None: ...

    def add_clinic(self, name: str, block: str, floor: str, room: str = "", hint: str = "") -> int: ...

    def add_doctor(self, full_name: str, title: str = "") -> int: ...

    def add_patient(self, first_name: str, last_name: str, national_id_hash: str, consent_at: datetime) -> int:
        """Register a patient. ``consent_at`` records when explicit consent was given."""
        ...

    def add_encoding(self, patient_id: int, encoding: Encoding, model: str) -> int: ...

    def add_appointment(
        self,
        patient_id: int,
        doctor_id: int,
        clinic_id: int,
        starts_at: datetime,
        status: AppointmentStatus = AppointmentStatus.SCHEDULED,
    ) -> int: ...

    def delete_face_data(self, patient_id: int) -> int:
        """Erase a patient's biometric data (consent withdrawn). Returns rows deleted."""
        ...

    def close(self) -> None: ...
