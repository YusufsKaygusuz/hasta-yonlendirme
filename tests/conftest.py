from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import datetime

import numpy as np
import pytest

from hasta_yonlendirme.demo import make_national_id
from hasta_yonlendirme.identity import NationalIdHasher
from hasta_yonlendirme.recognition.base import DetectedFace, Encoding, Frame
from hasta_yonlendirme.storage.sql import SqlRepository
from hasta_yonlendirme.storage.sqlite import SQLiteRepository

NOW = datetime(2026, 11, 2, 10, 0)
PEPPER = b"test-pepper-not-for-production-use"
AYSE_ID = make_national_id("444444444")
MEHMET_ID = make_national_id("555555555")


def unit_vector(index: int, dim: int = 128) -> Encoding:
    v = np.zeros(dim)
    v[index] = 1.0
    return v


class FakeClock:
    """Controllable replacement for datetime.now / time.monotonic."""

    def __init__(self, start: datetime = NOW) -> None:
        self.now = start
        self.seconds = 0.0

    def datetime(self) -> datetime:
        return self.now

    def monotonic(self) -> float:
        return self.seconds

    def advance(self, seconds: float) -> None:
        self.seconds += seconds


class ScriptedEncoder:
    """FaceEncoder that returns pre-set faces; the frame content is ignored."""

    def __init__(self, faces: list[DetectedFace] | None = None) -> None:
        self.faces = faces or []

    def encode(self, frame: Frame) -> list[DetectedFace]:
        return list(self.faces)


class RecordingAnnouncer:
    def __init__(self) -> None:
        self.spoken: list[str] = []

    def say(self, text: str) -> None:
        self.spoken.append(text)


@pytest.fixture
def hasher() -> NationalIdHasher:
    return NationalIdHasher(PEPPER)


def _mysql_repository() -> SqlRepository:
    """A clean MySQL database for one test; skipped unless HY_TEST_MYSQL_HOST is set (CI does)."""
    host = os.environ.get("HY_TEST_MYSQL_HOST")
    if not host:
        pytest.skip("set HY_TEST_MYSQL_HOST to run the MySQL tests")
    from hasta_yonlendirme.config import DatabaseConfig
    from hasta_yonlendirme.storage.mysql import MySQLRepository

    config = DatabaseConfig(
        backend="mysql",
        host=host,
        port=int(os.environ.get("HY_TEST_MYSQL_PORT", "3306")),
        name=os.environ.get("HY_TEST_MYSQL_DATABASE", "hasta_test"),
        user=os.environ.get("HY_TEST_MYSQL_USER", "root"),
        password_env="HY_TEST_MYSQL_PASSWORD",
    )
    repository = MySQLRepository(config)
    with repository._cursor(commit=True) as cur:
        for table in ("appointments", "face_encodings", "patients", "doctors", "clinics"):
            cur.execute(f"DROP TABLE IF EXISTS {table}")
    return repository


@pytest.fixture(params=["sqlite", pytest.param("mysql", marks=pytest.mark.mysql)])
def repo(request: pytest.FixtureRequest) -> Iterator[SqlRepository]:
    """Every storage-backed test runs against SQLite, and against MySQL when one is available."""
    repository = SQLiteRepository(":memory:") if request.param == "sqlite" else _mysql_repository()
    repository.create_schema()
    yield repository
    repository.close()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def hospital(repo: SqlRepository, hasher: NationalIdHasher) -> dict[str, int]:
    """Two clinics, two doctors, two patients; Ayşe has an appointment at 10:30."""
    eye = repo.add_clinic("Göz Hastalıkları", "A", "2", "214", "Asansörden çıkınca sağa dönün.")
    cardio = repo.add_clinic("Kardiyoloji", "B", "1")
    doctor = repo.add_doctor("Elif Yıldırım", "Doç. Dr.")
    ayse = repo.add_patient("Ayşe", "Demir", hasher.hash(AYSE_ID), consent_at=NOW)
    mehmet = repo.add_patient("Mehmet", "Kaya", hasher.hash(MEHMET_ID), consent_at=NOW)
    repo.add_encoding(ayse, unit_vector(0), "test")
    repo.add_encoding(mehmet, unit_vector(1), "test")
    repo.add_appointment(ayse, doctor, eye, NOW.replace(minute=30))
    return {"eye": eye, "cardio": cardio, "doctor": doctor, "ayse": ayse, "mehmet": mehmet}
