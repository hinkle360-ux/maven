"""
Integration tests for enabling and disabling the cognitive graph.

These tests are placeholders that exercise the graph configuration
toggle in a superficial manner.  They ensure that toggling the graph
does not raise exceptions when invoked through the memory librarian
and that trace files can be created on demand.  Real tests should
verify behavioural changes in later iterations.
"""

import os
from brains.cognitive.memory_librarian.service.memory_librarian import service_api as ml_api
from api.utils import CFG


def test_graph_disabled_linear_mode():
    # Ensure graph is disabled
    CFG.setdefault("graph", {}).update({"enabled": False})
    # Perform a WM put and tick; no exceptions should occur
    ml_api({"op": "WM_PUT", "payload": {"key": "g", "value": "x", "ttl": 1}})
    ml_api({"op": "CONTROL_TICK", "payload": {}})
    ml_api({"op": "PROCESS_EVENTS", "payload": {}})
    assert True


def test_graph_enabled_writes_trace(tmp_path, monkeypatch):
    # Enable the graph and override trace path
    CFG.setdefault("graph", {}).update({"enabled": True, "max_steps": 10})
    import brains.cognitive.graph_engine as ge_module
    # Patch trace path to temporary file
    monkeypatch.setattr(ge_module, "TRACE_PATH", str(tmp_path / "trace_graph_en.jsonl"), raising=False)
    # Trigger a WM event which will run the graph engine
    ml_api({"op": "WM_PUT", "payload": {"key": "h", "value": "x", "ttl": 1}})
    ml_api({"op": "CONTROL_TICK", "payload": {}})
    ml_api({"op": "PROCESS_EVENTS", "payload": {}})
    # A trace file should have been created
    assert os.path.exists(ge_module.TRACE_PATH)


def test_graph_toggle_restore(tmp_path, monkeypatch):
    # Turn graph off again and ensure trace file isn't overwritten on next tick
    CFG.setdefault("graph", {}).update({"enabled": False})
    import brains.cognitive.graph_engine as ge_module
    monkeypatch.setattr(ge_module, "TRACE_PATH", str(tmp_path / "trace_graph_off.jsonl"), raising=False)
    ml_api({"op": "WM_PUT", "payload": {"key": "z", "value": "y", "ttl": 1}})
    ml_api({"op": "CONTROL_TICK", "payload": {}})
    ml_api({"op": "PROCESS_EVENTS", "payload": {}})
    # Trace file should either not exist or be empty because no graph runs
    exists = os.path.exists(ge_module.TRACE_PATH)
    if exists:
        size = os.path.getsize(ge_module.TRACE_PATH)
        assert size == 0
    else:
        assert True


def test_graph_max_steps_effect(tmp_path, monkeypatch):
    # Set max_steps to 1 and enable graph
    CFG.setdefault("graph", {}).update({"enabled": True, "max_steps": 1})
    import brains.cognitive.graph_engine as ge_module
    monkeypatch.setattr(ge_module, "TRACE_PATH", str(tmp_path / "trace_graph_step.jsonl"), raising=False)
    # Insert a WM event
    ml_api({"op": "WM_PUT", "payload": {"key": "q", "value": "a", "ttl": 1}})
    ml_api({"op": "CONTROL_TICK", "payload": {}})
    ml_api({"op": "PROCESS_EVENTS", "payload": {}})
    # Graph trace file should exist
    assert os.path.exists(ge_module.TRACE_PATH)


def test_graph_config_reset():
    # Reset graph config to default disabled
    CFG.setdefault("graph", {}).update({"enabled": False, "max_steps": 50})
    assert not CFG.get("graph").get("enabled")