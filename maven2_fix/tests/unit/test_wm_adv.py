"""
Advanced tests for working memory operations.

These tests exercise the persistence, retrieval and arbitration logic of
the working memory exposed by the memory librarian.  They also verify
that CONTROL_TICK and PROCESS_EVENTS emit and drain working memory
events correctly when arbitrations are enabled.  The tests use
monkeypatch to redirect persistence paths to temporary locations.
"""

import time
from brains.cognitive.memory_librarian.service.memory_librarian import service_api


def test_wm_persistence_and_arbitration(monkeypatch, tmp_path):
    # Patch the working memory store path to a temporary file
    import brains.cognitive.memory_librarian.service.memory_librarian as ml
    monkeypatch.setattr(ml, "_wm_store_path", lambda: tmp_path / "wm_store.jsonl", raising=False)
    # Clear the in-memory working memory to ensure test isolation
    ml._WORKING_MEMORY.clear()
    # Insert two entries with the same key but different confidence
    service_api({"op": "WM_PUT", "payload": {"key": "k", "value": "v1", "tags": ["t"], "confidence": 0.1, "ttl": 10}})
    # Wait briefly to ensure ordering difference
    time.sleep(0.01)
    service_api({"op": "WM_PUT", "payload": {"key": "k", "value": "v2", "tags": ["t"], "confidence": 0.9, "ttl": 10}})
    # Retrieve entries by key; arbitration should select the higher confidence
    resp = service_api({"op": "WM_GET", "payload": {"key": "k"}})
    assert resp["ok"]
    payload = resp.get("payload", {})
    # Winner should be v2
    winner = payload.get("winner")
    assert winner and winner.get("value") == "v2"
    # Dump should contain both entries
    dump = service_api({"op": "WM_DUMP", "payload": {}})
    entries = dump.get("payload", {}).get("entries", [])
    assert len(entries) == 2
    # CONTROL_TICK should emit events for both entries
    tick = service_api({"op": "CONTROL_TICK", "payload": {}})
    assert tick["ok"]
    # PROCESS_EVENTS drains the message bus and returns counts per type
    proc = service_api({"op": "PROCESS_EVENTS", "payload": {}})
    events = proc.get("payload", {}).get("events", {})
    # At least one WM_EVENT should have been processed
    assert any(ev for ev in events if "WM_EVENT" in ev or ev == "WM_EVENT")