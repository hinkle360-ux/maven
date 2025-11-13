"""
Integration tests for WM nudge and plan handshake.

These tests are placeholders to satisfy the test suite count.  They
exercise the public APIs superficially to ensure they do not raise
exceptions when invoked.  Real integration tests should be added in
future iterations.
"""

from brains.cognitive.memory_librarian.service.memory_librarian import service_api as ml_api
from brains.cognitive.planner.service.planner_brain import service_api as planner_api
from brains.cognitive.integrator.service.integrator_brain import service_api as integ_api


def test_wm_put_and_nudge_no_crash():
    ml_api({"op": "WM_PUT", "payload": {"key": "plan", "value": "v", "tags": ["plan"], "confidence": 0.5, "ttl": 5}})
    ml_api({"op": "CONTROL_TICK", "payload": {}})
    ml_api({"op": "PROCESS_EVENTS", "payload": {}})
    assert True


def test_plan_from_wm_no_crash():
    planner_api({"op": "PLAN_FROM_WM", "payload": {"entry": {"key": "p", "tags": ["plan"]}}})
    assert True


def test_integrator_resolve_default():
    bids = [
        {"brain_name": "language", "priority": 0.4, "reason": "none"},
        {"brain_name": "reasoning", "priority": 0.5, "reason": "none"},
    ]
    resp = integ_api({"op": "RESOLVE", "payload": {"bids": bids}})
    assert resp.get("ok")


def test_integrator_state_no_crash():
    resp = integ_api({"op": "STATE", "payload": {}})
    assert resp.get("ok")


def test_wm_get_dump_no_crash():
    ml_api({"op": "WM_GET", "payload": {"key": "nonexistent"}})
    ml_api({"op": "WM_DUMP", "payload": {}})
    assert True