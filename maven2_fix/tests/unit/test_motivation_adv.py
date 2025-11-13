"""
Unit tests for the motivation brain's SCORE_DRIVE operation.

The SCORE_DRIVE operation produces a scalar motivation drive based on
success, affect and contradictions.  These tests ensure the returned
drive is clamped to [0,1] and increases or decreases as expected when
the input metrics vary.
"""

from brains.cognitive.motivation.service.motivation_brain import service_api as motivation_api


def test_score_drive_increases_with_success_and_affect():
    # Higher success and affect should produce a higher drive value
    d_low = motivation_api({"op": "SCORE_DRIVE", "payload": {"context": {"success_count": 0, "affect_score": 0.0, "contradictions": 0}}})["payload"]["drive"]
    d_med = motivation_api({"op": "SCORE_DRIVE", "payload": {"context": {"success_count": 1, "affect_score": 0.5, "contradictions": 0}}})["payload"]["drive"]
    d_high = motivation_api({"op": "SCORE_DRIVE", "payload": {"context": {"success_count": 2, "affect_score": 1.0, "contradictions": 0}}})["payload"]["drive"]
    assert 0.0 <= d_low <= d_med <= d_high <= 1.0


def test_score_drive_decreases_with_contradictions():
    base = motivation_api({"op": "SCORE_DRIVE", "payload": {"context": {"success_count": 1, "affect_score": 1.0, "contradictions": 0}}})["payload"]["drive"]
    lower = motivation_api({"op": "SCORE_DRIVE", "payload": {"context": {"success_count": 1, "affect_score": 1.0, "contradictions": 2}}})["payload"]["drive"]
    assert lower <= base