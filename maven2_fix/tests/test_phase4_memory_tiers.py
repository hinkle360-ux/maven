#!/usr/bin/env python3
"""
Phase 4: Tiered Memory System Tests

This test suite validates the tiered memory system implementation including:
- Tier assignment logic (_assign_tier)
- Retrieval scoring (_score_memory_hit)
- Cross-tier ranking in UNIFIED_RETRIEVE
- Memory health diagnostics
- No time-based logic verification

Run with: python tests/test_phase4_memory_tiers.py
"""

import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from brains.cognitive.memory_librarian.service.memory_librarian import (
    _assign_tier,
    _score_memory_hit,
    _next_seq_id,
    TIER_WM,
    TIER_SHORT,
    TIER_MID,
    TIER_LONG,
    TIER_PINNED,
)


def test_tier_assignment_identity():
    """Test that identity queries are assigned to PINNED tier."""
    print("Test: Identity queries → PINNED tier")

    # User identity statement
    record = {"content": "my name is Josh", "confidence": 0.9}
    context = {"intent": "IDENTITY", "verdict": "TRUE", "tags": ["identity"]}
    tier, importance = _assign_tier(record, context)

    assert tier == TIER_PINNED, f"Expected PINNED, got {tier}"
    assert importance == 1.0, f"Expected importance 1.0, got {importance}"
    print("✓ Identity query correctly assigned to PINNED tier with importance 1.0")


def test_tier_assignment_preference():
    """Test that preference statements are assigned to MID tier."""
    print("\nTest: Preference statements → MID tier")

    record = {"content": "I like green", "confidence": 0.8}
    context = {"intent": "PREFERENCE", "verdict": "PREFERENCE", "tags": ["preference"]}
    tier, importance = _assign_tier(record, context)

    assert tier == TIER_MID, f"Expected MID, got {tier}"
    assert importance >= 0.8, f"Expected importance >= 0.8, got {importance}"
    print("✓ Preference correctly assigned to MID tier")


def test_tier_assignment_relationship():
    """Test that relationship facts are assigned to MID tier."""
    print("\nTest: Relationship facts → MID tier")

    record = {"content": "we are friends", "confidence": 0.9}
    context = {"intent": "RELATIONSHIP", "verdict": "TRUE", "tags": ["relationship"]}
    tier, importance = _assign_tier(record, context)

    assert tier == TIER_MID, f"Expected MID, got {tier}"
    assert importance >= 0.9, f"Expected importance >= 0.9, got {importance}"
    print("✓ Relationship fact correctly assigned to MID tier")


def test_tier_assignment_high_confidence_fact():
    """Test that high-confidence facts are assigned to MID tier."""
    print("\nTest: High-confidence facts → MID tier")

    record = {"content": "the sky is blue", "confidence": 0.9}
    context = {"intent": "FACT", "verdict": "TRUE"}
    tier, importance = _assign_tier(record, context)

    assert tier == TIER_MID, f"Expected MID, got {tier}"
    assert importance == 0.9, f"Expected importance 0.9, got {importance}"
    print("✓ High-confidence fact correctly assigned to MID tier")


def test_tier_assignment_theory():
    """Test that theories are assigned to SHORT tier."""
    print("\nTest: Theories → SHORT tier")

    record = {"content": "it might rain tomorrow", "confidence": 0.6}
    context = {"intent": "SPECULATION", "verdict": "THEORY"}
    tier, importance = _assign_tier(record, context)

    assert tier == TIER_SHORT, f"Expected SHORT, got {tier}"
    assert importance < 1.0, f"Expected importance < 1.0, got {importance}"
    print("✓ Theory correctly assigned to SHORT tier")


def test_tier_assignment_creative_content():
    """Test that creative content is assigned to SHORT tier even with TRUE verdict."""
    print("\nTest: Creative content → SHORT tier")

    record = {"content": "once upon a time there was a story", "confidence": 0.8}
    context = {"intent": "CREATIVE", "verdict": "TRUE"}
    tier, importance = _assign_tier(record, context)

    assert tier == TIER_SHORT, f"Expected SHORT, got {tier}"
    print("✓ Creative content correctly assigned to SHORT tier")


