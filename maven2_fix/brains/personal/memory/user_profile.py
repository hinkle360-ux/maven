"""User Profile Utilities for Maven
====================================

This module implements a simple persistent store for capturing
user‑specific preferences and attributes.  Unlike the identity journal,
which records Maven's own self‑image, the user profile keeps track of
facts about the user (e.g. location, preferred language, interests)
that may influence interactions.  Storing these details allows
Maven to deliver more personalized responses over time while keeping
all updates within its safe sandbox.

The profile is stored as a JSON object in the ``reports`` directory
relative to the Maven project root.  Functions are provided to load
and save the profile, update individual attributes, and retrieve
values or the entire profile.  Errors during file operations are
silently ignored to avoid disrupting the main pipeline.

Functions:

  update_profile(key: str, value: str) -> None
      Set a profile attribute to a new value.  The key is stored
      lower‑cased and stripped of whitespace.  Values are stored as
      strings.  Existing keys are overwritten.

  get_profile() -> Dict[str, str]
      Return the current user profile dictionary.  If no profile
      exists, an empty dict is returned.

  get_attribute(key: str) -> Optional[str]
      Retrieve a single profile value by key.  Returns None if the
      key is not present.

The profile is intended to be small and human‑readable.  It is not
encrypted and should not contain sensitive personal information.  All
data is stored locally on the host running Maven.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

# Compute the project root.  This file lives at
# brains/personal/memory/user_profile.py so the Maven root is
# four levels up.
HERE = Path(__file__).resolve()
MAVEN_ROOT = HERE.parents[3]

# Path to the persistent user profile file
PROFILE_PATH = MAVEN_ROOT / "reports" / "user_profile.json"


def _load_profile() -> Dict[str, str]:
    """Load the user profile from disk.

    Returns a dictionary of key‑value pairs.  If the file cannot be
    read, an empty dict is returned.
    """
    try:
        if not PROFILE_PATH.exists():
            return {}
        with PROFILE_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return {}
        # Normalize keys to strings
        out: Dict[str, str] = {}
        for k, v in data.items():
            try:
                out[str(k).strip().lower()] = str(v)
            except Exception:
                continue
        return out
    except Exception:
        return {}


def _save_profile(profile: Dict[str, str]) -> None:
    """Persist the user profile to disk.

    The directory is created if missing.  Errors are ignored to
    avoid impacting callers.
    """
    try:
        PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        # Convert all keys/values to strings for consistency
        data = {str(k): str(v) for k, v in profile.items()}
        with PROFILE_PATH.open("w", encoding="utf-8") as fh:
            json.dump(data, fh)
    except Exception:
        return


def update_profile(key: str, value: str) -> None:
    """Update a single attribute in the user profile.

    Args:
        key: The attribute name.  Converted to lower‑case.
        value: The attribute value.  Converted to string.
    """
    try:
        k = str(key or "").strip().lower()
        v = str(value or "").strip()
        if not k:
            return
        profile = _load_profile()
        profile[k] = v
        _save_profile(profile)
    except Exception:
        return


def get_profile() -> Dict[str, str]:
    """Return the entire user profile as a dictionary.

    If no profile exists, returns an empty dict.
    """
    return _load_profile()


def get_attribute(key: str) -> Optional[str]:
    """Retrieve a single value from the user profile.

    Args:
        key: The attribute name (case‑insensitive).

    Returns:
        The stored value as a string, or None if the key is not present.
    """
    try:
        k = str(key or "").strip().lower()
        if not k:
            return None
        profile = _load_profile()
        return profile.get(k)
    except Exception:
        return None