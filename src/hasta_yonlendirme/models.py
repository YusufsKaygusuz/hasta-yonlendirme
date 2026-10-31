"""Domain objects shared by storage, routing and the kiosk.

They are plain, immutable dataclasses with no knowledge of databases or cameras,
so every other layer can be tested without hardware.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Clinic:
    id: int
    name: str
    block: str
    floor: str
    room: str = ""
    hint: str = ""
    """Free-text directions shown under the location, e.g. "Take the lift on your right"."""


@dataclass(frozen=True, slots=True)
class Doctor:
    id: int
    full_name: str
    title: str = ""

    @property
    def display_name(self) -> str:
        return f"{self.title} {self.full_name}".strip()


@dataclass(frozen=True, slots=True)
class Patient:
    id: int
    first_name: str
    last_name: str

    @property
    def public_name(self) -> str:
        """Name safe to show on a screen in a public hallway: "Ayşe D."."""
        initial = self.last_name[:1].upper()
        return f"{self.first_name} {initial}." if initial else self.first_name


class AppointmentStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


@dataclass(frozen=True, slots=True)
class Appointment:
    id: int
    patient_id: int
    starts_at: datetime
    doctor: Doctor
    clinic: Clinic
    status: AppointmentStatus = AppointmentStatus.SCHEDULED


class RouteStatus(str, enum.Enum):
    FOUND = "found"
    NO_APPOINTMENT = "no_appointment"
    UNKNOWN_PATIENT = "unknown_patient"


@dataclass(frozen=True, slots=True)
class RouteResult:
    status: RouteStatus
    patient: Patient | None = None
    appointment: Appointment | None = None
