from __future__ import annotations

import pytest

from hasta_yonlendirme.i18n import Messages, catalogue_keys
from hasta_yonlendirme.identity import NationalIdHasher
from hasta_yonlendirme.kiosk.console_ui import describe
from hasta_yonlendirme.kiosk.controller import KioskController, Screen
from hasta_yonlendirme.recognition.pipeline import Observation, Verdict
from hasta_yonlendirme.routing import RoutingService
from hasta_yonlendirme.storage.sql import SqlRepository

from .conftest import AYSE_ID, MEHMET_ID, FakeClock, RecordingAnnouncer

RESULT_SECONDS = 10.0
MANUAL_SECONDS = 30.0


@pytest.fixture
def announcer() -> RecordingAnnouncer:
    return RecordingAnnouncer()


@pytest.fixture
def kiosk(
    repo: SqlRepository,
    hasher: NationalIdHasher,
    clock: FakeClock,
    announcer: RecordingAnnouncer,
    hospital: dict[str, int],
) -> KioskController:
    routing = RoutingService(repo, hasher, clock=clock.datetime)
    return KioskController(
        routing,
        announcer,
        Messages("tr"),
        result_seconds=RESULT_SECONDS,
        manual_timeout_seconds=MANUAL_SECONDS,
        clock=clock.monotonic,
    )


def confirmed(patient_id: int) -> Observation:
    return Observation(Verdict.CONFIRMED, patient_id)


def test_starts_idle(kiosk: KioskController) -> None:
    assert kiosk.state.screen is Screen.IDLE


def test_scanning_then_back_to_idle(kiosk: KioskController) -> None:
    kiosk.on_observation(Observation(Verdict.PENDING))
    assert kiosk.state.screen is Screen.SCANNING
    kiosk.on_observation(Observation(Verdict.NOBODY))
    assert kiosk.state.screen is Screen.IDLE


def test_recognised_patient_is_routed_and_announced(
    kiosk: KioskController, hospital: dict[str, int], announcer: RecordingAnnouncer
) -> None:
    kiosk.on_observation(confirmed(hospital["ayse"]))
    assert kiosk.state.screen is Screen.ROUTE
    assert "A Blok" in describe(kiosk.state, kiosk.messages)
    assert "Ayşe D." in describe(kiosk.state, kiosk.messages)
    assert announcer.spoken == [
        "Merhaba Ayşe. Göz Hastalıkları, A blok, ikinci kat. Doktorunuz Doçent Doktor Elif Yıldırım."
    ]


def test_result_times_out_to_idle(kiosk: KioskController, hospital: dict[str, int], clock: FakeClock) -> None:
    kiosk.on_observation(confirmed(hospital["ayse"]))
    clock.advance(RESULT_SECONDS - 1)
    kiosk.tick()
    assert kiosk.state.screen is Screen.ROUTE
    clock.advance(1)
    kiosk.tick()
    assert kiosk.state.screen is Screen.IDLE


def test_camera_is_ignored_while_a_result_is_shown(kiosk: KioskController, hospital: dict[str, int]) -> None:
    kiosk.on_observation(confirmed(hospital["ayse"]))
    kiosk.on_observation(confirmed(hospital["mehmet"]))
    assert kiosk.state.result is not None
    assert kiosk.state.result.patient is not None
    assert kiosk.state.result.patient.first_name == "Ayşe"


def test_same_person_is_not_greeted_twice(
    kiosk: KioskController, hospital: dict[str, int], clock: FakeClock, announcer: RecordingAnnouncer
) -> None:
    kiosk.on_observation(confirmed(hospital["ayse"]))
    clock.advance(RESULT_SECONDS)
    kiosk.tick()
    kiosk.on_observation(confirmed(hospital["ayse"]))
    assert kiosk.state.screen is Screen.IDLE
    assert len(announcer.spoken) == 1
    clock.advance(2 * RESULT_SECONDS)
    kiosk.on_observation(confirmed(hospital["ayse"]))
    assert kiosk.state.screen is Screen.ROUTE


def test_patient_without_appointment(kiosk: KioskController, hospital: dict[str, int]) -> None:
    kiosk.on_observation(confirmed(hospital["mehmet"]))
    assert kiosk.state.screen is Screen.NO_APPOINTMENT


def test_unrecognised_offers_the_fallback(kiosk: KioskController, announcer: RecordingAnnouncer) -> None:
    kiosk.on_observation(Observation(Verdict.UNRECOGNISED))
    assert kiosk.state.screen is Screen.UNRECOGNISED
    assert announcer.spoken == ["Sizi tanıyamadık. TC kimlik numaranızla devam edebilirsiniz."]


