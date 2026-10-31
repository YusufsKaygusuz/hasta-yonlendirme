"""Persistence for clinics, doctors, patients, face encodings and appointments."""

from __future__ import annotations

from hasta_yonlendirme.config import DatabaseConfig
from hasta_yonlendirme.storage.base import Repository
from hasta_yonlendirme.storage.sqlite import SQLiteRepository


def open_repository(config: DatabaseConfig) -> Repository:
    """Open the repository selected in the configuration."""
    if config.backend == "mysql":
        from hasta_yonlendirme.storage.mysql import MySQLRepository

        return MySQLRepository(config)
    return SQLiteRepository(config.path)


__all__ = ["Repository", "SQLiteRepository", "open_repository"]
