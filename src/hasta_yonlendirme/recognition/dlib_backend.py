"""Face detection and encoding with the ``face_recognition`` library (dlib).

Imported lazily: the rest of the package, its tests and the ID-number fallback all
work on machines where dlib is not installed.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

import numpy as np

from hasta_yonlendirme.recognition.base import DetectedFace, Encoding, Frame


class FaceLibraryMissingError(RuntimeError):
    pass


def _import_face_recognition() -> Any:
    try:
        with warnings.catch_warnings():
            # face_recognition_models still uses the deprecated pkg_resources API.
            warnings.filterwarnings("ignore", message="pkg_resources is deprecated", category=UserWarning)
            import face_recognition
    except ImportError as exc:  # pragma: no cover - depends on the machine
        raise FaceLibraryMissingError(
            "Face recognition is not installed. Run: pip install 'hasta-yonlendirme[face]' "
            "(on a Raspberry Pi, follow docs/raspberry-pi.md first)."
        ) from exc
    return face_recognition


def _shrink(frame: Frame, factor: float) -> Frame:
    if factor >= 1.0:
        return frame
    try:
        import cv2
    except ImportError:
        step = max(1, round(1 / factor))
        return frame[::step, ::step]
    return np.asarray(cv2.resize(frame, (0, 0), fx=factor, fy=factor, interpolation=cv2.INTER_AREA))


class DlibFaceEncoder:
    """Detects faces and computes 128-value encodings.

    Frames are shrunk before detection: on a Raspberry Pi this is the single most
    effective speed-up, and the faces of people standing at a kiosk stay large
    enough to recognise.
    """

    def __init__(self, detection_model: str = "hog", downscale: float = 0.5, upsample: int = 1) -> None:
        self._fr = _import_face_recognition()
        self.detection_model = detection_model
        self.downscale = downscale
        self.upsample = upsample

    def encode(self, frame: Frame) -> list[DetectedFace]:
        small = _shrink(frame, self.downscale)
        rgb = np.ascontiguousarray(small[:, :, ::-1])  # BGR -> RGB; dlib needs contiguous memory
        boxes = self._fr.face_locations(rgb, number_of_times_to_upsample=self.upsample, model=self.detection_model)
        if not boxes:
            return []
        encodings = self._fr.face_encodings(rgb, known_face_locations=boxes)
        return [
            DetectedFace(top, right, bottom, left, np.asarray(enc, dtype=np.float64))
            for (top, right, bottom, left), enc in zip(boxes, encodings, strict=True)
        ]


class EnrollmentError(ValueError):
    pass


def encode_photo(path: Path, detection_model: str = "hog") -> Encoding:
    """Encoding of the single face in a registration photo.

    The photo itself is never stored; only this vector is. A photo with no face or
    with several faces is rejected, because guessing which face is the patient
    would register the wrong person.
    """
    fr = _import_face_recognition()
    image = fr.load_image_file(str(path))
    boxes = fr.face_locations(image, number_of_times_to_upsample=1, model=detection_model)
    if not boxes:
        raise EnrollmentError(f"No face found in {path.name}")
    if len(boxes) > 1:
        raise EnrollmentError(f"{len(boxes)} faces found in {path.name}; use a photo of the patient alone")
    (encoding,) = fr.face_encodings(image, known_face_locations=boxes, num_jitters=5)
    return np.asarray(encoding, dtype=np.float64)
