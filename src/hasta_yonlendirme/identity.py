"""Turkish national ID (T.C. Kimlik No) validation and pseudonymisation.

The kiosk never stores a national ID in clear text. It keeps a keyed hash (HMAC-SHA256)
instead, so a leaked database cannot be reversed into ID numbers without the secret
"pepper", which lives outside the database (an environment variable).
"""

from __future__ import annotations

import hashlib
import hmac
import os

MIN_PEPPER_BYTES = 16


class InvalidNationalIdError(ValueError):
    """Raised for input that is not a well-formed national ID."""


class MissingPepperError(RuntimeError):
    """Raised when the hashing secret is not configured."""


def normalize_national_id(raw: str) -> str:
    """Strip spaces and dashes a user may type on the keypad."""
    return "".join(ch for ch in raw if not ch.isspace() and ch != "-")


def is_valid_national_id(raw: str) -> bool:
    """Check length, leading digit and the two checksum digits of a T.C. Kimlik No.

    Rules (official algorithm): 11 digits, the first is not 0,
    d10 = ((d1+d3+d5+d7+d9) * 7 - (d2+d4+d6+d8)) mod 10 and
    d11 = (d1 + ... + d10) mod 10.
    """
    value = normalize_national_id(raw)
    if len(value) != 11 or not value.isdigit() or value[0] == "0":
        return False
    d = [int(ch) for ch in value]
    odd = d[0] + d[2] + d[4] + d[6] + d[8]
    even = d[1] + d[3] + d[5] + d[7]
    if (odd * 7 - even) % 10 != d[9]:
        return False
    return sum(d[:10]) % 10 == d[10]


class NationalIdHasher:
    """Turns a national ID into a stable, non-reversible lookup key."""

    def __init__(self, pepper: bytes) -> None:
        if len(pepper) < MIN_PEPPER_BYTES:
            raise MissingPepperError(f"The ID pepper must be at least {MIN_PEPPER_BYTES} bytes long.")
        self._pepper = pepper

    @classmethod
    def from_env(cls, variable: str) -> NationalIdHasher:
        value = os.environ.get(variable, "")
        if not value:
            raise MissingPepperError(
                f"Set the {variable} environment variable to a long random secret, "
                f'for example: export {variable}="$(openssl rand -hex 32)"'
            )
        return cls(value.encode("utf-8"))

    def hash(self, raw: str) -> str:
        """Validate and hash an ID. Raises InvalidNationalIdError for malformed input."""
        value = normalize_national_id(raw)
        if not is_valid_national_id(value):
            raise InvalidNationalIdError("Not a valid national ID number.")
        return hmac.new(self._pepper, value.encode("ascii"), hashlib.sha256).hexdigest()
