"""
Simple test runner for Step 3 (no pytest required)
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from brains.cognitive.self_model.service.self_model import service_api as self_model_api
from brains.cognitive.self_review.service.self_review_brain import service_api as self_review_api
from brains.cognitive.self_dmn.service.self_dmn_brain import service_api as self_dmn_api
from brains.cognitive.motivation.service.motivation_brain import service_api as motivation_api


def test_self_model_describe_self():
    """Test DESCRIBE_SELF operation."""
    print("Testing self_model.DESCRIBE_SELF...")
    resp = self_model_api({
        "op": "DESCRIBE_SELF",
        "payload": {"mode": "short"}
    })
    assert resp["ok"] is True, "DESCRIBE_SELF failed"
    assert "identity" in resp["payload"], "Missing identity"
    assert "capabilities" in resp["payload"], "Missing capabilities"
    assert "limitations" in resp["payload"], "Missing limitations"
    print("  ✓ DESCRIBE_SELF works")


def test_self_model_capabilities():
    """Test GET_CAPABILITIES operation."""
    print("Testing self_model.GET_CAPABILITIES...")
    resp = self_model_api({"op": "GET_CAPABILITIES"})
    assert resp["ok"] is True, "GET_CAPABILITIES failed"
    capabilities = resp["payload"]["capabilities"]
    assert isinstance(capabilities, list), "Capabilities should be a list"
    assert "reasoning" in capabilities, "Should include reasoning capability"
    print(f"  ✓ GET_CAPABILITIES works ({len(capabilities)} capabilities found)")


def test_self_model_limitations():
    """Test GET_LIMITATIONS operation."""
    print("Testing self_model.GET_LIMITATIONS...")
    resp = self_model_api({"op": "GET_LIMITATIONS"})
    assert resp["ok"] is True, "GET_LIMITATIONS failed"
    limitations = resp["payload"]["limitations"]
    assert isinstance(limitations, list), "Limitations should be a list"
    assert "no internet access" in limitations, "Should include no internet limitation"
    print(f"  ✓ GET_LIMITATIONS works ({len(limitations)} limitations found)")


def test_self_review_good_answer():
    """Test REVIEW_TURN with good answer."""
    print("Testing self_review.REVIEW_TURN (good answer)...")
    resp = self_review_api({
        "op": "REVIEW_TURN",
        "payload": {
            "query": "What is 2+2?",
            "plan": {"steps": ["Calculate"]},
            "thoughts": [{"content": "2+2 equals 4"}],
            "answer": "2 + 2 equals 4.",
            "metadata": {
                "confidences": {"final": 0.95, "reasoning": 0.9},
                "used_memories": [],
                "intents": ["question"]
            }
        }
    })
    assert resp["ok"] is True, "REVIEW_TURN failed"
    assert resp["payload"]["verdict"] == "ok", "Should accept good answer"
    assert resp["payload"]["recommended_action"] == "accept", "Should recommend accept"
    print("  ✓ REVIEW_TURN accepts good answer")


def test_self_review_bad_answer():
    """Test REVIEW_TURN with bad answer."""
    print("Testing self_review.REVIEW_TURN (bad answer)...")
    resp = self_review_api({
        "op": "REVIEW_TURN",
        "payload": {
            "query": "Explain quantum mechanics",
            "plan": {"steps": []},
            "thoughts": [],
            "answer": "",
            "metadata": {
                "confidences": {"final": 0.2, "reasoning": 0.2},
                "used_memories": [],
                "intents": ["question"]
            }
        }
    })
    assert resp["ok"] is True, "REVIEW_TURN failed"
    assert resp["payload"]["verdict"] == "major_issue", "Should flag major issue"
    assert resp["payload"]["recommended_action"] in ["revise", "ask_clarification"], "Should recommend action"
    print(f"  ✓ REVIEW_TURN flags bad answer (verdict: {resp['payload']['verdict']})")


def test_self_dmn_run_idle_cycle():
    """Test RUN_IDLE_CYCLE operation."""
    print("Testing self_dmn.RUN_IDLE_CYCLE...")
    resp = self_dmn_api({
        "op": "RUN_IDLE_CYCLE",
        "payload": {
            "system_history": [],
            "recent_issues": [
                {"severity": "major"},
                {"severity": "major"},
                {"severity": "major"},
                {"severity": "major"}
            ],
            "motivation_state": {}
        }
    })
    assert resp["ok"] is True, "RUN_IDLE_CYCLE failed"
    assert "insights" in resp["payload"], "Missing insights"
    assert "actions" in resp["payload"], "Missing actions"
    print(f"  ✓ RUN_IDLE_CYCLE works ({len(resp['payload']['insights'])} insights, {len(resp['payload']['actions'])} actions)")


def test_self_dmn_reflect_on_error():
    """Test REFLECT_ON_ERROR operation."""
    print("Testing self_dmn.REFLECT_ON_ERROR...")
    resp = self_dmn_api({
        "op": "REFLECT_ON_ERROR",
        "payload": {
            "error_context": {
                "verdict": "major_issue",
                "error_type": "LOW_CONFIDENCE",
                "issues": [{"code": "LOW_CONFIDENCE"}],
                "query": "test"
            },
            "turn_history": []
        }
    })
    assert resp["ok"] is True, "REFLECT_ON_ERROR failed"
    assert len(resp["payload"]["insights"]) > 0, "Should produce insights"
    print("  ✓ REFLECT_ON_ERROR produces insights")


def test_motivation_get_state():
    """Test GET_STATE operation."""
    print("Testing motivation.GET_STATE...")
    resp = motivation_api({"op": "GET_STATE"})
    assert resp["ok"] is True, "GET_STATE failed"
    state = resp["payload"]
    assert "helpfulness" in state, "Missing helpfulness"
    assert "truthfulness" in state, "Missing truthfulness"
    assert "curiosity" in state, "Missing curiosity"
    assert "self_improvement" in state, "Missing self_improvement"
    print("  ✓ GET_STATE works")


def test_motivation_adjust_state():
    """Test ADJUST_STATE operation."""
    print("Testing motivation.ADJUST_STATE...")
    resp = motivation_api({
        "op": "ADJUST_STATE",
        "payload": {
            "deltas": {"helpfulness": 0.05}
        }
    })
    assert resp["ok"] is True, "ADJUST_STATE failed"
    state = resp["payload"]
    assert "helpfulness" in state, "Missing helpfulness in adjusted state"
    print("  ✓ ADJUST_STATE works")


def test_motivation_evaluate_query():
    """Test EVALUATE_QUERY operation."""
    print("Testing motivation.EVALUATE_QUERY...")
    resp = motivation_api({
        "op": "EVALUATE_QUERY",
        "payload": {
            "query": "why does the sky appear blue?",
            "context": {}
        }
    })
    assert resp["ok"] is True, "EVALUATE_QUERY failed"
    assert "weights" in resp["payload"], "Missing weights"
    assert "base_state" in resp["payload"], "Missing base_state"
    weights = resp["payload"]["weights"]
    base = resp["payload"]["base_state"]
    # "why" questions should boost curiosity
    assert weights["curiosity"] > base["curiosity"], "Why questions should boost curiosity"
    print("  ✓ EVALUATE_QUERY works and boosts curiosity for 'why' questions")


def main():
    """Run all tests."""
    tests = [
        test_self_model_describe_self,
        test_self_model_capabilities,
        test_self_model_limitations,
        test_self_review_good_answer,
        test_self_review_bad_answer,
        test_self_dmn_run_idle_cycle,
        test_self_dmn_reflect_on_error,
        test_motivation_get_state,
        test_motivation_adjust_state,
        test_motivation_evaluate_query,
    ]

    print("=" * 60)
    print("Running Step 3 Self-Systems Tests")
    print("=" * 60)
    print()

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  ✗ FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ ERROR: {e}")
            failed += 1

    print()
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
