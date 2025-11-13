"""
Tests for memory librarian working memory persistence and arbitration.

These tests ensure that WM_PUT stores entries with TTL, WM_GET
retrieves them and that the persistence toggle works.  They use
monkeypatch to redirect the persistent store into a temporary path.
"""

import time
from pathlib import Path
import json

import pytest

from brains.cognitive.memory_librarian.service.memory_librarian import service_api


def test_wm_put_get_roundtrip(tmp_path, monkeypatch):
    # Patch the WM store path to a temp file
    from brains.cognitive.memory_librarian.service import memory_librarian as ml
    monkeypatch.setattr(ml, "_wm_store_path", lambda: Path(tmp_path / "wm_store.jsonl"))
    # Ensure loaded flag resets
    monkeypatch.setattr(ml, "_WM_LOADED_FROM_DISK", False, raising=False)
    # Put an entry with TTL
    key = "key1"
    value = {"foo": "bar"}
    resp = service_api({"op": "WM_PUT", "mid": "m1", "payload": {"key": key, "value": value, "confidence": 0.8, "ttl": 5.0}})
    assert resp.get("ok")
    # Get by key
    resp_get = service_api({"op": "WM_GET", "mid": "m2", "payload": {"key": key}})
    assert resp_get.get("ok")
    entries = (resp_get.get("payload") or {}).get("entries") or []
    assert any(e.get("value") == value for e in entries)


def test_wm_persistence(tmp_path, monkeypatch):
    # Patch persistence path and enable persistence
    from brains.cognitive.memory_librarian.service import memory_librarian as ml
    monkeypatch.setattr(ml, "_wm_store_path", lambda: Path(tmp_path / "wm_store.jsonl"))
    monkeypatch.setattr(ml, "_WM_LOADED_FROM_DISK", False, raising=False)
    # Enable persistence via CFG
    from api.utils import CFG
    old_cfg = dict(CFG.get("wm", {}))
    CFG.setdefault("wm", {})["persist"] = True
    # Put entry
    key = "persist_key"
    resp = service_api({"op": "WM_PUT", "mid": "m3", "payload": {"key": key, "value": 123, "confidence": 0.5, "ttl": 1.0}})
    assert resp.get("ok")
    # Wait for TTL to expire
    time.sleep(1.1)
    # Load persisted entries (should skip expired) then get
    ml._WM_LOADED_FROM_DISK = False
    resp_load = service_api({"op": "WM_GET", "mid": "m4", "payload": {"key": key}})
    entries = (resp_load.get("payload") or {}).get("entries") or []
    # Since TTL expired, the list should be empty
    assert all(e.get("key") != key for e in entries)
    # Restore cfg
    CFG["wm"] = old_cfg