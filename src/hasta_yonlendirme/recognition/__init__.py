"""Face detection, encoding and matching.

The pipeline is split so that only :mod:`.dlib_backend` touches the heavy
``face_recognition`` library; matching and confirmation are pure NumPy and are
fully covered by tests that run without a camera or dlib.
"""

from hasta_yonlendirme.recognition.base import DetectedFace, FaceEncoder
from hasta_yonlendirme.recognition.matcher import FaceGallery, FaceMatcher, MatchDecision, MatchResult
from hasta_yonlendirme.recognition.pipeline import Observation, Recognizer, Verdict, VoteConfirmer

__all__ = [
    "DetectedFace",
    "FaceEncoder",
    "FaceGallery",
    "FaceMatcher",
    "MatchDecision",
    "MatchResult",
    "Observation",
    "Recognizer",
    "Verdict",
    "VoteConfirmer",
]
