"""
Additional tests for the episodic memory module.

This test ensures that storing episodes with explicit TTLs and retrieving
them via the service API works end to end.  It patches the episode
storage path to a temporary location to avoid side effects.
"""

from brains.memory import episodic_memory as em


def test_episode_store_get_summary(monkeypatch, tmp_path):
    # Redirect the episodic storage path to a temporary file
    monkeypatch.setattr(em, "EPISODE_PATH", str(tmp_path / "episodes.jsonl"), raising=False)
    # Store two episodes
    em.service_api("EPISODE_STORE", {"info": {"question": "Q1", "answer": "A1", "confidence": 0.6}, "ttl": 10})
    em.service_api("EPISODE_STORE", {"info": {"question": "Q2", "answer": "A2", "confidence": 0.8}, "ttl": 10})
    # Get episodes via the API
    resp = em.service_api("EPISODE_GET", {"limit": 2})
    assert resp.get("ok")
    eps = resp.get("payload", {}).get("episodes", [])
    assert len(eps) == 2
    # Summary should report the same count
    summary = em.service_api("EPISODE_SUMMARY", {"n": 2})
    assert summary.get("ok")
    summ = summary.get("payload", {}).get("summary", {})
    assert summ.get("count") >= 2