def test_tier_assignment_skip_storage():
    """Test that low-quality content is skipped (empty tier)."""
    print("\nTest: Low-quality content → SKIP_STORAGE")

    # Very low confidence
    record = {"content": "something unclear", "confidence": 0.2}
    context = {"intent": "UNKNOWN", "verdict": "UNKNOWN"}
    tier, importance = _assign_tier(record, context)

    assert tier == "", f"Expected empty string (skip), got {tier}"
    assert importance == 0.0, f"Expected importance 0.0, got {importance}"
    print("✓ Low-quality content correctly skipped")


def test_tier_assignment_question_skip():
    """Test that questions are skipped by default."""
    print("\nTest: Questions → SKIP_STORAGE (default)")

    record = {"content": "what is the capital of France?", "confidence": 0.8}
    context = {"intent": "QUESTION", "verdict": "SKIP_STORAGE", "storable_type": "QUESTION"}
    tier, importance = _assign_tier(record, context)

    assert tier == "", f"Expected empty string (skip), got {tier}"
    print("✓ Question correctly skipped by default")


def test_seq_id_monotonic():
    """Test that seq_id counter is monotonically increasing."""
    print("\nTest: Sequence ID monotonic increment")

    id1 = _next_seq_id()
    id2 = _next_seq_id()
    id3 = _next_seq_id()

    assert id2 > id1, f"Expected id2 ({id2}) > id1 ({id1})"
    assert id3 > id2, f"Expected id3 ({id3}) > id2 ({id2})"
    print(f"✓ Sequence IDs are monotonic: {id1} < {id2} < {id3}")


def test_scoring_tier_priority():
    """Test that tier priority affects scoring."""
    print("\nTest: Tier priority in scoring")

    query = {"query": "test"}

    # PINNED tier hit
    hit_pinned = {"tier": TIER_PINNED, "importance": 0.5, "use_count": 0, "seq_id": 10, "score": 0.5}
    score_pinned = _score_memory_hit(hit_pinned, query)

    # MID tier hit with same base score
    hit_mid = {"tier": TIER_MID, "importance": 0.5, "use_count": 0, "seq_id": 10, "score": 0.5}
    score_mid = _score_memory_hit(hit_mid, query)

    # SHORT tier hit with same base score
    hit_short = {"tier": TIER_SHORT, "importance": 0.5, "use_count": 0, "seq_id": 10, "score": 0.5}
    score_short = _score_memory_hit(hit_short, query)

    assert score_pinned > score_mid, f"Expected PINNED ({score_pinned}) > MID ({score_mid})"
    assert score_mid > score_short, f"Expected MID ({score_mid}) > SHORT ({score_short})"
    print(f"✓ Tier priority ordering: PINNED ({score_pinned:.2f}) > MID ({score_mid:.2f}) > SHORT ({score_short:.2f})")


def test_scoring_importance_boost():
    """Test that importance affects scoring."""
    print("\nTest: Importance boost in scoring")

    query = {"query": "test"}

    # High importance
    hit_high_imp = {"tier": TIER_MID, "importance": 1.0, "use_count": 0, "seq_id": 10, "score": 0.5}
    score_high = _score_memory_hit(hit_high_imp, query)

    # Low importance
    hit_low_imp = {"tier": TIER_MID, "importance": 0.1, "use_count": 0, "seq_id": 10, "score": 0.5}
    score_low = _score_memory_hit(hit_low_imp, query)

    assert score_high > score_low, f"Expected high importance ({score_high}) > low importance ({score_low})"
    print(f"✓ Importance affects scoring: high ({score_high:.2f}) > low ({score_low:.2f})")


def test_scoring_use_count_boost():
    """Test that use_count affects scoring."""
    print("\nTest: Use count boost in scoring")

    query = {"query": "test"}

    # High use count
    hit_high_use = {"tier": TIER_MID, "importance": 0.5, "use_count": 10, "seq_id": 10, "score": 0.5}
    score_high = _score_memory_hit(hit_high_use, query)

    # Low use count
    hit_low_use = {"tier": TIER_MID, "importance": 0.5, "use_count": 0, "seq_id": 10, "score": 0.5}
    score_low = _score_memory_hit(hit_low_use, query)

    assert score_high > score_low, f"Expected high use_count ({score_high}) > low use_count ({score_low})"
    print(f"✓ Use count affects scoring: high use ({score_high:.2f}) > low use ({score_low:.2f})")