@pytest.mark.parametrize(
    ("language", "floor", "spoken"),
    [("tr", "2", "ikinci kat"), ("tr", "0", "zemin kat"), ("tr", "-1", "eksi birinci kat"), ("tr", "14", "14. kat"),
     ("en", "2", "floor 2"), ("en", "0", "the ground floor")],
)  # fmt: skip
def test_floors_are_spoken_as_words(language: str, floor: str, spoken: str) -> None:
    assert Messages(language).spoken_floor(floor) == spoken  # type: ignore[arg-type]


def test_titles_are_expanded_for_speech() -> None:
    t = Messages("tr")
    assert t.speakable("Prof. Dr. Ali ve Dr. Can") == "Profesör Doktor Ali ve Doktor Can"
    assert t.speakable("Dr. Öğr. Üyesi Ece") == "Doktor Öğretim Üyesi Ece"


def test_match_for_a_deleted_patient_counts_as_unrecognised(kiosk: KioskController) -> None:
    kiosk.on_observation(confirmed(999))
    assert kiosk.state.screen is Screen.UNRECOGNISED


def type_id(kiosk: KioskController, number: str) -> None:
    kiosk.open_manual_entry()
    for digit in number:
        kiosk.press_digit(digit)
    kiosk.submit_manual_entry()


def test_manual_entry_routes_by_national_id(kiosk: KioskController) -> None:
    type_id(kiosk, AYSE_ID)
    assert kiosk.state.screen is Screen.ROUTE


def test_manual_entry_rejects_an_invalid_number(kiosk: KioskController) -> None:
    type_id(kiosk, "12345678901")
    assert kiosk.state.screen is Screen.MANUAL_ENTRY
    assert kiosk.state.error_key == "manual.invalid"
    assert kiosk.state.digits == ""


def test_manual_entry_does_not_reveal_registration(kiosk: KioskController) -> None:
    type_id(kiosk, MEHMET_ID)  # registered, no appointment
    registered = kiosk.state
    kiosk.open_manual_entry()
    type_id(kiosk, "10000000146")  # valid but unknown
    assert registered.screen is kiosk.state.screen is Screen.NO_APPOINTMENT
    assert registered.result == kiosk.state.result
    assert registered.result is not None
    assert registered.result.patient is None


def test_keypad_editing(kiosk: KioskController) -> None:
    kiosk.press_digit("1")  # ignored outside the keypad screen
    kiosk.open_manual_entry()
    for key in "123x":
        kiosk.press_digit(key)
    kiosk.delete_digit()
    assert kiosk.state.digits == "12"
    for _ in range(20):
        kiosk.press_digit("9")
    assert len(kiosk.state.digits) == 11


def test_keypad_times_out_and_can_be_cancelled(kiosk: KioskController, clock: FakeClock) -> None:
    kiosk.open_manual_entry()
    clock.advance(MANUAL_SECONDS - 1)
    kiosk.press_digit("1")  # activity extends the timeout
    clock.advance(MANUAL_SECONDS - 1)
    kiosk.tick()
    assert kiosk.state.screen is Screen.MANUAL_ENTRY
    kiosk.cancel_manual_entry()
    assert kiosk.state.screen is Screen.IDLE


def test_camera_failure_and_recovery(kiosk: KioskController, clock: FakeClock) -> None:
    kiosk.on_camera_error()
    assert kiosk.state.screen is Screen.CAMERA_ERROR
    type_id(kiosk, AYSE_ID)
    assert kiosk.state.screen is Screen.ROUTE
    kiosk.on_observation(Observation(Verdict.NOBODY))  # frames are arriving again
    clock.advance(RESULT_SECONDS)
    kiosk.tick()
    assert kiosk.state.screen is Screen.IDLE
    kiosk.on_camera_error()
    kiosk.on_observation(Observation(Verdict.PENDING))
    assert kiosk.state.screen is Screen.SCANNING


def test_returns_to_camera_error_screen_after_a_result(kiosk: KioskController, clock: FakeClock) -> None:
    kiosk.on_camera_error()
    type_id(kiosk, AYSE_ID)
    clock.advance(RESULT_SECONDS)
    kiosk.tick()
    assert kiosk.state.screen is Screen.CAMERA_ERROR


def test_version_changes_only_on_state_change(kiosk: KioskController) -> None:
    start = kiosk.version
    kiosk.on_observation(Observation(Verdict.NOBODY))
    assert kiosk.version == start
    kiosk.on_observation(Observation(Verdict.PENDING))
    assert kiosk.version == start + 1


def test_languages_have_the_same_messages() -> None:
    assert catalogue_keys("tr") == catalogue_keys("en")


@pytest.mark.parametrize("screen", list(Screen))
def test_every_screen_can_be_described(screen: Screen) -> None:
    from hasta_yonlendirme.kiosk.controller import ViewState

    assert describe(ViewState(screen), Messages("en"))
