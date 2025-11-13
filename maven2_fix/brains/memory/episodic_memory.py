"""
episodic_memory.py
~~~~~~~~~~~~~~~~~~~

This module introduces a very simple episodic memory store for Maven.  An
episode is a snapshot of an interaction that includes context such as the
question, answer, confidence, tags and timestamps.  Episodic memory
enables future recall of past experiences and can be queried or
summarised by other cognitive components.  This implementation is
deliberately minimal: it writes each episode as a JSON line to
``reports/episodic_memory.jsonl`` and provides basic operations to store
and retrieve episodes.

To comply with Maven's rules, the memory operates offline and uses
standard library only.  It does not integrate with any vector database
or external search; retrieval is simple linear scanning.  TTL (time to
live) may be provided per episode to limit how long experiences persist.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Iterator, List, Optional

# Determine the reports directory relative to this file.  We locate the
# project root by traversing upward until 'reports' is found.
MODULE_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(MODULE_DIR)))
EPISODE_PATH = os.path.join(PROJECT_ROOT, "reports", "episodic_memory.jsonl")


def _ensure_directory(path: str) -> None:
    """Ensure that the parent directory of ``path`` exists."""
    os.makedirs(os.path.dirname(path), exist_ok=True)


def store_episode(info: Dict[str, Any], ttl: Optional[float] = None) -> None:
    """Persist a single episode to disk.

    Args:
        info: A dictionary containing information about the episode.  It
            should include keys such as ``question``, ``answer``,
            ``confidence``, and optional ``tags``.
        ttl: If provided, the number of seconds this episode should remain
            retrievable.  The expiry timestamp is stored in the record.
    """
    record = dict(info or {})
    record["timestamp"] = time.time()
    if ttl is not None:
        try:
            ttl_float = float(ttl)
        except Exception:
            ttl_float = 0.0
        record["expires_at"] = record["timestamp"] + max(0.0, ttl_float)
    _ensure_directory(EPISODE_PATH)
    try:
        with open(EPISODE_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        # ignore file errors
        pass


def _read_episodes() -> Iterator[Dict[str, Any]]:
    """Yield all episodes from disk, pruning expired entries."""
    now = time.time()
    try:
        with open(EPISODE_PATH, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line.strip())
                except json.JSONDecodeError:
                    continue
                expires = rec.get("expires_at")
                if expires is not None and expires < now:
                    continue  # skip expired
                yield rec
    except FileNotFoundError:
        return
    except Exception:
        return


def get_episodes(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Return a list of stored episodes.

    Args:
        limit: Maximum number of episodes to return, most recent first.
    Returns:
        A list of episode records.
    """
    episodes = list(_read_episodes())
    # sort by timestamp descending
    episodes.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    if limit is not None:
        try:
            l = int(limit)
        except Exception:
            l = 0
        episodes = episodes[:max(l, 0)]
    return episodes


def summarize_episodes(n: int = 5) -> Dict[str, Any]:
    """Return a summary of the most recent episodes.

    Args:
        n: Number of recent episodes to include in the summary.
    Returns:
        A dict with a ``count`` of total episodes and a list of
        ``recent`` episodes (up to ``n``).  Each summary includes the
        question, answer and confidence.
    """
    episodes = get_episodes(n)
    summary = {
        "count": len(episodes),
        "recent": [
            {
                "question": e.get("question"),
                "answer": e.get("answer"),
                "confidence": e.get("confidence"),
                "timestamp": e.get("timestamp"),
            }
            for e in episodes
        ],
    }
    return summary


def service_api(op: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Service API for episodic memory operations.

    Supported operations:

      - EPISODE_STORE: store a new episode.  ``payload`` should contain
        the episode info and optional ``ttl``.
      - EPISODE_GET: retrieve episodes.  Optionally specify ``limit``.
      - EPISODE_SUMMARY: return a summary of the most recent episodes.

    Returns a dictionary with operation results or an error message.
    """
    op_upper = (op or "").upper()
    payload = payload or {}
    if op_upper == "EPISODE_STORE":
        info = payload.get("info") or {}
        ttl = payload.get("ttl")
        store_episode(info, ttl)
        return {"ok": True, "op": op_upper}
    if op_upper == "EPISODE_GET":
        limit = payload.get("limit")
        episodes = get_episodes(limit)
        return {"ok": True, "op": op_upper, "payload": {"episodes": episodes}}
    if op_upper == "EPISODE_SUMMARY":
        n = payload.get("n", 5)
        try:
            n_int = int(n)
        except Exception:
            n_int = 5
        summary = summarize_episodes(n_int)
        return {"ok": True, "op": op_upper, "payload": {"summary": summary}}
    return {"ok": False, "op": op_upper, "error": "unknown operation"}