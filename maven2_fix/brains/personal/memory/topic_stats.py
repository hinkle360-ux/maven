"""Topic statistics utilities for Maven.

This module maintains a simple count of topics extracted from user
questions across sessions.  A topic is defined as the first one or
two words of a normalized question.  Counts are persisted to a
JSON file under ``reports/topic_stats.json``.  The statistics can
be queried via the personal brain API to support cross‑episode
learning and introspection (e.g. identifying popular topics or
trending subjects).

Functions:

  update_topic(question: str) -> None
      Extract a topic key from the given question and increment its
      count in the persistent stats file.  No value is returned.

  get_stats(limit: int = 10) -> List[Dict[str, int]]
      Return the top ``limit`` topics sorted by count.  Each entry
      includes ``topic`` and ``count`` fields.

The helpers in this module do not raise exceptions on failure; any
errors (e.g. due to file permissions) are silently ignored to avoid
impacting the main pipeline.
"""

from __future__ import annotations

from pathlib import Path
import json
from typing import Dict, List
import re

# Ascend to the Maven root: this file resides in
# brains/personal/memory/topic_stats.py.  The Maven root is four levels up.
HERE = Path(__file__).resolve()
PERSONAL_MEMORY_ROOT = HERE.parent  # .../personal/memory
MAVEN_ROOT = PERSONAL_MEMORY_ROOT.parents[3]

# Path to the persistent topic statistics file.
STATS_PATH = MAVEN_ROOT / "reports" / "topic_stats.json"


def _normalize_question(question: str) -> str:
    """Normalize a question string for topic extraction.

    This helper lowercases the question, removes punctuation and
    excessive whitespace.  It is intentionally simple and does not
    perform semantic parsing.

    Args:
        question: The raw user question.

    Returns:
        A normalized string containing only lowercase alphanumerics
        and single spaces.
    """
    s = (question or "").strip().lower()
    # Replace non‑alphanumeric characters with spaces
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    # Collapse multiple spaces
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _topic_key(question: str, n_words: int = 2) -> str:
    """Generate a topic key from a question.

    The topic key consists of the first ``n_words`` of the normalized
    question.  If the question has fewer than ``n_words`` words, the
    entire normalized string is returned.  Leading/trailing spaces are
    removed.

    Args:
        question: The raw user question.
        n_words: Number of words to include in the topic key.

    Returns:
        A lowercase string representing the topic key, or an empty
        string if the question is empty or cannot be normalized.
    """
    s = _normalize_question(question)
    if not s:
        return ""
    parts = s.split()
    return " ".join(parts[: min(n_words, len(parts))])


def update_topic(question: str) -> None:
    """Update the global topic statistics with a new question.

    This helper extracts a simple key from the question (the first two
    words by default) and increments its count in a persistent JSON
    file.  If the stats file does not exist, it is created.  Errors
    are silently ignored.

    Args:
        question: The user question string.
    """
    try:
        key = _topic_key(question)
        if not key:
            return
        # Ensure parent directory exists
        STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
        stats: Dict[str, int] = {}
        # Load existing stats if available
        if STATS_PATH.exists():
            with STATS_PATH.open("r", encoding="utf-8") as fh:
                try:
                    stats = json.load(fh)
                except Exception:
                    stats = {}
        # Increment count for this topic
        stats[key] = int(stats.get(key, 0)) + 1
        # Write back to disk
        with STATS_PATH.open("w", encoding="utf-8") as fh:
            json.dump(stats, fh)
    except Exception:
        # Avoid raising exceptions from stats update
        return


def get_stats(limit: int = 10) -> List[Dict[str, int]]:
    """Return a list of topics sorted by count.

    The returned list contains up to ``limit`` entries with the
    highest counts.  Each entry is a dict with ``topic`` and
    ``count`` keys.  If the stats file does not exist or cannot be
    read, an empty list is returned.

    Args:
        limit: Maximum number of topics to return (default 10).

    Returns:
        A list of dicts sorted by descending count.
    """
    out: List[Dict[str, int]] = []
    try:
        if not STATS_PATH.exists():
            return out
        with STATS_PATH.open("r", encoding="utf-8") as fh:
            try:
                stats: Dict[str, int] = json.load(fh)
            except Exception:
                return out
        items = sorted(stats.items(), key=lambda kv: kv[1], reverse=True)
        for topic, count in items[: max(1, int(limit))]:
            out.append({"topic": topic, "count": int(count)})
    except Exception:
        return []
    return out