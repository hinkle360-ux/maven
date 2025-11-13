"""
Belief Tracker
==============

This module provides a simple persistent store for beliefs (facts)
and helper functions to record, query and detect conflicts among
beliefs.  A belief consists of a ``subject``, a ``predicate``, an
``object`` and an optional ``confidence`` score.  Beliefs are
stored in a newline‑delimited JSON file under the ``reports``
directory so that they persist across sessions.

Functions exported include:

* ``add_belief(subject, predicate, obj, confidence=1.0)`` – Append a
  new belief record to the belief file.
* ``find_related_beliefs(query)`` – Return all beliefs whose
  subject or object contains the query string (case insensitive).
* ``detect_conflict(subject, predicate, obj)`` – Check if a new
  belief about ``subject`` and ``predicate`` conflicts with existing
  beliefs (different object).  Returns the first conflicting belief
  or ``None`` if no conflict is found.

These helpers are intentionally lightweight and do not perform
semantic reasoning.  They are intended to serve as building blocks
for a richer belief management system in future upgrades.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Dict, Any, Optional

# Determine the path for the belief store.  It resides under
# the top‑level ``reports`` directory relative to this file.  If the
# directory does not exist, it will be created on demand when
# appending beliefs.
_ROOT = Path(__file__).resolve().parents[4]
BELIEF_FILE = _ROOT / "reports" / "beliefs.jsonl"


def _load_beliefs() -> List[Dict[str, Any]]:
    """Load all belief records from the belief file.

    Returns:
        A list of belief dictionaries.  If the file does not exist
        or an error occurs, an empty list is returned.
    """
    records: List[Dict[str, Any]] = []
    try:
        if BELIEF_FILE.exists():
            with open(BELIEF_FILE, "r", encoding="utf-8") as fh:
                for line in fh:
                    try:
                        obj = json.loads(line.strip())
                        if isinstance(obj, dict):
                            records.append(obj)
                    except Exception:
                        continue
    except Exception:
        return []
    return records


def _append_belief(rec: Dict[str, Any]) -> None:
    """Append a single belief record to the belief file.

    Args:
        rec: The belief dictionary to write.  Must contain at least
            ``subject``, ``predicate`` and ``object`` keys.
    """
    try:
        BELIEF_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(BELIEF_FILE, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
    except Exception:
        # Silently ignore write errors
        pass


def add_belief(subject: str, predicate: str, obj: str, confidence: float = 1.0) -> None:
    """Add a new belief to the belief store.

    Args:
        subject: The subject of the belief (e.g. "Paris").
        predicate: The predicate or relation (e.g. "is").
        obj: The object of the belief (e.g. "the capital of France").
        confidence: Optional confidence score between 0 and 1.
    """
    try:
        rec = {
            "subject": str(subject).strip(),
            "predicate": str(predicate).strip(),
            "object": str(obj).strip(),
            "confidence": float(confidence),
        }
        _append_belief(rec)
    except Exception:
        pass


def find_related_beliefs(query: str) -> List[Dict[str, Any]]:
    """Find beliefs related to the provided query string.

    A belief is considered related if the query appears as a
    substring (case insensitive) of the belief's subject or object.

    Args:
        query: The query string to search for.
    Returns:
        A list of matching belief dictionaries.
    """
    try:
        q = str(query).strip().lower()
    except Exception:
        q = ""
    if not q:
        return []
    try:
        records = _load_beliefs()
        matches: List[Dict[str, Any]] = []
        for rec in records:
            subj = str(rec.get("subject", "")).lower()
            obj = str(rec.get("object", "")).lower()
            if q in subj or q in obj:
                matches.append(rec)
        return matches
    except Exception:
        return []


def detect_conflict(subject: str, predicate: str, obj: str) -> Optional[Dict[str, Any]]:
    """Detect whether a new belief conflicts with an existing one.

    A conflict occurs when there is already a belief with the same
    subject and predicate but a different object.  Only the first
    conflicting belief is returned.

    Args:
        subject: The subject of the new belief.
        predicate: The predicate of the new belief.
        obj: The object of the new belief.
    Returns:
        The conflicting belief dictionary if found; otherwise ``None``.
    """
    try:
        s = str(subject).strip().lower()
        p = str(predicate).strip().lower()
        o = str(obj).strip().lower()
        for rec in _load_beliefs():
            rs = str(rec.get("subject", "")).strip().lower()
            rp = str(rec.get("predicate", "")).strip().lower()
            ro = str(rec.get("object", "")).strip().lower()
            if rs == s and rp == p and ro != o:
                return rec
        return None
    except Exception:
        return None