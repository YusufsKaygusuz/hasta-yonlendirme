"""Configuration: a TOML file for settings, environment variables for secrets.

Every field has a sensible default, so the kiosk runs with no file at all on a
development machine. Secrets (database password, ID pepper) are never read from
the TOML file, only from the environment, so the file can be committed safely.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field, fields, is_dataclass, replace
from pathlib import Path
from typing import Any, Literal, TypeVar, cast

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

Language = Literal["tr", "en"]
CameraBackend = Literal["opencv", "picamera2"]
DetectionModel = Literal["hog", "cnn"]
DatabaseBackend = Literal["sqlite", "mysql"]

DEFAULT_CONFIG_PATHS = (Path("hasta-yonlendirme.toml"), Path("/etc/hasta-yonlendirme/config.toml"))


class ConfigError(ValueError):
    """Raised for an invalid configuration file or value."""


@dataclass(frozen=True)
class KioskConfig:
    language: Language = "tr"
    fullscreen: bool = True
    result_seconds: float = 12.0
    """How long a route stays on screen before the kiosk returns to idle."""
    manual_entry_timeout_seconds: float = 45.0
    hospital_name: str = ""


@dataclass(frozen=True)
class CameraConfig:
    backend: CameraBackend = "opencv"
    device: int = 0
    width: int = 640
    height: int = 480


@dataclass(frozen=True)
class RecognitionConfig:
    detection_model: DetectionModel = "hog"
    """"hog" runs in real time on a Raspberry Pi 4; "cnn" is more accurate but needs a GPU."""
    downscale: float = 0.5
    """Frames are shrunk by this factor before detection. Smaller is faster."""
    tolerance: float = 0.5
    """Maximum face distance for a match. Lower is stricter (the library default is 0.6)."""
    ambiguity_margin: float = 0.06
    """The best match must beat the runner-up patient by at least this much."""
    confirm_frames: int = 3
    """Consecutive frames that must agree before a patient is accepted."""
    min_face_size: int = 60
    """Faces smaller than this many pixels (after downscaling) are ignored as too far away."""
    gallery_refresh_seconds: float = 300.0
    """How often the running kiosk reloads encodings to pick up newly enrolled patients."""


@dataclass(frozen=True)
class DatabaseConfig:
    backend: DatabaseBackend = "sqlite"
    path: str = "data/hasta-yonlendirme.db"
    host: str = "localhost"
    port: int = 3306
    name: str = "hasta_yonlendirme"
    user: str = "kiosk"
    password_env: str = "HY_DB_PASSWORD"  # noqa: S105 - the variable name, not a password

    @property
    def password(self) -> str:
        return os.environ.get(self.password_env, "")


@dataclass(frozen=True)
class PrivacyConfig:
    pepper_env: str = "HY_ID_PEPPER"
    """Environment variable holding the secret used to hash national ID numbers."""


@dataclass(frozen=True)
class RoutingConfig:
    early_arrival_minutes: int = 240
    """How long before an appointment the kiosk already shows it."""
    late_arrival_minutes: int = 60
    """How long after the start time an appointment is still shown."""


@dataclass(frozen=True)
class AudioConfig:
    enabled: bool = True
    voice: str = ""
    """espeak-ng voice. Empty means the kiosk language ("tr" or "en")."""
    speed: int = 150


@dataclass(frozen=True)
class Config:
    kiosk: KioskConfig = field(default_factory=KioskConfig)
    camera: CameraConfig = field(default_factory=CameraConfig)
    recognition: RecognitionConfig = field(default_factory=RecognitionConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    privacy: PrivacyConfig = field(default_factory=PrivacyConfig)
    routing: RoutingConfig = field(default_factory=RoutingConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)

    def validate(self) -> Config:
        r = self.recognition
        if not 0.1 <= r.downscale <= 1.0:
            raise ConfigError("recognition.downscale must be between 0.1 and 1.0")
        if not 0.2 <= r.tolerance <= 0.8:
            raise ConfigError("recognition.tolerance must be between 0.2 and 0.8")
        if not 0 <= r.ambiguity_margin < r.tolerance:
            raise ConfigError("recognition.ambiguity_margin must be at least 0 and below the tolerance")
        if r.confirm_frames < 1:
            raise ConfigError("recognition.confirm_frames must be at least 1")
        if self.kiosk.result_seconds <= 0 or self.kiosk.manual_entry_timeout_seconds <= 0:
            raise ConfigError("kiosk timeouts must be positive")
        _check_choice("kiosk.language", self.kiosk.language, ("tr", "en"))
        _check_choice("camera.backend", self.camera.backend, ("opencv", "picamera2"))
        _check_choice("recognition.detection_model", r.detection_model, ("hog", "cnn"))
        _check_choice("database.backend", self.database.backend, ("sqlite", "mysql"))
        return self


def _check_choice(name: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise ConfigError(f"{name} must be one of {', '.join(allowed)} (got {value!r})")


T = TypeVar("T")


def _build(cls: type[T], data: dict[str, Any], section: str) -> T:
    """Create a dataclass from a TOML table, rejecting unknown keys and wrong types."""
    assert is_dataclass(cls)
    known = {f.name: f for f in fields(cls)}
    unknown = set(data) - set(known)
    if unknown:
        raise ConfigError(f"Unknown setting(s) in [{section}]: {', '.join(sorted(unknown))}")
    defaults = cls()
    values: dict[str, Any] = {}
    for name, value in data.items():
        expected = type(getattr(defaults, name))
        if expected is float and isinstance(value, int) and not isinstance(value, bool):
            value = float(value)
        if not isinstance(value, expected) or (expected is int and isinstance(value, bool)):
            raise ConfigError(f"[{section}] {name} must be {expected.__name__}, got {type(value).__name__}")
        values[name] = value
    return cast(T, replace(cast(Any, defaults), **values))


def load_config(path: Path | None = None) -> Config:
    """Load a TOML config file, or return defaults when no file is found.

    Without an explicit path, ./hasta-yonlendirme.toml and then
    /etc/hasta-yonlendirme/config.toml are tried.
    """
    if path is None:
        path = next((p for p in DEFAULT_CONFIG_PATHS if p.is_file()), None)
        if path is None:
            return Config().validate()
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"Config file not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path} is not valid TOML: {exc}") from exc

    sections = {f.name: f for f in fields(Config)}
    unknown = set(raw) - set(sections)
    if unknown:
        raise ConfigError(f"Unknown section(s): {', '.join(sorted(unknown))}")
    parts: dict[str, Any] = {}
    for name, table in raw.items():
        if not isinstance(table, dict):
            raise ConfigError(f"[{name}] must be a table")
        section_type = type(getattr(Config(), name))
        parts[name] = _build(section_type, table, name)
    return Config(**parts).validate()
