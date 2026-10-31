"""SQLite repository: zero setup, ideal for a single kiosk, development and tests."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from hasta_yonlendirme.storage.sql import SqlRepository

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS clinics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        block TEXT NOT NULL,
        floor TEXT NOT NULL,
        room TEXT NOT NULL DEFAULT '',
        hint TEXT NOT NULL DEFAULT ''
    )""",
    """CREATE TABLE IF NOT EXISTS doctors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        title TEXT NOT NULL DEFAULT ''
    )""",
    """CREATE TABLE IF NOT EXISTS patients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        first_name TEXT NOT NULL,
        last_name TEXT NOT NULL,
        national_id_hash TEXT NOT NULL UNIQUE,
        consent_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS face_encodings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
        encoding BLOB NOT NULL,
        model TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS appointments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
        doctor_id INTEGER NOT NULL REFERENCES doctors(id),
        clinic_id INTEGER NOT NULL REFERENCES clinics(id),
        starts_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'scheduled'
    )""",
    "CREATE INDEX IF NOT EXISTS ix_appointments_patient_time ON appointments (patient_id, starts_at)",
    "CREATE INDEX IF NOT EXISTS ix_face_encodings_patient ON face_encodings (patient_id)",
)


class SQLiteRepository(SqlRepository):
    schema = SCHEMA

    def __init__(self, path: str | Path) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        # The kiosk reads from its UI thread and the CLI from the main thread; access is
        # serialised by the lock in SqlRepository.
        conn = sqlite3.connect(str(path), check_same_thread=False)
        conn.execute("PRAGMA foreign_keys = ON")
        super().__init__(conn)

    def _format_time(self, moment: datetime) -> str:
        # Stored as ISO text so that string order equals time order.
        return moment.replace(microsecond=0).isoformat(sep=" ")
