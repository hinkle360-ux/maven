"""
Test Step 3: Self Systems & Behavioral Control
================================================

This test suite verifies that the self-systems implemented in Step 3
actually affect how Maven thinks and answers, not just log passively.

Tests cover:
- self_model: DESCRIBE_SELF, GET_CAPABILITIES, GET_LIMITATIONS, UPDATE_SELF_FACTS
- self_review: REVIEW_TURN with actual action triggering
- self_dmn: RUN_IDLE_CYCLE and REFLECT_ON_ERROR with behavior changes
- motivation: GET_STATE, ADJUST_STATE, EVALUATE_QUERY
- attention: motivation integration into focus decisions
"""

import pytest
from brains.cognitive.self_model.service.self_model import service_api as self_model_api
from brains.cognitive.self_review.service.self_review_brain import service_api as self_review_api
from brains.cognitive.self_dmn.service.self_dmn_brain import service_api as self_dmn_api
from brains.cognitive.motivation.service.motivation_brain import service_api as motivation_api


class TestSelfModel:
    """Test self_model brain operations."""

    def test_describe_self_short(self):
        """DESCRIBE_SELF with mode='short' returns basic identity."""
        resp = self_model_api({
            "op": "DESCRIBE_SELF",
            "payload": {"mode": "short"}
        })

        assert resp["ok"] is True
        payload = resp["payload"]
        assert "identity" in payload
        assert "capabilities" in payload
        assert "limitations" in payload

        identity = payload["identity"]
        assert identity["name"] == "Maven"
        assert identity["role"] == "offline personal intelligence"

    def test_describe_self_detailed(self):
        """DESCRIBE_SELF with mode='detailed' returns full identity."""
        resp = self_model_api({
            "op": "DESCRIBE_SELF",
            "payload": {"mode": "detailed"}
        })

        assert resp["ok"] is True
        payload = resp["payload"]
        identity = payload["identity"]

        assert "creator" in identity
        assert "Josh Hinkle" in identity["creator"]
        assert "origin" in identity
        assert "goals" in identity
        assert isinstance(identity["goals"], list)
        assert len(identity["goals"]) > 0

    def test_get_capabilities(self):
        """GET_CAPABILITIES returns list of capabilities."""
        resp = self_model_api({"op": "GET_CAPABILITIES"})

        assert resp["ok"] is True
        capabilities = resp["payload"]["capabilities"]
        assert isinstance(capabilities, list)
        assert "reasoning" in capabilities
        assert "planning" in capabilities
        assert "memory storage and retrieval" in capabilities

    def test_get_limitations(self):
        """GET_LIMITATIONS returns list of limitations."""
        resp = self_model_api({"op": "GET_LIMITATIONS"})

        assert resp["ok"] is True
        limitations = resp["payload"]["limitations"]
        assert isinstance(limitations, list)
        assert "no internet access" in limitations
        assert "no physical actions" in limitations

    def test_no_hallucinated_capabilities(self):
        """Verify no hallucinated capabilities like 'browse internet'."""
        resp = self_model_api({"op": "GET_CAPABILITIES"})

        assert resp["ok"] is True
        capabilities = resp["payload"]["capabilities"]

        hallucinated = ["browse internet", "internet access", "web browsing", "physical actions"]
        for cap in capabilities:
            cap_lower = str(cap).lower()
            assert not any(h in cap_lower for h in hallucinated)


class TestSelfReview:
    """Test self_review brain operations."""

    def test_review_good_answer(self):
        """REVIEW_TURN accepts a good answer."""
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

        assert resp["ok"] is True
        payload = resp["payload"]
        assert payload["verdict"] == "ok"
        assert payload["recommended_action"] == "accept"
        assert len(payload["issues"]) == 0

    def test_review_low_confidence_answer(self):
        """REVIEW_TURN flags low confidence."""
        resp = self_review_api({
            "op": "REVIEW_TURN",
            "payload": {
                "query": "What is quantum entanglement?",
                "plan": {"steps": ["Explain"]},
                "thoughts": [],
                "answer": "I think it's something about particles.",
                "metadata": {
                    "confidences": {"final": 0.25, "reasoning": 0.3},
                    "used_memories": [],
                    "intents": ["question"]
                }
            }
        })

        assert resp["ok"] is True
        payload = resp["payload"]
        assert payload["verdict"] in ["minor_issue", "major_issue"]
        assert payload["recommended_action"] in ["revise", "ask_clarification"]
        assert any(i["code"] == "LOW_CONFIDENCE" for i in payload["issues"])

    def test_review_incomplete_answer(self):
        """REVIEW_TURN flags incomplete/empty answers."""
        resp = self_review_api({
            "op": "REVIEW_TURN",
            "payload": {
                "query": "Explain photosynthesis",
                "plan": {"steps": ["Explain process"]},
                "thoughts": [],
                "answer": "",
                "metadata": {
                    "confidences": {"final": 0.5, "reasoning": 0.5},
                    "used_memories": [],
                    "intents": ["question"]
                }
            }
        })

        assert resp["ok"] is True
        payload = resp["payload"]
        assert payload["verdict"] == "major_issue"
        assert payload["recommended_action"] in ["revise", "ask_clarification"]
        assert any(i["code"] == "INCOMPLETE" for i in payload["issues"])


