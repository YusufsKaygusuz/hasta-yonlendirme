from __future__ import annotations

import pytest

from hasta_yonlendirme.demo import make_national_id
from hasta_yonlendirme.identity import (
    InvalidNationalIdError,
    MissingPepperError,
    NationalIdHasher,
    is_valid_national_id,
    normalize_national_id,
)


@pytest.mark.parametrize("value", ["10000000146", "100 000 001 46", "1000-0000-146"])
def test_valid_ids(value: str) -> None:
    assert is_valid_national_id(value)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "1000000014",  # too short
        "100000001466",  # too long
        "00000000146",  # leading zero
        "10000000156",  # wrong 10th digit
        "10000000147",  # wrong 11th digit
        "1000000014a",
    ],
)
def test_invalid_ids(value: str) -> None:
    assert not is_valid_national_id(value)


def test_generated_ids_pass_the_checksum() -> None:
    for prefix in ("111111111", "987654321", "100000001"):
        assert is_valid_national_id(make_national_id(prefix))
    assert make_national_id("100000001") == "10000000146"


def test_make_national_id_rejects_bad_prefix() -> None:
    with pytest.raises(ValueError, match="nine digits"):
        make_national_id("012345678")


def test_normalize_removes_separators() -> None:
    assert normalize_national_id(" 100-000 00146 ") == "10000000146"


def test_hash_is_stable_keyed_and_hides_the_number() -> None:
    a = NationalIdHasher(b"a" * 32)
    b = NationalIdHasher(b"b" * 32)
    digest = a.hash("10000000146")
    assert digest == a.hash("100 000 001 46")
    assert digest != b.hash("10000000146")
    assert "10000000146" not in digest
    assert len(digest) == 64


def test_hash_rejects_invalid_ids() -> None:
    with pytest.raises(InvalidNationalIdError):
        NationalIdHasher(b"a" * 32).hash("12345678901")


def test_short_pepper_is_rejected() -> None:
    with pytest.raises(MissingPepperError):
        NationalIdHasher(b"short")


def test_pepper_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_PEPPER", "x" * 32)
    assert NationalIdHasher.from_env("TEST_PEPPER").hash("10000000146")
    monkeypatch.delenv("TEST_PEPPER")
    with pytest.raises(MissingPepperError, match="TEST_PEPPER"):
        NationalIdHasher.from_env("TEST_PEPPER")
