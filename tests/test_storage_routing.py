from __future__ import annotations

from datetime import timedelta

import numpy as np
import pytest

from hasta_yonlendirme.identity import InvalidNationalIdError, NationalIdHasher
from hasta_yonlendirme.models import AppointmentStatus, RouteStatus
from hasta_yonlendirme.routing import RoutingService
from hasta_yonlendirme.storage.sql import SqlRepository, encoding_from_bytes, encoding_to_bytes
from hasta_yonlendirme.storage.sqlite import SQLiteRepository

from .conftest import AYSE_ID, MEHMET_ID, NOW, FakeClock, unit_vector


def test_encoding_round_trip_is_exact() -> None:
    vector = np.random.default_rng(7).normal(size=128)
    assert np.array_equal(encoding_from_bytes(encoding_to_bytes(vector)), vector)


def test_schema_creation_is_idempotent(repo: SqlRepository) -> None:
    repo.create_schema()


def test_patients_and_encodings(repo: SqlRepository, hospital: dict[str, int], hasher: NationalIdHasher) -> None:
    patient = repo.get_patient(hospital["ayse"])
    assert patient is not None
    assert patient.public_name == "Ayşe D."
    assert repo.find_patient_id(hasher.hash(AYSE_ID)) == hospital["ayse"]
    assert repo.get_patient(999) is None
    encodings = dict(repo.load_encodings())
    assert np.array_equal(encodings[hospital["mehmet"]], unit_vector(1))


def test_national_id_is_never_stored_in_clear(repo: SqlRepository, hospital: dict[str, int]) -> None:
    if not isinstance(repo, SQLiteRepository):
        pytest.skip("uses SQLite's dump")
    dump = "\n".join(repo._conn.iterdump())
    assert AYSE_ID not in dump
    assert MEHMET_ID not in dump


def test_appointments_between_joins_clinic_and_doctor(repo: SqlRepository, hospital: dict[str, int]) -> None:
    (appt,) = repo.appointments_between(hospital["ayse"], NOW, NOW + timedelta(hours=1))
    assert appt.clinic.block == "A"
    assert appt.clinic.floor == "2"
    assert appt.doctor.display_name == "Doç. Dr. Elif Yıldırım"
    assert appt.starts_at == NOW.replace(minute=30)
    assert repo.appointments_between(hospital["ayse"], NOW + timedelta(hours=1), NOW + timedelta(hours=2)) == []


def test_delete_face_data_keeps_the_patient(repo: SqlRepository, hospital: dict[str, int]) -> None:
    assert repo.delete_face_data(hospital["ayse"]) == 1
    assert hospital["ayse"] not in dict(repo.load_encodings())
    assert repo.get_patient(hospital["ayse"]) is not None


def test_duplicate_national_id_is_rejected(repo: SqlRepository, hasher: NationalIdHasher) -> None:
    repo.add_patient("A", "B", hasher.hash(AYSE_ID), consent_at=NOW)
    with pytest.raises(Exception) as excinfo:  # noqa: PT011 - each driver has its own IntegrityError
        repo.add_patient("C", "D", hasher.hash(AYSE_ID), consent_at=NOW)
    assert type(excinfo.value).__name__ == "IntegrityError"


@pytest.fixture
def routing(repo: SqlRepository, hasher: NationalIdHasher, clock: FakeClock) -> RoutingService:
    return RoutingService(repo, hasher, clock=clock.datetime)


def test_route_found(routing: RoutingService, hospital: dict[str, int]) -> None:
    result = routing.route_patient(hospital["ayse"])
    assert result.status is RouteStatus.FOUND
    assert result.appointment is not None
    assert result.appointment.clinic.name == "Göz Hastalıkları"


def test_route_no_appointment(routing: RoutingService, hospital: dict[str, int]) -> None:
    result = routing.route_patient(hospital["mehmet"])
    assert result.status is RouteStatus.NO_APPOINTMENT
    assert result.patient is not None


def test_route_unknown_patient(routing: RoutingService) -> None:
    assert routing.route_patient(12345).status is RouteStatus.UNKNOWN_PATIENT


def test_route_by_national_id(routing: RoutingService, hospital: dict[str, int]) -> None:
    assert routing.route_national_id(AYSE_ID).status is RouteStatus.FOUND
    assert routing.route_national_id("10000000146").status is RouteStatus.UNKNOWN_PATIENT
    with pytest.raises(InvalidNationalIdError):
        routing.route_national_id("12345678901")


def test_route_by_national_id_needs_a_hasher(repo: SqlRepository) -> None:
    with pytest.raises(RuntimeError, match="NationalIdHasher"):
        RoutingService(repo).route_national_id(AYSE_ID)


def test_cancelled_appointments_are_ignored(
    repo: SqlRepository, routing: RoutingService, hospital: dict[str, int]
) -> None:
    repo.add_appointment(
        hospital["mehmet"], hospital["doctor"], hospital["cardio"], NOW, status=AppointmentStatus.CANCELLED
    )
    assert routing.route_patient(hospital["mehmet"]).status is RouteStatus.NO_APPOINTMENT


@pytest.mark.parametrize(
    ("offsets_minutes", "expected_offset"),
    [
        ([30, 120], 30),  # the nearest upcoming one
        ([-20, 90], 90),  # upcoming beats already started
        ([-50, -20], -20),  # all started: the most recent
        ([-90], None),  # started too long ago
        ([300], None),  # too far ahead
    ],
)
def test_appointment_choice(
    repo: SqlRepository,
    routing: RoutingService,
    hospital: dict[str, int],
    offsets_minutes: list[int],
    expected_offset: int | None,
) -> None:
    patient = hospital["mehmet"]
    for offset in offsets_minutes:
        repo.add_appointment(patient, hospital["doctor"], hospital["cardio"], NOW + timedelta(minutes=offset))
    result = routing.route_patient(patient)
    if expected_offset is None:
        assert result.status is RouteStatus.NO_APPOINTMENT
    else:
        assert result.appointment is not None
        assert result.appointment.starts_at == NOW + timedelta(minutes=expected_offset)
