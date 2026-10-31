"""Matching a face signature against the registered patients.

A face is accepted only when it is both *close* to a patient (distance below the
tolerance) and *clearly closer* to that patient than to anyone else (ambiguity
margin). When either test fails the kiosk says "not recognised" and offers the
ID-number fallback, rather than guessing and sending someone to the wrong clinic.
"""

from __future__ import annotations

import enum
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from hasta_yonlendirme.recognition.base import Encoding


class MatchDecision(str, enum.Enum):
    MATCH = "match"
    UNKNOWN = "unknown"
    """Nobody in the gallery is close enough."""
    AMBIGUOUS = "ambiguous"
    """Two different patients are almost equally close."""


@dataclass(frozen=True, slots=True)
class MatchResult:
    decision: MatchDecision
    patient_id: int | None = None
    distance: float = float("inf")

    @property
    def is_match(self) -> bool:
        return self.decision is MatchDecision.MATCH


class FaceGallery:
    """All registered encodings as one matrix, so a lookup is a single vectorised step.

    A patient may have several encodings (photos taken at different times or angles);
    the closest one counts.
    """

    def __init__(self, entries: Iterable[tuple[int, Encoding]] = ()) -> None:
        ids: list[int] = []
        vectors: list[Encoding] = []
        for patient_id, encoding in entries:
            ids.append(patient_id)
            vectors.append(np.asarray(encoding, dtype=np.float64))
        if vectors and len({v.shape for v in vectors}) != 1:
            raise ValueError("All encodings in a gallery must have the same length")
        self._ids: npt.NDArray[np.int64] = np.asarray(ids, dtype=np.int64)
        self._matrix: npt.NDArray[np.float64] = np.vstack(vectors) if vectors else np.empty((0, 0), dtype=np.float64)

    def __len__(self) -> int:
        return int(self._ids.size)

    @property
    def patient_count(self) -> int:
        return int(np.unique(self._ids).size)

    def nearest_per_patient(self, encoding: Encoding) -> list[tuple[int, float]]:
        """Distance from ``encoding`` to each patient's closest sample, nearest first."""
        if not len(self):
            return []
        distances = np.linalg.norm(self._matrix - encoding, axis=1)
        best: dict[int, float] = {}
        for patient_id, distance in zip(self._ids.tolist(), distances.tolist(), strict=True):
            if distance < best.get(patient_id, float("inf")):
                best[patient_id] = distance
        return sorted(best.items(), key=lambda item: item[1])


class FaceMatcher:
    def __init__(self, gallery: FaceGallery, tolerance: float = 0.5, ambiguity_margin: float = 0.06) -> None:
        self.gallery = gallery
        self.tolerance = tolerance
        self.ambiguity_margin = ambiguity_margin

    def match(self, encoding: Encoding) -> MatchResult:
        ranked = self.gallery.nearest_per_patient(encoding)
        if not ranked:
            return MatchResult(MatchDecision.UNKNOWN)
        best_id, best = ranked[0]
        if best > self.tolerance:
            return MatchResult(MatchDecision.UNKNOWN, distance=best)
        if len(ranked) > 1 and ranked[1][1] - best < self.ambiguity_margin:
            return MatchResult(MatchDecision.AMBIGUOUS, distance=best)
        return MatchResult(MatchDecision.MATCH, patient_id=best_id, distance=best)
