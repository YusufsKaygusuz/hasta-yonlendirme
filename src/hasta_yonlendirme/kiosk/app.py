"""Wiring: builds every component of the kiosk from a :class:`Config`."""

from __future__ import annotations

import logging
import queue
from collections.abc import Callable
from datetime import timedelta
from functools import partial

from hasta_yonlendirme.announcer import make_announcer
from hasta_yonlendirme.camera import open_camera
from hasta_yonlendirme.config import Config
from hasta_yonlendirme.i18n import Messages
from hasta_yonlendirme.identity import NationalIdHasher
from hasta_yonlendirme.kiosk.controller import KioskController
from hasta_yonlendirme.kiosk.worker import Event, RecognitionWorker
from hasta_yonlendirme.recognition.base import Encoding
from hasta_yonlendirme.recognition.matcher import FaceGallery, FaceMatcher
from hasta_yonlendirme.recognition.pipeline import Recognizer, VoteConfirmer
from hasta_yonlendirme.routing import RoutingService
from hasta_yonlendirme.storage import open_repository

log = logging.getLogger(__name__)


def run_kiosk(config: Config, *, headless: bool = False) -> None:
    repository = open_repository(config.database)
    hasher = NationalIdHasher.from_env(config.privacy.pepper_env)
    messages = Messages(config.kiosk.language)
    routing = RoutingService(
        repository,
        hasher,
        early=timedelta(minutes=config.routing.early_arrival_minutes),
        late=timedelta(minutes=config.routing.late_arrival_minutes),
    )
    announcer = make_announcer(config.audio.enabled, config.audio.voice or config.kiosk.language, config.audio.speed)
    controller = KioskController(
        routing,
        announcer,
        messages,
        result_seconds=config.kiosk.result_seconds,
        manual_timeout_seconds=config.kiosk.manual_entry_timeout_seconds,
    )
    events: queue.Queue[Event] = queue.Queue()
    worker = _build_worker(config, repository.load_encodings, events)
    if worker is None:
        controller.on_camera_error()  # face recognition unavailable: ID-number mode only

    try:
        if headless:
            from hasta_yonlendirme.kiosk.console_ui import ConsoleKiosk

            ConsoleKiosk(controller, messages, events, worker).run()
        else:
            from hasta_yonlendirme.kiosk.tk_ui import TkKiosk

            TkKiosk(
                controller,
                messages,
                events,
                worker,
                fullscreen=config.kiosk.fullscreen,
                hospital_name=config.kiosk.hospital_name,
            ).run()
    finally:
        repository.close()


def _build_worker(
    config: Config,
    load_gallery: Callable[[], list[tuple[int, Encoding]]],
    events: queue.Queue[Event],
) -> RecognitionWorker | None:
    """Create the recognition thread, or None when the face library is missing.

    The kiosk stays useful without recognition: patients can still find their way
    with their ID number, so a missing library degrades the service instead of stopping it.
    """
    from hasta_yonlendirme.recognition.dlib_backend import DlibFaceEncoder, FaceLibraryMissingError

    try:
        encoder = DlibFaceEncoder(config.recognition.detection_model, config.recognition.downscale)
    except FaceLibraryMissingError:
        log.warning("Face recognition library missing; running in ID-number-only mode")
        return None
    gallery = FaceGallery(load_gallery())
    log.info("Loaded %d face encodings for %d patients", len(gallery), gallery.patient_count)
    r = config.recognition
    matcher = FaceMatcher(gallery, r.tolerance, r.ambiguity_margin)
    return RecognitionWorker(
        partial(open_camera, config.camera),
        Recognizer(encoder, matcher, r.min_face_size),
        VoteConfirmer(r.confirm_frames),
        events,
        load_gallery=load_gallery,
        gallery_refresh_seconds=r.gallery_refresh_seconds,
    )
