from __future__ import annotations

import numpy as np
import pytest

from hasta_yonlendirme.recognition import (
    DetectedFace,
    FaceGallery,
    FaceMatcher,
    MatchDecision,
    MatchResult,
    Recognizer,
    Verdict,
    VoteConfirmer,
)

from .conftest import ScriptedEncoder, unit_vector

FRAME = np.zeros((10, 10, 3), dtype=np.uint8)


def near(vector: np.ndarray, distance: float, axis: int = 127) -> np.ndarray:
    """A vector at exactly ``distance`` from ``vector`` (moving along an unused axis)."""
    out = vector.copy()
    out[axis] += distance
    return out


@pytest.fixture
def gallery() -> FaceGallery:
    # Patient 1 has two samples; the closest one counts.
    return FaceGallery([(1, unit_vector(0)), (1, unit_vector(2)), (2, unit_vector(1))])


def test_gallery_counts(gallery: FaceGallery) -> None:
    assert len(gallery) == 3
    assert gallery.patient_count == 2


def test_gallery_rejects_mixed_lengths() -> None:
    with pytest.raises(ValueError, match="same length"):
        FaceGallery([(1, np.zeros(128)), (2, np.zeros(64))])


def test_nearest_per_patient_uses_best_sample(gallery: FaceGallery) -> None:
    ranked = gallery.nearest_per_patient(near(unit_vector(2), 0.1))
    assert ranked[0][0] == 1
    assert ranked[0][1] == pytest.approx(0.1)
    assert [pid for pid, _ in ranked] == [1, 2]


def test_match_within_tolerance(gallery: FaceGallery) -> None:
    result = FaceMatcher(gallery, tolerance=0.5).match(near(unit_vector(0), 0.3))
    assert result == MatchResult(MatchDecision.MATCH, 1, pytest.approx(0.3))
    assert result.is_match


def test_unknown_beyond_tolerance(gallery: FaceGallery) -> None:
    result = FaceMatcher(gallery, tolerance=0.5).match(near(unit_vector(0), 0.55))
    assert result.decision is MatchDecision.UNKNOWN
    assert result.patient_id is None


def test_ambiguous_when_two_patients_are_equally_close() -> None:
    gallery = FaceGallery([(1, unit_vector(0)), (2, unit_vector(1))])
    probe = (unit_vector(0) + unit_vector(1)) / 2  # same distance from both
    result = FaceMatcher(gallery, tolerance=0.8, ambiguity_margin=0.05).match(probe)
    assert result.decision is MatchDecision.AMBIGUOUS


def test_empty_gallery_is_unknown() -> None:
    assert FaceMatcher(FaceGallery()).match(unit_vector(0)).decision is MatchDecision.UNKNOWN


def face(encoding: np.ndarray, size: int = 100) -> DetectedFace:
    return DetectedFace(0, size, size, 0, encoding)


def test_recognizer_picks_the_largest_face(gallery: FaceGallery) -> None:
    encoder = ScriptedEncoder([face(unit_vector(1), size=80), face(unit_vector(0), size=150)])
    result = Recognizer(encoder, FaceMatcher(gallery), min_face_size=60).process(FRAME)
    assert result is not None
    assert result.patient_id == 1


def test_recognizer_ignores_faces_that_are_too_small(gallery: FaceGallery) -> None:
    encoder = ScriptedEncoder([face(unit_vector(0), size=40)])
    assert Recognizer(encoder, FaceMatcher(gallery), min_face_size=60).process(FRAME) is None


def match(pid: int) -> MatchResult:
    return MatchResult(MatchDecision.MATCH, pid, 0.2)


UNKNOWN = MatchResult(MatchDecision.UNKNOWN)


def test_confirmer_needs_consecutive_agreement() -> None:
    confirmer = VoteConfirmer(confirm_frames=3)
    assert confirmer.feed(match(1)).verdict is Verdict.PENDING
    assert confirmer.feed(match(1)).verdict is Verdict.PENDING
    observation = confirmer.feed(match(1))
    assert observation.verdict is Verdict.CONFIRMED
    assert observation.patient_id == 1


def test_confirmer_is_not_fooled_by_one_odd_frame() -> None:
    confirmer = VoteConfirmer(confirm_frames=3)
    for result in (match(1), match(2), match(1)):
        assert confirmer.feed(result).verdict is Verdict.PENDING
    assert confirmer.feed(match(1)).verdict is Verdict.PENDING
    assert confirmer.feed(match(1)).verdict is Verdict.CONFIRMED


def test_confirmer_gives_up_on_a_stranger() -> None:
    confirmer = VoteConfirmer(confirm_frames=2, give_up_frames=4)
    verdicts = [confirmer.feed(UNKNOWN).verdict for _ in range(4)]
    assert verdicts == [Verdict.PENDING] * 3 + [Verdict.UNRECOGNISED]


def test_confirmer_resets_when_the_face_leaves() -> None:
    confirmer = VoteConfirmer(confirm_frames=2)
    confirmer.feed(match(1))
    assert confirmer.feed(None).verdict is Verdict.NOBODY
    assert confirmer.feed(match(1)).verdict is Verdict.PENDING


def test_confirmer_validates_arguments() -> None:
    with pytest.raises(ValueError, match="confirm_frames"):
        VoteConfirmer(confirm_frames=5, give_up_frames=3)
