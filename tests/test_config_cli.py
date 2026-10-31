from __future__ import annotations

from pathlib import Path

import pytest

from hasta_yonlendirme.cli import main
from hasta_yonlendirme.config import Config, ConfigError, load_config
from hasta_yonlendirme.demo import PATIENTS
from hasta_yonlendirme.storage.sqlite import SQLiteRepository

EXAMPLE = Path(__file__).resolve().parent.parent / "config" / "hasta-yonlendirme.example.toml"


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_defaults_without_a_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert load_config() == Config()


def test_example_config_is_valid() -> None:
    config = load_config(EXAMPLE)
    assert config.kiosk.language == "tr"


def test_values_are_read_and_ints_become_floats(tmp_path: Path) -> None:
    config = load_config(write(tmp_path, "[recognition]\ntolerance = 0.45\n[kiosk]\nresult_seconds = 8\n"))
    assert config.recognition.tolerance == 0.45
    assert config.kiosk.result_seconds == 8.0


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("[kiosk]\nlanguag = 'tr'\n", "Unknown setting"),
        ("[kiosks]\n", "Unknown section"),
        ("[kiosk]\nfullscreen = 'yes'\n", "must be bool"),
        ("[camera]\ndevice = true\n", "must be int"),
        ("[recognition]\ntolerance = 0.95\n", "tolerance"),
        ("[recognition]\nconfirm_frames = 0\n", "confirm_frames"),
        ("[kiosk]\nlanguage = 'de'\n", "kiosk.language"),
        ("[database]\nbackend = 'oracle'\n", "database.backend"),
        ("kiosk = 3\n", "must be a table"),
        ("not toml [", "not valid TOML"),
    ],
)
def test_invalid_configs(tmp_path: Path, text: str, message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        load_config(write(tmp_path, text))


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.toml")


def test_password_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HY_DB_PASSWORD", "s3cret")
    assert Config().database.password == "s3cret"


@pytest.fixture
def cli_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db = tmp_path / "kiosk.db"
    monkeypatch.setenv("HY_ID_PEPPER", "p" * 32)
    write(tmp_path, f"[database]\npath = '{db}'\n")
    return tmp_path / "config.toml"


def test_cli_demo_and_management(cli_env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["-c", str(cli_env), "demo"]) == 0
    assert PATIENTS[0].national_id in capsys.readouterr().out

    national_id = PATIENTS[2].national_id
    assert main(["-c", str(cli_env), "add-appointment", "--national-id", national_id,
                 "--clinic", "1", "--doctor", "1", "--at", "2026-11-02 14:30"]) == 0  # fmt: skip
    assert main(["-c", str(cli_env), "add-clinic", "--name", "Nöroloji", "--block", "D", "--floor", "4"]) == 0
    assert main(["-c", str(cli_env), "add-doctor", "--name", "Ali Veli", "--title", "Dr."]) == 0
    assert main(["-c", str(cli_env), "forget", "--national-id", national_id]) == 0
    assert "Deleted 0 face encoding" in capsys.readouterr().out


def test_cli_reports_operator_errors(cli_env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["-c", str(cli_env), "init-db"]) == 0
    assert main(["-c", str(cli_env), "forget", "--national-id", "10000000146"]) == 1
    assert "No patient is registered" in capsys.readouterr().err
    assert main(["-c", str(cli_env), "forget", "--national-id", "12345678901"]) == 1
    assert main(["-c", str(cli_env), "add-appointment", "--national-id", "10000000146",
                 "--clinic", "1", "--doctor", "1", "--at", "tomorrow"]) == 1  # fmt: skip
    assert "--at must look like" in capsys.readouterr().err


def test_enroll_requires_consent(cli_env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["-c", str(cli_env), "enroll", "--first-name", "A", "--last-name", "B",
                 "--national-id", "10000000146", "--photo", "x.jpg"])  # fmt: skip
    assert code == 1
    assert "explicit consent" in capsys.readouterr().err


def test_cli_without_pepper_explains_how_to_set_it(
    cli_env: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("HY_ID_PEPPER")
    assert main(["-c", str(cli_env), "demo"]) == 1
    assert "openssl rand" in capsys.readouterr().err


def test_demo_data_is_consistent(cli_env: Path) -> None:
    main(["-c", str(cli_env), "demo"])
    repo = SQLiteRepository(cli_env.parent / "kiosk.db")
    try:
        assert repo.get_patient(1) is not None
    finally:
        repo.close()
