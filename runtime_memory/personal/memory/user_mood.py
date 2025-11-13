"""Persistent user mood tracking for the Maven cognitive system.

This module maintains a simple scalar representing the user's overall
emotional state.  The mood value ranges from -1.0 (very negative) to
1.0 (very positive) and decays toward neutral (0.0) over time.  Each
interaction can update the mood based on the valence (positive or
negative sentiment) detected in the user's input.  The mood can be
retrieved to influence tone and style in responses, and reset when
needed.  All data is persisted to disk in ``reports/user_mood.json``
relative to the Maven project root.
"""

from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Dict, Any

# Compute the project root.  This file lives at
# brains/personal/memory/user_mood.py so the Maven root is
# three levels up (memory → personal → brains → maven).
HERE = Path(__file__).resolve()
MAVEN_ROOT = HERE.parents[3]

# Path to the persistent mood file.
_MOOD_PATH = MAVEN_ROOT / "reports" / "user_mood.json"

# Daily decay factor.  The mood value is multiplied by this factor
# each day (86,400 seconds) since the last update.  A value of 0.95
# corresponds to a 5% decay per day.
_DAILY_DECAY = 0.95

# Weight factor applied to incoming valence updates.  The new valence
# influences the mood by this weight relative to the existing mood.
_UPDATE_WEIGHT = 0.2


def _load() -> Dict[str, Any]:
    """Load the mood record from disk.

    Returns:
        A dict with keys ``value`` (float) and ``last_update`` (float
        timestamp).  If the file is missing or invalid, returns a
        default neutral mood record.
    """
    try:
        if _MOOD_PATH.exists():
            with open(_MOOD_PATH, "r", encoding="utf-8") as fh:
                data = json.load(fh) or {}
            value = float(data.get("value", 0.0))
            last_update = float(data.get("last_update", 0.0))
            return {"value": value, "last_update": last_update}
    except Exception:
        pass
    # Default neutral mood
    return {"value": 0.0, "last_update": 0.0}


def _save(data: Dict[str, Any]) -> None:
    """Persist the mood record to disk."""
    try:
        _MOOD_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_MOOD_PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
    except Exception:
        # Ignore write failures
        pass


def _apply_decay(value: float, last_update: float, now: float) -> float:
    """Apply exponential decay to the mood value based on elapsed time.

    Args:
        value: The previous mood value.
        last_update: Timestamp of the last update (seconds since epoch).
        now: Current timestamp.

    Returns:
        The decayed mood value.
    """
    try:
        elapsed = float(now) - float(last_update)
    except Exception:
        elapsed = 0.0
    if elapsed <= 0 or value == 0.0:
        return value
    # Compute the decay factor based on elapsed days
    days = elapsed / 86400.0
    decay_factor = _DAILY_DECAY ** days
    return value * decay_factor


def update(valence: float) -> None:
    """Update the user's mood based on detected valence.

    Args:
        valence: A float in the range [-1.0, 1.0] representing the
            sentiment of the user's input.  Negative values indicate
            negative emotion, positive values indicate positive emotion.

    This function loads the existing mood record, applies decay
    proportional to the time since the last update, then combines the
    decayed value with the new valence using a weighted average.
    The result is clamped to [-1.0, 1.0] and persisted.
    """
    try:
        val = float(valence)
    except Exception:
        return
    if val < -1.0:
        val = -1.0
    elif val > 1.0:
        val = 1.0
    rec = _load()
    now = time.time()
    # Apply decay to previous value
    base = _apply_decay(rec.get("value", 0.0), rec.get("last_update", 0.0), now)
    # Combine with new valence using UPDATE_WEIGHT
    updated = base + _UPDATE_WEIGHT * val
    # Clamp to [-1,1]
    if updated > 1.0:
        updated = 1.0
    elif updated < -1.0:
        updated = -1.0
    # Save new record
    _save({"value": updated, "last_update": now})


def get_mood() -> float:
    """Return the current mood value with decay applied.

    Returns:
        A float in [-1.0, 1.0] representing the decayed mood.  Positive
        values indicate positive mood, negative values indicate
        negative mood.
    """
    rec = _load()
    now = time.time()
    value = _apply_decay(rec.get("value", 0.0), rec.get("last_update", 0.0), now)
    # Optionally clamp within [-1,1]
    if value > 1.0:
        value = 1.0
    elif value < -1.0:
        value = -1.0
    return float(value)


def reset() -> None:
    """Reset the mood to neutral (0.0) by removing the persisted file."""
    try:
        if _MOOD_PATH.exists():
            _MOOD_PATH.unlink()
    except Exception:
        pass