"""Repository implementation shared by SQLite and MySQL.

Queries are written once with ``?`` placeholders; the MySQL subclass swaps them for
``%s``. Every value goes through driver parameters, never string formatting.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime
from typing import Any

import numpy as np

from hasta_yonlendirme.models import Appointment, AppointmentStatus, Clinic, Doctor, Patient
from hasta_yonlendirme.recognition.base import Encoding

ENCODING_DTYPE = np.dtype("<f8")  # little-endian float64, independent of the machine

_APPOINTMENTS_SQL = """
SELECT a.id, a.patient_id, a.starts_at, a.status,
       d.id, d.full_name, d.title,
       c.id, c.name, c.block, c.floor, c.room, c.hint
FROM appointments a
JOIN doctors d ON d.id = a.doctor_id
JOIN clinics c ON c.id = a.clinic_id
WHERE a.patient_id = ? AND a.starts_at >= ? AND a.starts_at < ?
ORDER BY a.starts_at
"""


def _to_datetime(value: Any) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))


def encoding_to_bytes(encoding: Encoding) -> bytes:
    return np.asarray(encoding, dtype=ENCODING_DTYPE).tobytes()


def encoding_from_bytes(blob: bytes) -> Encoding:
    return np.frombuffer(blob, dtype=ENCODING_DTYPE).astype(np.float64)


class SqlRepository:
    """Base class; subclasses provide the connection and the schema."""

    placeholder = "?"
    schema: Sequence[str] = ()

    def __init__(self, connection: Any) -> None:
        self._conn = connection
        self._lock = threading.Lock()

    # --- helpers -----------------------------------------------------------------------
    def _sql(self, query: str) -> str:
        return query if self.placeholder == "?" else query.replace("?", self.placeholder)

    def _ensure_connected(self) -> None:
        """Hook for servers that may drop idle connections; a file database never does."""

    @contextmanager
    def _cursor(self, commit: bool = False) -> Iterator[Any]:
        with self._lock:
            self._ensure_connected()
            cur = self._conn.cursor()
            try:
                yield cur
                if commit:
                    self._conn.commit()
            except Exception:
                if commit:
                    self._conn.rollback()
                raise
            finally:
                cur.close()

    def _insert(self, query: str, params: Sequence[Any]) -> int:
        with self._cursor(commit=True) as cur:
            cur.execute(self._sql(query), params)
            return int(cur.lastrowid)

    def _format_time(self, moment: datetime) -> Any:
        return moment.replace(microsecond=0)

    # --- schema --------------------------------------------------------------------------
    def create_schema(self) -> None:
        with self._cursor(commit=True) as cur:
            for statement in self.schema:
                cur.execute(statement)

    # --- read side ---------------------------------------------------------------------
    def get_patient(self, patient_id: int) -> Patient | None:
        with self._cursor() as cur:
            cur.execute(self._sql("SELECT id, first_name, last_name FROM patients WHERE id = ?"), (patient_id,))
            row = cur.fetchone()
        return Patient(int(row[0]), row[1], row[2]) if row else None

    def find_patient_id(self, national_id_hash: str) -> int | None:
        with self._cursor() as cur:
            cur.execute(self._sql("SELECT id FROM patients WHERE national_id_hash = ?"), (national_id_hash,))
            row = cur.fetchone()
        return int(row[0]) if row else None

    def load_encodings(self) -> list[tuple[int, Encoding]]:
        with self._cursor() as cur:
            cur.execute("SELECT patient_id, encoding FROM face_encodings ORDER BY id")
            rows = cur.fetchall()
        return [(int(pid), encoding_from_bytes(bytes(blob))) for pid, blob in rows]

    def appointments_between(self, patient_id: int, start: datetime, end: datetime) -> list[Appointment]:
        with self._cursor() as cur:
            cur.execute(
                self._sql(_APPOINTMENTS_SQL),
                (patient_id, self._format_time(start), self._format_time(end)),
            )
            rows = cur.fetchall()
        return [
            Appointment(
                id=int(r[0]),
                patient_id=int(r[1]),
                starts_at=_to_datetime(r[2]),
                status=AppointmentStatus(r[3]),
                doctor=Doctor(int(r[4]), r[5], r[6] or ""),
                clinic=Clinic(int(r[7]), r[8], r[9], r[10], r[11] or "", r[12] or ""),
            )
            for r in rows
        ]

    # --- write side ----------------------------------------------------------------------
    def add_clinic(self, name: str, block: str, floor: str, room: str = "", hint: str = "") -> int:
        return self._insert(
            "INSERT INTO clinics (name, block, floor, room, hint) VALUES (?, ?, ?, ?, ?)",
            (name, block, floor, room, hint),
        )

    def add_doctor(self, full_name: str, title: str = "") -> int:
        return self._insert("INSERT INTO doctors (full_name, title) VALUES (?, ?)", (full_name, title))

    def add_patient(self, first_name: str, last_name: str, national_id_hash: str, consent_at: datetime) -> int:
        return self._insert(
            "INSERT INTO patients (first_name, last_name, national_id_hash, consent_at) VALUES (?, ?, ?, ?)",
            (first_name, last_name, national_id_hash, self._format_time(consent_at)),
        )

    def add_encoding(self, patient_id: int, encoding: Encoding, model: str) -> int:
        return self._insert(
            "INSERT INTO face_encodings (patient_id, encoding, model, created_at) VALUES (?, ?, ?, ?)",
            (patient_id, encoding_to_bytes(encoding), model, self._format_time(datetime.now())),
        )

    def add_appointment(
        self,
        patient_id: int,
        doctor_id: int,
        clinic_id: int,
        starts_at: datetime,
        status: AppointmentStatus = AppointmentStatus.SCHEDULED,
    ) -> int:
        return self._insert(
            "INSERT INTO appointments (patient_id, doctor_id, clinic_id, starts_at, status) VALUES (?, ?, ?, ?, ?)",
            (patient_id, doctor_id, clinic_id, self._format_time(starts_at), status.value),
        )

    def delete_face_data(self, patient_id: int) -> int:
        with self._cursor(commit=True) as cur:
            cur.execute(self._sql("DELETE FROM face_encodings WHERE patient_id = ?"), (patient_id,))
            return int(cur.rowcount)

    def close(self) -> None:
        self._conn.close()
