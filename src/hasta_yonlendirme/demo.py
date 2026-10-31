"""Sample hospital data for trying the kiosk without real patients.

Every name here is fictional. The ID numbers repeat one digit (11111111110, ...): they
pass the checksum, so they can be typed on the keypad, but are recognisably fake test
values rather than numbers that could belong to a real person.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from hasta_yonlendirme.identity import NationalIdHasher
from hasta_yonlendirme.storage.base import Repository


def make_national_id(first_nine: str) -> str:
    """Append the two checksum digits to nine digits (the first must not be 0)."""
    if len(first_nine) != 9 or not first_nine.isdigit() or first_nine[0] == "0":
        raise ValueError("Need nine digits, the first not 0")
    d = [int(ch) for ch in first_nine]
    tenth = ((d[0] + d[2] + d[4] + d[6] + d[8]) * 7 - (d[1] + d[3] + d[5] + d[7])) % 10
    eleventh = (sum(d) + tenth) % 10
    return f"{first_nine}{tenth}{eleventh}"


@dataclass(frozen=True)
class DemoPatient:
    first_name: str
    last_name: str
    national_id: str
    has_appointment: bool


CLINICS = (
    ("Göz Hastalıkları", "A", "2", "214", "Asansörden çıkınca sağa dönün."),
    ("Kardiyoloji", "B", "1", "105", "Ana koridorun sonunda, solda."),
    ("Dahiliye", "A", "1", "118", ""),
    ("Ortopedi", "C", "3", "302", "C blok asansörlerini kullanın."),
)

DOCTORS = (
    ("Elif Yıldırım", "Doç. Dr."),
    ("Mehmet Kaya", "Uzm. Dr."),
    ("Zeynep Arslan", "Prof. Dr."),
    ("Can Demir", "Op. Dr."),
)

PATIENTS = (
    DemoPatient("Ayşe", "Demir", make_national_id("111111111"), True),
    DemoPatient("Mustafa", "Şahin", make_national_id("222222222"), True),
    DemoPatient("Fatma", "Çelik", make_national_id("333333333"), False),
)


def seed_demo_data(repository: Repository, hasher: NationalIdHasher, now: datetime | None = None) -> list[DemoPatient]:
    """Create clinics, doctors and patients; patients with an appointment get one later today."""
    now = (now or datetime.now()).replace(second=0, microsecond=0)
    clinic_ids = [repository.add_clinic(*clinic) for clinic in CLINICS]
    doctor_ids = [repository.add_doctor(name, title) for name, title in DOCTORS]
    for index, patient in enumerate(PATIENTS):
        patient_id = repository.add_patient(
            patient.first_name, patient.last_name, hasher.hash(patient.national_id), consent_at=now
        )
        if patient.has_appointment:
            repository.add_appointment(
                patient_id, doctor_ids[index], clinic_ids[index], now + timedelta(minutes=30 + 20 * index)
            )
    return list(PATIENTS)
