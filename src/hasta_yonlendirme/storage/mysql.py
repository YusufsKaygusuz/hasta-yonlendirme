"""MySQL repository, for hospitals that keep kiosk data next to their existing systems.

The kiosk connects remotely; nothing about patients is stored on the Raspberry Pi.
Give the kiosk's database user only SELECT on these tables; enrolment runs from an
administrator's machine with a separate account.
"""

from __future__ import annotations

from typing import Any

from hasta_yonlendirme.config import DatabaseConfig
from hasta_yonlendirme.storage.sql import SqlRepository

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS clinics (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(200) NOT NULL,
        block VARCHAR(20) NOT NULL,
        floor VARCHAR(20) NOT NULL,
        room VARCHAR(40) NOT NULL DEFAULT '',
        hint VARCHAR(300) NOT NULL DEFAULT ''
    ) CHARACTER SET utf8mb4""",
    """CREATE TABLE IF NOT EXISTS doctors (
        id INT AUTO_INCREMENT PRIMARY KEY,
        full_name VARCHAR(200) NOT NULL,
        title VARCHAR(60) NOT NULL DEFAULT ''
    ) CHARACTER SET utf8mb4""",
    """CREATE TABLE IF NOT EXISTS patients (
        id INT AUTO_INCREMENT PRIMARY KEY,
        first_name VARCHAR(100) NOT NULL,
        last_name VARCHAR(100) NOT NULL,
        national_id_hash CHAR(64) NOT NULL UNIQUE,
        consent_at DATETIME NOT NULL
    ) CHARACTER SET utf8mb4""",
    """CREATE TABLE IF NOT EXISTS face_encodings (
        id INT AUTO_INCREMENT PRIMARY KEY,
        patient_id INT NOT NULL,
        encoding BLOB NOT NULL,
        model VARCHAR(40) NOT NULL,
        created_at DATETIME NOT NULL,
        INDEX ix_face_encodings_patient (patient_id),
        FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE
    ) CHARACTER SET utf8mb4""",
    """CREATE TABLE IF NOT EXISTS appointments (
        id INT AUTO_INCREMENT PRIMARY KEY,
        patient_id INT NOT NULL,
        doctor_id INT NOT NULL,
        clinic_id INT NOT NULL,
        starts_at DATETIME NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'scheduled',
        INDEX ix_appointments_patient_time (patient_id, starts_at),
        FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
        FOREIGN KEY (doctor_id) REFERENCES doctors(id),
        FOREIGN KEY (clinic_id) REFERENCES clinics(id)
    ) CHARACTER SET utf8mb4""",
)


class MySQLRepository(SqlRepository):
    placeholder = "%s"
    schema = SCHEMA

    def __init__(self, config: DatabaseConfig) -> None:
        try:
            import mysql.connector
        except ImportError as exc:  # pragma: no cover - depends on the machine
            raise RuntimeError("MySQL support is not installed. Run: pip install 'hasta-yonlendirme[mysql]'") from exc
        conn: Any = mysql.connector.connect(
            host=config.host,
            port=config.port,
            user=config.user,
            password=config.password,
            database=config.name,
            charset="utf8mb4",
            # Autocommit so every read sees fresh appointments; a long-lived transaction
            # would keep serving the snapshot taken when the kiosk started.
            autocommit=True,
            connection_timeout=10,
        )
        super().__init__(conn)

    def _ensure_connected(self) -> None:
        # A kiosk runs for weeks; reconnect transparently if the server dropped us.
        self._conn.ping(reconnect=True, attempts=3, delay=2)
