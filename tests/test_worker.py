from __future__ import annotations

import queue
from pathlib import Path

import numpy as np
import pytest

from hasta_yonlendirme.announcer import EspeakAnnouncer, MacSayAnnouncer, SilentAnnouncer, make_announcer
from hasta_yonlendirme.camera import CameraError
from hasta_yonlendirme.kiosk.worker import CameraFailure, Event, RecognitionWorker
from hasta_yonlendirme.recognition import DetectedFace, FaceGallery, FaceMatcher, Recognizer, Verdict, VoteConfirmer

from .conftest import ScriptedEncoder, unit_vector

FRAME = np.zeros((4, 4, 3), dtype=np.uint8)


class FakeCamera:
    def __init__(self, frames: int, worker_ref: list[RecognitionWorker]) -> None:
        self.remaining = frames
        self.worker_ref = worker_ref
        self.closed = False

    def read(self) -> np.ndarray:
        if self.remaining == 0:
            self.worker_ref[0].stop()
            raise CameraError("end of test footage")
        self.remaining -= 1
        return FRAME

    def close(self) -> None:
        self.closed = True


def make_worker(
    faces: list[DetectedFace], frames: int, **kwargs: object
) -> tuple[RecognitionWorker, queue.Queue[Event], list[FakeCamera]]:
    events: queue.Queue[Event] = queue.Queue()
    ref: list[RecognitionWorker] = []
    cameras: list[FakeCamera] = []

    def open_camera() -> FakeCamera:
        cameras.append(FakeCamera(frames, ref))
        return cameras[-1]

    gallery = FaceGallery([(1, unit_vector(0))])
    worker = RecognitionWorker(
        open_camera,
        Recognizer(ScriptedEncoder(faces), FaceMatcher(gallery), min_face_size=10),
        VoteConfirmer(confirm_frames=2),
        events,
        idle_delay_seconds=0,
        retry_seconds=0,
        **kwargs,  # type: ignore[arg-type]
    )
    ref.append(worker)
    return worker, events, cameras


def drain(events: queue.Queue[Event]) -> list[Event]:
    out = []
    while not events.empty():
        out.append(events.get_nowait())
    return out


def test_worker_reports_changes_and_final_verdicts() -> None:
    worker, events, cameras = make_worker([DetectedFace(0, 50, 50, 0, unit_vector(0))], frames=4)
    worker.run()  # synchronously, in this thread
    published = drain(events)
    verdicts = [e.verdict for e in published if not isinstance(e, CameraFailure)]
    # pending, confirmed, pending, confirmed: repeated "pending" frames are not re-sent
    assert verdicts == [Verdict.PENDING, Verdict.CONFIRMED, Verdict.PENDING, Verdict.CONFIRMED]
    assert isinstance(published[-1], CameraFailure)
    assert cameras[0].closed


def test_worker_reports_nobody_once() -> None:
    worker, events, _ = make_worker([], frames=5)
    worker.run()
    verdicts = [e.verdict for e in drain(events) if not isinstance(e, CameraFailure)]
    assert verdicts == [Verdict.NOBODY]


def test_worker_retries_a_camera_that_will_not_open() -> None:
    events: queue.Queue[Event] = queue.Queue()
    attempts = []

    def broken() -> FakeCamera:
        attempts.append(1)
        if len(attempts) == 2:
            worker.stop()
        raise CameraError("no camera")

    worker = RecognitionWorker(
        broken,
        Recognizer(ScriptedEncoder(), FaceMatcher(FaceGallery())),
        VoteConfirmer(),
        events,
        retry_seconds=0,
    )
    worker.run()
    assert len(attempts) == 2
    assert all(isinstance(e, CameraFailure) for e in drain(events))


def test_worker_refreshes_the_gallery() -> None:
    loads = []

    def load() -> list[tuple[int, np.ndarray]]:
        loads.append(1)
        return [(7, unit_vector(3))]

    worker, _, _ = make_worker([], frames=2, load_gallery=load, gallery_refresh_seconds=0)
    worker.run()
    assert loads
    assert worker.recognizer.matcher.gallery.patient_count == 1


def test_worker_keeps_the_old_gallery_when_reload_fails() -> None:
    def load() -> list[tuple[int, np.ndarray]]:
        raise ConnectionError("database down")

    worker, _, _ = make_worker([], frames=2, load_gallery=load, gallery_refresh_seconds=0)
    old = worker.recognizer.matcher
    worker.run()
    assert worker.recognizer.matcher is old


def test_paused_worker_does_not_publish() -> None:
    worker, events, _ = make_worker([DetectedFace(0, 50, 50, 0, unit_vector(0))], frames=3)
    worker.pause(True)
    worker.run()
    assert all(isinstance(e, CameraFailure) for e in drain(events))


def test_announcer_falls_back_to_silence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda _name: None)
    assert isinstance(make_announcer(True, "tr", 150), SilentAnnouncer)
    assert isinstance(make_announcer(False, "tr", 150), SilentAnnouncer)
    with pytest.raises(FileNotFoundError):
        EspeakAnnouncer("tr")


def test_announcer_prefers_espeak_then_macos(monkeypatch: pytest.MonkeyPatch) -> None:
    available = {"say": "/usr/bin/say"}
    monkeypatch.setattr("shutil.which", available.get)
    monkeypatch.setattr("sys.platform", "darwin")
    mac = make_announcer(True, "tr", 160)
    assert isinstance(mac, MacSayAnnouncer)
    assert mac._command("Merhaba") == ["/usr/bin/say", "-v", "Yelda", "-r", "160", "Merhaba"]
    available["espeak-ng"] = "/usr/bin/espeak-ng"
    espeak = make_announcer(True, "tr", 160)
    assert isinstance(espeak, EspeakAnnouncer)
    assert espeak._command("Merhaba") == ["/usr/bin/espeak-ng", "-v", "tr", "-s", "160", "Merhaba"]


def test_speech_does_not_block_and_interrupts_itself(tmp_path: Path) -> None:
    script = tmp_path / "fake-tts"
    script.write_text("#!/bin/sh\nsleep 5\n")
    script.chmod(0o755)
    announcer = EspeakAnnouncer("tr", executable=str(script))
    announcer.say("bir")
    first = announcer._process
    announcer.say("iki")
    assert first is not None
    assert first.wait(timeout=2) != 0  # terminated by the second announcement
    assert announcer._process is not None
    announcer._process.terminate()
