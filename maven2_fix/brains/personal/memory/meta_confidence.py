"""Domain‑Specific Confidence Tracking
=======================================

This module implements a simple mechanism to track the Maven agent's
performance on different domains or topics and to compute a confidence
adjustment based on historical success rates.  Each domain is keyed by
a short string (typically the first one or two words of a question or
fact).  For each domain we store a count of successes and failures.
Successes correspond to cases where the agent produced a definitive
answer (e.g. verdict TRUE), while failures correspond to unanswered or
unknown responses.  These counts are persisted to a JSON file so that
confidence adjustments can be applied across sessions.

Functions:

  update(domain: str, success: bool) -> None
      Record a new success or failure for the given domain.  Domains
      are compared case‑insensitively.  An empty domain string is
      ignored.

  get_confidence(domain: str) -> float
      Compute a small adjustment factor based on the historical
      success rate for the domain.  The returned value is in the
      range [-0.1, 0.1], where positive values indicate higher
      confidence and negative values indicate lower confidence.  A
      neutral default of 0.0 is returned when there is no history.

  get_stats(limit: int = 10) -> list[dict]
      Return a list of domains with their success/failure counts and
      computed confidence adjustments.  The list is sorted by
      decreasing total count and truncated to the requested limit.

The meta‑confidence file is stored under ``reports/meta_confidence.json`` in
the Maven repository.  Errors in reading or writing this file are
silently ignored to avoid impacting the main pipeline.
"""

from __future__ import annotations
from pathlib import Path
import json
from typing import Dict, List, Tuple
import time

# Compute the Maven root.  This file resides at
# brains/personal/memory/meta_confidence.py, so ascend three levels to
# reach the ``maven`` directory.
HERE = Path(__file__).resolve()
MAVEN_ROOT = HERE.parents[3]
METACONF_PATH = MAVEN_ROOT / "reports" / "meta_confidence.json"


def _load() -> Dict[str, Dict[str, object]]:
    """Load the meta confidence statistics from disk.

    Returns a dictionary mapping domain keys to a dictionary with
    'success' and 'failure' counts.  Missing or malformed files
    produce an empty dictionary.
    """
    try:
        if not METACONF_PATH.exists():
            return {}
        with METACONF_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return {}
        out: Dict[str, Dict[str, object]] = {}
        for k, v in data.items():
            # We expect each record to be a dict with numeric success/failure and
            # optionally a last_update timestamp.  Unknown fields are ignored.
            if not isinstance(k, str) or not isinstance(v, dict):
                continue
            try:
                s = float(v.get("success", 0))
            except Exception:
                s = 0.0
            try:
                f = float(v.get("failure", 0))
            except Exception:
                f = 0.0
            try:
                sw = float(v.get("success_weight", s))
            except Exception:
                sw = s
            try:
                fw = float(v.get("failure_weight", f))
            except Exception:
                fw = f
            try:
                t = float(v.get("last_update", 0))
            except Exception:
                t = 0.0
            out[k] = {
                "success": max(0.0, s),
                "failure": max(0.0, f),
                "success_weight": max(0.0, sw),
                "failure_weight": max(0.0, fw),
                "last_update": t,
            }
        return out
    except Exception:
        return {}


def _save(stats: Dict[str, Dict[str, object]]) -> None:
    """Persist the given statistics dictionary to disk.

    Errors are silently ignored.
    """
    try:
        METACONF_PATH.parent.mkdir(parents=True, exist_ok=True)
        with METACONF_PATH.open("w", encoding="utf-8") as fh:
            # Convert floats to numbers for JSON serialization.  We keep
            # success/failure counts and last_update as numeric types.
            serialisable = {}
            for k, v in stats.items():
                if not isinstance(v, dict):
                    continue
                serialisable[k] = {
                    "success": float(v.get("success", 0.0)),
                    "failure": float(v.get("failure", 0.0)),
                    "success_weight": float(v.get("success_weight", v.get("success", 0.0))),
                    "failure_weight": float(v.get("failure_weight", v.get("failure", 0.0))),
                    "last_update": float(v.get("last_update", 0.0)),
                }
            json.dump(serialisable, fh)
    except Exception:
        return


