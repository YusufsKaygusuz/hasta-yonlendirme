"""Background thread that reads the camera and turns frames into recognition verdicts.

Face detection takes a noticeable fraction of a second on a Raspberry Pi, so it runs
off the UI thread. The worker only reports changes (and every final verdict) through
a queue, which the UI drains on its own schedule.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable

from hasta_yonlendirme.camera import Camera, CameraError
from hasta_yonlendirme.recognition.base import Encoding
from hasta_yonlendirme.recognition.matcher import FaceGallery, FaceMatcher
from hasta_yonlendirme.recognition.pipeline import Observation, Recognizer, Verdict, VoteConfirmer

log = logging.getLogger(__name__)


class CameraFailure:
    """Queue message: the camera stopped delivering frames."""


Event = Observation | CameraFailure


class RecognitionWorker(threading.Thread):
    def __init__(
        self,
        open_camera: Callable[[], Camera],
        recognizer: Recognizer,
        confirmer: VoteConfirmer,
        events: queue.Queue[Event],
        *,
        load_gallery: Callable[[], list[tuple[int, Encoding]]] | None = None,
        gallery_refresh_seconds: float = 300.0,
        idle_delay_seconds: float = 0.05,
        retry_seconds: float = 3.0,
    ) -> None:
        super().__init__(name="recognition", daemon=True)
        self._open_camera = open_camera
        self.recognizer = recognizer
        self.confirmer = confirmer
        self.events = events
        self._load_gallery = load_gallery
        self._refresh = gallery_refresh_seconds
        self._idle_delay = idle_delay_seconds
        self._retry = retry_seconds
        self._stop_event = threading.Event()
        self._paused = threading.Event()
        self._last_verdict: Verdict | None = None
        self._next_refresh = time.monotonic() + gallery_refresh_seconds

    def stop(self) -> None:
        self._stop_event.set()

    def pause(self, paused: bool) -> None:
        """Skip processing while the screen is busy (keypad, result) to save CPU."""
        if paused:
            self._paused.set()
        else:
            self._paused.clear()

    def run(self) -> None:
        camera: Camera | None = None
        while not self._stop_event.is_set():
            if camera is None:
                camera = self._try_open()
                if camera is None:
                    continue
            try:
                # Read even while paused, so processing resumes on a current frame.
                frame = camera.read()
            except CameraError as exc:
                log.warning("%s; reopening the camera", exc)
                camera.close()
                camera = None
                self.events.put(CameraFailure())
                continue
            if self._paused.is_set():
                self.confirmer.reset()
                self._last_verdict = None
                self._stop_event.wait(0.1)
                continue
            self._maybe_refresh_gallery()
            observation = self.confirmer.feed(self.recognizer.process(frame))
            self._publish(observation)
            if observation.verdict is Verdict.NOBODY:
                self._stop_event.wait(self._idle_delay)
        if camera is not None:
            camera.close()

    def _try_open(self) -> Camera | None:
        try:
            return self._open_camera()
        except CameraError as exc:
            log.warning("%s; retrying in %.0f s", exc, self._retry)
            self.events.put(CameraFailure())
            self._stop_event.wait(self._retry)
            return None

    def _publish(self, observation: Observation) -> None:
        final = observation.verdict in (Verdict.CONFIRMED, Verdict.UNRECOGNISED)
        if final or observation.verdict is not self._last_verdict:
            self.events.put(observation)
        self._last_verdict = None if final else observation.verdict

    def _maybe_refresh_gallery(self) -> None:
        """Pick up patients enrolled while the kiosk is running."""
        if self._load_gallery is None or time.monotonic() < self._next_refresh:
            return
        self._next_refresh = time.monotonic() + self._refresh
        try:
            gallery = FaceGallery(self._load_gallery())
        except Exception:
            log.exception("Could not refresh the face gallery; keeping the current one")
            return
        old = self.recognizer.matcher
        self.recognizer.matcher = FaceMatcher(gallery, old.tolerance, old.ambiguity_margin)
        log.info("Face gallery refreshed: %d patients", gallery.patient_count)
