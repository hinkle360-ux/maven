"""User Knowledge Tracking
===========================

This module tracks how often a particular user asks questions or
interacts with Maven in various domains.  A domain is defined as the
first one or two words of a normalised question (e.g. ``"what is"`` or
``"how do"``).  Each time a question is answered, the domain count is
incremented.  By analysing these counts, Maven can infer the user's
familiarity with certain topics and adjust its responses accordingly.

The knowledge data is persisted in ``reports/user_knowledge.json``
within the Maven repository.  Counts decay gradually over time so
that long‑ago interactions have less influence on current familiarity.

Functions
---------

``update(domain: str) -> None``
    Increment the count for the given domain and update the timestamp.

``get_level(domain: str) -> str``
    Return a string indicating the user's familiarity level for the
    domain: ``"expert"``, ``"familiar"`` or ``"novice"`` based on the
    decayed count.

``get_stats(limit: int = 10) -> list[dict]``
    Return a list of the most frequently encountered domains along
    with their decayed counts and inferred familiarity levels.

The decay uses an exponential factor (5% per day) similar to the
meta‑confidence module.  This means that if a user stops asking about
a topic, their familiarity will gradually diminish.
"""

from __future__ import annotations

from pathlib import Path
import json
import time
from typing import Dict, List, Tuple

# Determine the Maven root directory (three levels up).  This file is
# located at ``brains/personal/memory/user_knowledge.py``.
HERE = Path(__file__).resolve()
MAVEN_ROOT = HERE.parents[3]
DATA_PATH = MAVEN_ROOT / "reports" / "user_knowledge.json"


def _load() -> Dict[str, Dict[str, float]]:
    """Load the user knowledge dictionary from disk.

    Returns a dict mapping domain keys to records with ``count`` and
    ``last_update``.  Missing or malformed files return an empty dict.
    """
    try:
        if not DATA_PATH.exists():
            return {}
        with DATA_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return {}
        out: Dict[str, Dict[str, float]] = {}
        for k, v in data.items():
            if not isinstance(k, str) or not isinstance(v, dict):
                continue
            try:
                c = float(v.get("count", 0.0))
            except Exception:
                c = 0.0
            try:
                t = float(v.get("last_update", 0.0))
            except Exception:
                t = 0.0
            out[k] = {"count": max(0.0, c), "last_update": t}
        return out
    except Exception:
        return {}


def _save(data: Dict[str, Dict[str, float]]) -> None:
    """Persist the knowledge data to disk.  Errors are silently ignored."""
    try:
        DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        serialisable = {}
        for k, v in data.items():
            if not isinstance(v, dict):
                continue
            serialisable[k] = {
                "count": float(v.get("count", 0.0)),
                "last_update": float(v.get("last_update", 0.0)),
            }
        with DATA_PATH.open("w", encoding="utf-8") as fh:
            json.dump(serialisable, fh)
    except Exception:
        return


def update(domain: str) -> None:
    """Increment the count for the given domain and apply decay.

    Args:
        domain: The domain key (lower‑cased) to update.  Empty keys are
            ignored.
    """
    try:
        key = str(domain or "").strip().lower()
        if not key:
            return
        stats = _load()
        rec = stats.get(key)
        now = time.time()
        DECAY_PER_DAY = 0.95  # 5% decay per day
        if rec is None:
            rec = {"count": 0.0, "last_update": now}
        else:
            try:
                last_ts = float(rec.get("last_update", 0.0))
            except Exception:
                last_ts = 0.0
            if last_ts > 0.0:
                delta_sec = max(0.0, now - last_ts)
                days = delta_sec / 86400.0
                decay = DECAY_PER_DAY ** days
                rec["count"] = float(rec.get("count", 0.0)) * decay
        rec["count"] = float(rec.get("count", 0.0)) + 1.0
        rec["last_update"] = now
        stats[key] = rec
        _save(stats)
    except Exception:
        return


def get_level(domain: str) -> str:
    """Return the user's familiarity level for the domain.

    Levels are assigned based on the decayed count:

    - ``"expert"`` for counts >= 10
    - ``"familiar"`` for counts >= 5
    - ``"novice"`` otherwise

    Args:
        domain: The domain key to look up.

    Returns:
        A string representing the familiarity level.
    """
    try:
        key = str(domain or "").strip().lower()
        if not key:
            return "novice"
        stats = _load()
        rec = stats.get(key)
        if not rec:
            return "novice"
        # Apply decay to the count before determining level
        count = float(rec.get("count", 0.0))
        try:
            last_ts = float(rec.get("last_update", 0.0))
        except Exception:
            last_ts = 0.0
        if last_ts > 0.0:
            now = time.time()
            delta_sec = max(0.0, now - last_ts)
            days = delta_sec / 86400.0
            DECAY_PER_DAY = 0.95
            decay = DECAY_PER_DAY ** days
            count *= decay
        if count >= 10.0:
            return "expert"
        if count >= 5.0:
            return "familiar"
        return "novice"
    except Exception:
        return "novice"


def get_stats(limit: int = 10) -> List[Dict[str, object]]:
    """Return a list of top domains by decayed count.

    Args:
        limit: Maximum number of domains to return.

    Returns:
        A list of dictionaries with keys ``domain``, ``count`` (decayed)
        and ``level`` indicating the inferred familiarity.
    """
    try:
        if limit <= 0:
            return []
        stats = _load()
        # Compute decayed counts for sorting
        entries: List[Tuple[str, float]] = []
        now = time.time()
        DECAY_PER_DAY = 0.95
        for k, rec in stats.items():
            count = float(rec.get("count", 0.0))
            try:
                last_ts = float(rec.get("last_update", 0.0))
            except Exception:
                last_ts = 0.0
            if last_ts > 0.0:
                delta_sec = max(0.0, now - last_ts)
                days = delta_sec / 86400.0
                decay = DECAY_PER_DAY ** days
                count *= decay
            entries.append((k, count))
        # Sort by decayed count descending
        entries.sort(key=lambda x: x[1], reverse=True)
        out: List[Dict[str, object]] = []
        for k, count in entries[:int(limit)]:
            level = get_level(k)
            out.append({"domain": k, "count": round(count, 4), "level": level})
        return out
    except Exception:
        return []