def update(domain: str, success: bool, weight: float = 1.0) -> None:
    """Record a new success or failure for the given domain.

    Each update can be weighted to reflect the difficulty or length of the
    query.  The default weight of 1.0 treats all events equally.  When
    updating, both the unweighted and weighted counts are stored.  A
    decaying factor is applied to both sets of counts based on the time
    elapsed since the last update.

    Args:
        domain: A string key identifying the domain (e.g. topic key).
        success: True if the agent produced a correct answer, False
            otherwise.
        weight: A positive number representing the importance of this
            event.  Larger weights emphasise harder or more complex
            queries.  Values less than or equal to zero are treated as
            1.0.
    """
    try:
        key = str(domain or "").strip().lower()
        if not key:
            return
        # Normalise weight to be at least 1.0 to avoid reducing counts.
        try:
            w = float(weight)
        except Exception:
            w = 1.0
        if w <= 0.0:
            w = 1.0
        stats = _load()
        rec = stats.get(key, None)
        now = time.time()
        # Decay counts based on elapsed time since last update.  We use an
        # exponential decay so that older successes/failures have less
        # influence.  If there is no prior record, start fresh.
        DECAY_PER_DAY = 0.95  # 5% decay per day
        if rec is None:
            rec = {
                "success": 0.0,
                "failure": 0.0,
                "success_weight": 0.0,
                "failure_weight": 0.0,
                "last_update": now,
            }
        else:
            try:
                last_ts = float(rec.get("last_update", 0.0))
            except Exception:
                last_ts = 0.0
            # Compute elapsed time in days.  If timestamps are zero or
            # invalid, skip decay.
            if last_ts > 0.0:
                delta_sec = max(0.0, now - last_ts)
                days = delta_sec / 86400.0
                # Apply exponential decay: counts *= DECAY_PER_DAY**days
                decay = DECAY_PER_DAY ** days
                rec["success"] = float(rec.get("success", 0.0)) * decay
                rec["failure"] = float(rec.get("failure", 0.0)) * decay
                rec["success_weight"] = float(rec.get("success_weight", rec.get("success", 0.0))) * decay
                rec["failure_weight"] = float(rec.get("failure_weight", rec.get("failure", 0.0))) * decay
        # Add the new event.  Increment both unweighted and weighted counts.
        if success:
            rec["success"] = float(rec.get("success", 0.0)) + 1.0
            rec["success_weight"] = float(rec.get("success_weight", 0.0)) + w
        else:
            rec["failure"] = float(rec.get("failure", 0.0)) + 1.0
            rec["failure_weight"] = float(rec.get("failure_weight", 0.0)) + w
        rec["last_update"] = now
        stats[key] = rec
        _save(stats)
    except Exception:
        return


def get_confidence(domain: str) -> float:
    """Compute a confidence adjustment for the given domain.

    The adjustment is based on the ratio of successes to total
    attempts.  When there are no attempts, return 0.0.  The formula
    maps success rates to a range between -0.1 and +0.1.

    Args:
        domain: The domain key to look up.

    Returns:
        A float in [-0.1, 0.1] representing the confidence adjustment.
    """
    try:
        key = str(domain or "").strip().lower()
        if not key:
            return 0.0
        stats = _load()
        rec = stats.get(key)
        if not rec:
            return 0.0
        # Pull counts as floats.  If weighted counts are present use them;
        # otherwise fall back to unweighted counts.
        try:
            succ = float(rec.get("success_weight", rec.get("success", 0.0)))
        except Exception:
            succ = float(rec.get("success", 0.0))
        try:
            fail = float(rec.get("failure_weight", rec.get("failure", 0.0)))
        except Exception:
            fail = float(rec.get("failure", 0.0))
        # Apply decay based on time since last update.  Use the same
        # exponential decay as in update() to ensure decayed ratio.
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
            succ *= decay
            fail *= decay
        total_weight = succ + fail
        if total_weight <= 0.0:
            return 0.0
        ratio = succ / float(total_weight)
        # Map ratio [0,1] to adjustment [-0.1, +0.1] with 0.5 as neutral
        adj = (ratio - 0.5) * 0.2
        # Clamp to [-0.1, 0.1]
        if adj > 0.1:
            adj = 0.1
        if adj < -0.1:
            adj = -0.1
        return adj
    except Exception:
        return 0.0


def get_stats(limit: int = 10) -> List[Dict[str, object]]:
    """Return a list of domain statistics with computed adjustments.

    Args:
        limit: Maximum number of records to return (default 10).

    Returns:
        A list of dicts each containing the domain key, success count,
        failure count, total attempts and computed confidence adjustment.
        Sorted by total attempts descending.
    """
    try:
        if limit <= 0:
            return []
        stats = _load()
        items: List[Tuple[str, Dict[str, int]]] = list(stats.items())
        items.sort(key=lambda t: (t[1].get("success", 0) + t[1].get("failure", 0)), reverse=True)
        out: List[Dict[str, object]] = []
        for key, rec in items[:int(limit)]:
            succ = float(rec.get("success", 0.0))
            fail = float(rec.get("failure", 0.0))
            succ_w = float(rec.get("success_weight", succ))
            fail_w = float(rec.get("failure_weight", fail))
            total = succ + fail
            total_weight = succ_w + fail_w
            adj = get_confidence(key)
            out.append({
                "domain": key,
                "success": int(succ),
                "failure": int(fail),
                "total": int(total),
                "success_weight": round(succ_w, 4),
                "failure_weight": round(fail_w, 4),
                "total_weight": round(total_weight, 4),
                "adjustment": round(adj, 4),
            })
        return out
    except Exception:
        return []