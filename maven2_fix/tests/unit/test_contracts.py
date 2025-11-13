"""
Unit tests for IO schema validation and agent executor contract enforcement.

These tests verify that the agent executor rejects malformed task
specifications and accepts well‑formed ones.  It exercises the PLAN
operation, but the same validation is applied to DRY_RUN and EXECUTE.
"""

from brains.agent.service import agent_executor  # type: ignore


def test_valid_taskspec_plan() -> None:
    # A simple task with a single edit should succeed
    spec = {"edits": [{"path": "README.md", "new_text": "foo"}]}
    res = agent_executor.service_api({"op": "PLAN", "payload": {"taskspec": spec}})
    assert res.get("ok") is True, f"expected ok response, got: {res}"


def test_invalid_taskspec_non_mapping() -> None:
    # Non‑mapping taskspec should be rejected
    res = agent_executor.service_api({"op": "PLAN", "payload": {"taskspec": "invalid"}})
    assert res.get("ok") is False, "non‑mapping taskspec should be invalid"
    err = res.get("error", {})
    assert "Invalid task specification" in err.get("message", ""), f"unexpected error message: {err}"


def test_invalid_taskspec_missing_path() -> None:
    # Missing path on edit should be rejected
    spec = {"edits": [{"new_text": "foo"}]}
    res = agent_executor.service_api({"op": "PLAN", "payload": {"taskspec": spec}})
    assert res.get("ok") is False, "missing 'path' should be invalid"
    err = res.get("error", {})
    assert "path" in err.get("message", ""), f"unexpected error message: {err}"


def test_invalid_taskspec_missing_cmd() -> None:
    # Missing cmd in run should be rejected
    spec = {"run": [{}]}
    res = agent_executor.service_api({"op": "PLAN", "payload": {"taskspec": spec}})
    assert res.get("ok") is False, "missing 'cmd' should be invalid"
    err = res.get("error", {})
    assert "cmd" in err.get("message", ""), f"unexpected error message: {err}"