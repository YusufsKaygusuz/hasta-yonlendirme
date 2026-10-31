"""Every kiosk screen must fit in its window, in both languages and at common screen sizes.

Needs a display; skipped where Tk cannot open a window (for example in CI without X).
"""

from __future__ import annotations

import queue
import tkinter as tk
from collections.abc import Iterator

import pytest

from hasta_yonlendirme.i18n import Messages
from hasta_yonlendirme.identity import NationalIdHasher
from hasta_yonlendirme.kiosk.controller import KioskController, Screen, ViewState
from hasta_yonlendirme.kiosk.tk_ui import TkKiosk, scale_for
from hasta_yonlendirme.recognition.pipeline import Observation, Verdict
from hasta_yonlendirme.routing import RoutingService
from hasta_yonlendirme.storage.sql import SqlRepository
from hasta_yonlendirme.storage.sqlite import SQLiteRepository

from .conftest import FakeClock, RecordingAnnouncer

SIZES = [(800, 480), (1024, 600), (1280, 800), (1920, 1080)]


def _display_available() -> bool:
    try:
        tk.Tk().destroy()
    except tk.TclError:
        return False
    return True


pytestmark = pytest.mark.skipif(not _display_available(), reason="no display for Tk")


def screens(controller: KioskController, patient_id: int) -> Iterator[tuple[str, ViewState]]:
    yield "idle", ViewState()
    yield "scanning", ViewState(Screen.SCANNING)
    yield "no_appointment", ViewState(Screen.NO_APPOINTMENT)
    yield "unrecognised", ViewState(Screen.UNRECOGNISED)
    yield "camera_error", ViewState(Screen.CAMERA_ERROR)
    yield "manual", ViewState(Screen.MANUAL_ENTRY, digits="1234567890", error_key="manual.invalid")
    controller.on_observation(Observation(Verdict.CONFIRMED, patient_id))
    assert controller.state.screen is Screen.ROUTE
    yield "route", controller.state


@pytest.mark.parametrize("language", ["tr", "en"])
def test_every_screen_fits(
    repo: SqlRepository, hasher: NationalIdHasher, clock: FakeClock, hospital: dict[str, int], language: str
) -> None:
    if not isinstance(repo, SQLiteRepository):
        pytest.skip("layout does not depend on the database")
    messages = Messages(language)  # type: ignore[arg-type]
    controller = KioskController(
        RoutingService(repo, hasher, clock=clock.datetime), RecordingAnnouncer(), messages, clock=clock.monotonic
    )
    ui = TkKiosk(controller, messages, queue.Queue(), None, fullscreen=False, hospital_name="Yalova Devlet Hastanesi")
    try:
        assert ui._scale == 1.0, "a window must not take its text size from the whole screen"
        problems = []
        for width, height in SIZES:
            ui._scale = scale_for(width, height)
            for name, state in screens(controller, hospital["ayse"]):
                ui._render(state)
                ui.root.update_idletasks()
                need_w, need_h = ui._body.winfo_reqwidth(), ui._body.winfo_reqheight()
                if need_w > width or need_h > height:
                    problems.append(f"{name} at {width}x{height} needs {need_w}x{need_h}")
            controller.cancel_manual_entry()
            clock.advance(3600)
            controller.tick()
        assert not problems, "\n".join(problems)
    finally:
        ui.root.destroy()


def test_scale_follows_the_window() -> None:
    assert scale_for(800, 480) == 1.0
    assert scale_for(1920, 1080) == pytest.approx(2.25)
    assert scale_for(400, 240) == 0.6
