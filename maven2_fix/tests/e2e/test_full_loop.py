"""
End‑to‑end tests exercising multiple components together.

These tests perform very simple integration checks across episodic
memory, self‑review, working memory and planner modules.  They do not
attempt to simulate the full Maven pipeline but provide smoke tests
covering cross‑module interactions introduced in Step‑4.
"""

import json
import time
from pathlib import Path

from brains.cognitive.self_review.service.self_review_brain import service_api as review_api
from brains.memory import episodic_memory as em
from brains.cognitive.planner.service.planner_brain import service_api as planner_api
from brains.cognitive.memory_librarian.service.memory_librarian import service_api as ml_api
from brains.cognitive.motivation.service.motivation_brain import service_api as motivation_api


def test_self_review_suggests_tuning(tmp_path, monkeypatch):
    # Create a fake trace file with a low confidence value
    trace_path = tmp_path / "trace_graph.jsonl"
    record = {
        "timestamp": time.time(),
        "event_type": "test",
        "payload": {},
        "visits": [("reasoning", {"confidence": 0.3})],
    }
    with open(trace_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    # Request tuning suggestions using our fake trace
    resp = review_api({"op": "RECOMMEND_TUNING", "payload": {"trace_path": str(trace_path)}})
    suggestions = resp.get("payload", {}).get("suggestions", [])
    # At least one suggestion should be present for low confidence
    assert suggestions


def test_episodic_store_and_recall(tmp_path, monkeypatch):
    # Redirect episodic memory path to temporary file
    monkeypatch.setattr(em, "EPISODE_PATH", str(tmp_path / "episodes.jsonl"), raising=False)
    # Store an episode via the service API
    em.service_api("EPISODE_STORE", {"info": {"question": "What?", "answer": "42", "confidence": 0.7}, "ttl": 10})
    # Retrieve episodes; expect at least one
    eps = em.service_api("EPISODE_GET", {"limit": 1}).get("payload", {}).get("episodes", [])
    assert eps
    # Summary should reference the same question
    summ = em.service_api("EPISODE_SUMMARY", {"n": 1}).get("payload", {}).get("summary", {})
    assert summ.get("recent")[0]["question"] == "What?"


def test_contradiction_reduces_drive():
    base = motivation_api({"op": "SCORE_DRIVE", "payload": {"context": {"success_count": 1, "affect_score": 1.0, "contradictions": 0}}})["payload"]["drive"]
    lower = motivation_api({"op": "SCORE_DRIVE", "payload": {"context": {"success_count": 1, "affect_score": 1.0, "contradictions": 5}}})["payload"]["drive"]
    assert lower < base


def test_plan_event_triggers_goal():
    entry = {"key": "e2e", "tags": ["plan"]}
    resp = planner_api({"op": "PLAN_FROM_WM", "payload": {"entry": entry}})
    goal = resp.get("payload", {}).get("goal")
    assert goal == "WM_PLAN:e2e"


def test_self_review_again(tmp_path, monkeypatch):
    # Another low‑confidence trace triggers tuning suggestions
    trace_path = tmp_path / "trace_graph2.jsonl"
    rec = {
        "timestamp": time.time(),
        "event_type": "test",
        "payload": {},
        "visits": [("language", {"confidence": 0.2})],
    }
    with open(trace_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    resp = review_api({"op": "RECOMMEND_TUNING", "payload": {"trace_path": str(trace_path)}})
    suggestions = resp.get("payload", {}).get("suggestions", [])
    assert suggestions