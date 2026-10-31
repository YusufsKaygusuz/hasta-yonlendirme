"""From camera frames to a confident decision about who is standing at the kiosk."""

from __future__ import annotations

import enum
from collections import deque
from dataclasses import dataclass

from hasta_yonlendirme.recognition.base import FaceEncoder, Frame
from hasta_yonlendirme.recognition.matcher import FaceMatcher, MatchDecision, MatchResult


class Verdict(str, enum.Enum):
    NOBODY = "nobody"
    """No usable face in view."""
    PENDING = "pending"
    """A face is in view but not enough frames agree yet."""
    CONFIRMED = "confirmed"
    UNRECOGNISED = "unrecognised"
    """A face stayed in view but never matched anyone."""


@dataclass(frozen=True, slots=True)
class Observation:
    verdict: Verdict
    patient_id: int | None = None


class Recognizer:
    """Runs the encoder on a frame and matches the person nearest to the kiosk.

    Only the largest face counts: the person standing in front of the screen,
    not someone walking past in the background.
    """

    def __init__(self, encoder: FaceEncoder, matcher: FaceMatcher, min_face_size: int = 60) -> None:
        self.encoder = encoder
        self.matcher = matcher
        self.min_face_size = min_face_size

    def process(self, frame: Frame) -> MatchResult | None:
        faces = [f for f in self.encoder.encode(frame) if f.size >= self.min_face_size]
        if not faces:
            return None
        nearest = max(faces, key=lambda f: f.area)
        return self.matcher.match(nearest.encoding)


class VoteConfirmer:
    """Accepts a patient only after several consecutive frames agree.

    A single lucky frame can match the wrong person; requiring agreement across
    ``confirm_frames`` frames makes a wrong route much less likely at the cost of
    a fraction of a second. After ``give_up_frames`` frames with a face but no
    agreement, the person is reported as unrecognised so they can use the fallback.
    """

    def __init__(self, confirm_frames: int = 3, give_up_frames: int = 15) -> None:
        if confirm_frames < 1 or give_up_frames < confirm_frames:
            raise ValueError("Need 1 <= confirm_frames <= give_up_frames")
        self.confirm_frames = confirm_frames
        self.give_up_frames = give_up_frames
        self._recent: deque[int | None] = deque(maxlen=confirm_frames)
        self._attempts = 0

    def reset(self) -> None:
        self._recent.clear()
        self._attempts = 0

    def feed(self, result: MatchResult | None) -> Observation:
        if result is None:
            self.reset()
            return Observation(Verdict.NOBODY)

        self._attempts += 1
        self._recent.append(result.patient_id if result.decision is MatchDecision.MATCH else None)
        first = self._recent[0]
        if first is not None and len(self._recent) == self.confirm_frames and all(pid == first for pid in self._recent):
            self.reset()
            return Observation(Verdict.CONFIRMED, first)
        if self._attempts >= self.give_up_frames:
            self.reset()
            return Observation(Verdict.UNRECOGNISED)
        return Observation(Verdict.PENDING)