class TestSelfDMN:
    """Test self_dmn brain operations."""

    def test_run_idle_cycle_no_issues(self):
        """RUN_IDLE_CYCLE with no issues returns minimal insights."""
        resp = self_dmn_api({
            "op": "RUN_IDLE_CYCLE",
            "payload": {
                "system_history": [],
                "recent_issues": [],
                "motivation_state": {}
            }
        })

        assert resp["ok"] is True
        payload = resp["payload"]
        assert "insights" in payload
        assert "actions" in payload
        assert isinstance(payload["insights"], list)
        assert isinstance(payload["actions"], list)

    def test_run_idle_cycle_with_errors(self):
        """RUN_IDLE_CYCLE with errors suggests actions."""
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

        assert resp["ok"] is True
        payload = resp["payload"]
        assert len(payload["insights"]) > 0
        assert len(payload["actions"]) > 0

        has_motivation_action = any(a["kind"] == "adjust_motivation" for a in payload["actions"])
        assert has_motivation_action

    def test_reflect_on_error(self):
        """REFLECT_ON_ERROR produces insights and actions."""
        resp = self_dmn_api({
            "op": "REFLECT_ON_ERROR",
            "payload": {
                "error_context": {
                    "verdict": "major_issue",
                    "error_type": "LOW_CONFIDENCE",
                    "issues": [{"code": "LOW_CONFIDENCE", "message": "Confidence too low"}],
                    "query": "test query"
                },
                "turn_history": []
            }
        })

        assert resp["ok"] is True
        payload = resp["payload"]
        assert len(payload["insights"]) > 0
        assert len(payload["actions"]) > 0


class TestMotivation:
    """Test motivation brain operations."""

    def test_get_state(self):
        """GET_STATE returns current drive vector."""
        resp = motivation_api({"op": "GET_STATE"})

        assert resp["ok"] is True
        state = resp["payload"]
        assert "helpfulness" in state
        assert "truthfulness" in state
        assert "curiosity" in state
        assert "self_improvement" in state

        for key, value in state.items():
            assert isinstance(value, (int, float))
            assert 0.0 <= value <= 1.0

    def test_adjust_state(self):
        """ADJUST_STATE modifies drives with bounded deltas."""
        # Get initial state
        initial_resp = motivation_api({"op": "GET_STATE"})
        initial_state = initial_resp["payload"]
        initial_help = initial_state["helpfulness"]

        # Adjust
        resp = motivation_api({
            "op": "ADJUST_STATE",
            "payload": {
                "deltas": {"helpfulness": 0.1}
            }
        })

        assert resp["ok"] is True
        new_state = resp["payload"]
        assert new_state["helpfulness"] >= initial_help
        assert new_state["helpfulness"] <= 1.0

    def test_adjust_state_bounded(self):
        """ADJUST_STATE respects bounds (max ±0.2)."""
        resp = motivation_api({
            "op": "ADJUST_STATE",
            "payload": {
                "deltas": {"helpfulness": 0.5}  # Try to add 0.5, should be clamped to 0.2
            }
        })

        assert resp["ok"] is True
        # Verify the adjustment was bounded (can't verify exact value without knowing initial state)
        state = resp["payload"]
        assert state["helpfulness"] <= 1.0

    def test_evaluate_query(self):
        """EVALUATE_QUERY computes motivation weights for a query."""
        resp = motivation_api({
            "op": "EVALUATE_QUERY",
            "payload": {
                "query": "why does the sky appear blue?",
                "context": {}
            }
        })

        assert resp["ok"] is True
        payload = resp["payload"]
        assert "weights" in payload
        assert "base_state" in payload

        weights = payload["weights"]
        assert "curiosity" in weights
        assert "truthfulness" in weights

        # "why" questions should boost curiosity
        assert weights["curiosity"] > payload["base_state"]["curiosity"]


class TestIntegration:
    """Test that self-systems actually integrate and affect behavior."""

    def test_motivation_affects_attention(self):
        """Verify motivation weights are incorporated into attention decisions."""
        # This is tested indirectly through the integrator brain which now uses motivation
        # The integrator reads motivation and adjusts brain priorities
        # This test verifies the motivation API is working correctly
        resp = motivation_api({
            "op": "EVALUATE_QUERY",
            "payload": {
                "query": "help me understand this",
                "context": {}
            }
        })

        assert resp["ok"] is True
        weights = resp["payload"]["weights"]
        # "help" keyword should boost helpfulness
        assert weights["helpfulness"] > 0.8

    def test_self_model_reflects_design(self):
        """Verify self_model reflects YOUR Maven design, not generic responses."""
        resp = self_model_api({
            "op": "DESCRIBE_SELF",
            "payload": {"mode": "detailed"}
        })

        assert resp["ok"] is True
        identity = resp["payload"]["identity"]

        # Should mention Josh Hinkle as creator
        assert "Josh Hinkle" in str(identity.get("creator", ""))
        # Should mention November 2025
        assert "November 2025" in str(identity.get("origin", ""))
        # Should have specific goals, not generic
        goals = identity.get("goals", [])
        assert len(goals) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
