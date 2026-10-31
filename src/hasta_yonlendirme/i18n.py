"""User-facing text in Turkish and English.

Kept in one small catalogue rather than gettext: the kiosk has a few dozen strings
and hospitals often want to edit the wording, which is easier in plain Python.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Final

from hasta_yonlendirme.config import Language

_CATALOGUE: Final[Mapping[str, Mapping[str, str]]] = {
    "tr": {
        "idle.title": "Hoş geldiniz",
        "idle.body": "Randevunuzu bulmak için lütfen kameraya bakın.",
        "idle.manual": "TC kimlik no ile devam et",
        "scanning": "Yüzünüz tanınıyor…",
        "found.greeting": "Merhaba {name}",
        "found.time": "Randevu saati {time}",
        "found.speech": "Merhaba {name}. {clinic}, {block} blok, {floor}. Doktorunuz {doctor}.",
        "location.block": "{block} Blok",
        "location.floor": "{floor}. Kat",
        "location.room": "Oda {room}",
        "no_appointment.title": "Bugün için randevunuz bulunamadı",
        "no_appointment.body": "Lütfen danışma masasına başvurun.",
        "no_appointment.speech": "Bugün için randevunuz bulunamadı. Lütfen danışma masasına başvurun.",
        "unknown.title": "Sizi tanıyamadık",
        "unknown.body": "TC kimlik numaranızla devam edebilirsiniz.",
        "unknown.speech": "Sizi tanıyamadık. TC kimlik numaranızla devam edebilirsiniz.",
        "manual.title": "TC kimlik numaranızı girin",
        "manual.invalid": "Geçersiz kimlik numarası. Lütfen kontrol edin.",
        "manual.submit": "Devam",
        "manual.clear": "Sil",
        "manual.cancel": "Vazgeç",
        "privacy.notice": "Fotoğrafınız kaydedilmez.",
        "error.camera": "Kamera şu anda kullanılamıyor. TC kimlik numaranızla devam edebilirsiniz.",
    },
    "en": {
        "idle.title": "Welcome",
        "idle.body": "Please look at the camera to find your appointment.",
        "idle.manual": "Continue with ID number",
        "scanning": "Recognising…",
        "found.greeting": "Hello {name}",
        "found.time": "Appointment at {time}",
        "found.speech": "Hello {name}. {clinic}, block {block}, {floor}. Your doctor is {doctor}.",
        "location.block": "Block {block}",
        "location.floor": "Floor {floor}",
        "location.room": "Room {room}",
        "no_appointment.title": "No appointment found for today",
        "no_appointment.body": "Please ask at the information desk.",
        "no_appointment.speech": "No appointment found for today. Please ask at the information desk.",
        "unknown.title": "We could not recognise you",
        "unknown.body": "You can continue with your national ID number.",
        "unknown.speech": "We could not recognise you. You can continue with your national ID number.",
        "manual.title": "Enter your national ID number",
        "manual.invalid": "Invalid ID number. Please check it.",
        "manual.submit": "Continue",
        "manual.clear": "Delete",
        "manual.cancel": "Cancel",
        "privacy.notice": "Your photo is never stored.",
        "error.camera": "The camera is unavailable. You can continue with your national ID number.",
    },
}


class Messages:
    """Looks up and formats kiosk text for one language."""

    def __init__(self, language: Language) -> None:
        self.language = language
        self._table = _CATALOGUE[language]

    def __call__(self, key: str, **values: object) -> str:
        return self._table[key].format(**values)

    def time(self, moment: datetime) -> str:
        return moment.strftime("%H:%M")

    def spoken_floor(self, floor: str) -> str:
        """Floor as a speech engine should read it: "2" -> "ikinci kat" / "floor 2"."""
        if self.language == "en":
            return "the ground floor" if floor == "0" else f"floor {floor}"
        word = _TR_ORDINALS.get(floor)
        return f"{word} kat" if word else f"{floor}. kat"

    def speakable(self, text: str) -> str:
        """Expand abbreviations that speech engines read letter by letter ("Doç. Dr.")."""
        for short, full in _SPOKEN_ABBREVIATIONS.get(self.language, ()):
            text = text.replace(short, full)
        return text


_TR_ORDINALS: Final[Mapping[str, str]] = {
    "-2": "eksi ikinci",
    "-1": "eksi birinci",
    "0": "zemin",
    "1": "birinci",
    "2": "ikinci",
    "3": "üçüncü",
    "4": "dördüncü",
    "5": "beşinci",
    "6": "altıncı",
    "7": "yedinci",
    "8": "sekizinci",
    "9": "dokuzuncu",
    "10": "onuncu",
}

# Longest first, so "Dr." does not swallow the end of "Prof. Dr.".
_SPOKEN_ABBREVIATIONS: Final[Mapping[str, tuple[tuple[str, str], ...]]] = {
    "tr": (
        ("Dr. Öğr. Üyesi", "Doktor Öğretim Üyesi"),
        ("Prof. Dr.", "Profesör Doktor"),
        ("Doç. Dr.", "Doçent Doktor"),
        ("Uzm. Dr.", "Uzman Doktor"),
        ("Op. Dr.", "Operatör Doktor"),
        ("Dr.", "Doktor"),
    ),
    "en": (
        ("Prof. Dr.", "Professor Doctor"),
        ("Dr.", "Doctor"),
    ),
}


def catalogue_keys(language: Language) -> frozenset[str]:
    return frozenset(_CATALOGUE[language])
