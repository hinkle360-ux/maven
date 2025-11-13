"""
Unit tests for the planner brain's PLAN_FROM_WM handshake.

These tests ensure that PLAN_FROM_WM returns a deterministic goal ID
based on the working memory entry key and that repeated calls do not
generate duplicate goals.  The ledger side effects are not
asserted here to keep the test self‑contained.
"""

from brains.cognitive.planner.service.planner_brain import service_api as planner_api


def test_plan_from_wm_single_goal():
    # Send the same WM entry twice; the resulting goal ID should be deterministic
    entry = {"key": "123", "tags": ["plan"]}
    resp1 = planner_api({"op": "PLAN_FROM_WM", "payload": {"entry": entry}})
    resp2 = planner_api({"op": "PLAN_FROM_WM", "payload": {"entry": entry}})
    goal1 = resp1.get("payload", {}).get("goal")
    goal2 = resp2.get("payload", {}).get("goal")
    assert goal1 == "WM_PLAN:123"
    assert goal1 == goal2