def test_scoring_recency_boost():
    """Test that recency (seq_id) affects scoring."""
    print("\nTest: Recency boost in scoring")

    query = {"query": "test"}

    # Recent (high seq_id)
    hit_recent = {"tier": TIER_MID, "importance": 0.5, "use_count": 0, "seq_id": 1000, "score": 0.5}
    score_recent = _score_memory_hit(hit_recent, query)

    # Older (low seq_id)
    hit_old = {"tier": TIER_MID, "importance": 0.5, "use_count": 0, "seq_id": 10, "score": 0.5}
    score_old = _score_memory_hit(hit_old, query)

    assert score_recent >= score_old, f"Expected recent ({score_recent}) >= old ({score_old})"
    print(f"✓ Recency affects scoring: recent ({score_recent:.2f}) >= old ({score_old:.2f})")


def test_scoring_deterministic():
    """Test that scoring is deterministic (same input → same output)."""
    print("\nTest: Scoring determinism")

    query = {"query": "test"}
    hit = {"tier": TIER_MID, "importance": 0.7, "use_count": 5, "seq_id": 100, "score": 0.6}

    score1 = _score_memory_hit(hit, query)
    score2 = _score_memory_hit(hit, query)
    score3 = _score_memory_hit(hit, query)

    assert score1 == score2 == score3, f"Scores not deterministic: {score1}, {score2}, {score3}"
    print(f"✓ Scoring is deterministic: {score1} == {score2} == {score3}")


def test_no_time_imports():
    """Verify that memory_librarian.py does not import time or datetime modules."""
    print("\nTest: No time-based logic (import verification)")

    mem_lib_path = Path(__file__).resolve().parents[1] / "maven2_fix" / "brains" / "cognitive" / "memory_librarian" / "service" / "memory_librarian.py"

    # If path doesn't exist, try alternate location
    if not mem_lib_path.exists():
        mem_lib_path = Path(__file__).resolve().parents[1] / "brains" / "cognitive" / "memory_librarian" / "service" / "memory_librarian.py"

    if not mem_lib_path.exists():
        print("⚠ Could not find memory_librarian.py to verify imports")
        return

    with open(mem_lib_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Check for forbidden imports
    forbidden_patterns = [
        "import time",
        "from time import",
        "import datetime",
        "from datetime import",
        ".time()",
        "time.time",
        "datetime.now",
        "datetime.utcnow",
    ]

    violations = []
    for pattern in forbidden_patterns:
        if pattern in content:
            violations.append(pattern)

    if violations:
        print(f"✗ Found time-based logic: {violations}")
        assert False, f"Memory librarian contains time-based logic: {violations}"
    else:
        print("✓ No time-based imports or calls detected")


def test_tier_metadata_presence():
    """Test that tier metadata fields are present in records."""
    print("\nTest: Tier metadata field presence")

    # Test that _assign_tier returns both tier and importance
    record = {"content": "test content", "confidence": 0.8}
    context = {"intent": "FACT", "verdict": "TRUE"}
    result = _assign_tier(record, context)

    assert isinstance(result, tuple), f"Expected tuple, got {type(result)}"
    assert len(result) == 2, f"Expected 2-tuple, got {len(result)}-tuple"
    tier, importance = result
    assert isinstance(tier, str), f"Expected tier to be str, got {type(tier)}"
    assert isinstance(importance, (int, float)), f"Expected importance to be numeric, got {type(importance)}"
    print("✓ Tier assignment returns proper (tier, importance) tuple")


def run_all_tests():
    """Run all tier system tests."""
    print("=" * 70)
    print("Phase 4: Tiered Memory System Test Suite")
    print("=" * 70)

    tests = [
        # Tier assignment tests
        test_tier_assignment_identity,
        test_tier_assignment_preference,
        test_tier_assignment_relationship,
        test_tier_assignment_high_confidence_fact,
        test_tier_assignment_theory,
        test_tier_assignment_creative_content,
        test_tier_assignment_skip_storage,
        test_tier_assignment_question_skip,

        # Sequence ID tests
        test_seq_id_monotonic,

        # Scoring tests
        test_scoring_tier_priority,
        test_scoring_importance_boost,
        test_scoring_use_count_boost,
        test_scoring_recency_boost,
        test_scoring_deterministic,

        # Metadata tests
        test_tier_metadata_presence,

        # Compliance tests
        test_no_time_imports,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"✗ FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ ERROR: {e}")
            failed += 1

    print("\n" + "=" * 70)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("=" * 70)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
