"""Persistent synonym mapping for the Maven cognitive system.

This module maintains a simple mapping of informal terms or phrases to
canonical subject names.  It enables the system to answer questions
that refer to entities via nicknames or common epithets (e.g., "the red
planet" → "mars").  Synonyms are stored on disk in
``config/synonyms.json`` relative to the Maven project root.  The
mapping is case‑insensitive and returns lower‑cased canonical forms.

The API exposes helpers to lookup the canonical form of a term,
update the mapping with new synonym → canonical pairs, and retrieve
the entire mapping.  Failed reads/writes are silently ignored to
avoid interrupting the main cognitive pipeline.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Dict

# Compute the project root.  This file lives at
# brains/personal/memory/synonyms.py so the Maven root is
# three levels up (memory → personal → brains → maven).
HERE = Path(__file__).resolve()
MAVEN_ROOT = HERE.parents[3]

# Path to the persistent synonym mapping file.  Synonyms live under
# the ``config`` directory alongside other configuration files.
_SYN_PATH = MAVEN_ROOT / "config" / "synonyms.json"


def _load_mapping() -> Dict[str, str]:
    """Load the synonym mapping from disk.

    Returns:
        A dictionary mapping lower‑cased synonym strings to their
        canonical lower‑cased form.  Returns an empty dict if the file
        does not exist or cannot be parsed.
    """
    try:
        if _SYN_PATH.exists():
            with open(_SYN_PATH, "r", encoding="utf-8") as fh:
                data = json.load(fh) or {}
            # Normalize keys and values to lowercase strings
            mapping = {}
            for syn, canon in data.items():
                try:
                    s = str(syn).strip().lower()
                    c = str(canon).strip().lower()
                    if s and c:
                        mapping[s] = c
                except Exception:
                    continue
            return mapping
    except Exception:
        pass
    return {}


def _save_mapping(mapping: Dict[str, str]) -> None:
    """Persist the given mapping to disk.

    Args:
        mapping: A dictionary of synonym → canonical form (both lowercase).
    """
    try:
        _SYN_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_SYN_PATH, "w", encoding="utf-8") as fh:
            json.dump(mapping, fh, ensure_ascii=False, indent=2)
    except Exception:
        # Silently ignore write failures
        pass


def get_canonical(term: str) -> str:
    """Return the canonical form of a given term if a mapping exists.

    Args:
        term: The input term (case‑insensitive).

    Returns:
        The canonical form if found; otherwise the lower‑cased input term.
    """
    try:
        t = str(term or "").strip().lower()
    except Exception:
        t = ""
    if not t:
        return ""
    mapping = _load_mapping()
    # Return mapped value if exists, else the original lowercase term
    return mapping.get(t, t)


def update_synonym(synonym: str, canonical: str) -> None:
    """Update the synonym mapping with a new pair and persist it.

    Args:
        synonym: The informal term to map (e.g. "the red planet").
        canonical: The canonical name (e.g. "mars").

    This function lowercases and trims both terms before inserting.  If
    the canonical form is empty, the mapping is not updated.  Existing
    mappings with the same synonym will be overwritten.
    """
    try:
        syn_key = str(synonym or "").strip().lower()
        canon_val = str(canonical or "").strip().lower()
    except Exception:
        return
    if not syn_key or not canon_val:
        return
    mapping = _load_mapping()
    mapping[syn_key] = canon_val
    _save_mapping(mapping)

def remove_synonym(synonym: str) -> bool:
    """Remove a synonym mapping from the persistent store.

    Args:
        synonym: The synonym term to remove (case‑insensitive).

    Returns:
        True if the mapping was removed; False if the synonym was not
        present or an error occurred.
    """
    try:
        syn_key = str(synonym or "").strip().lower()
    except Exception:
        return False
    if not syn_key:
        return False
    mapping = _load_mapping()
    if syn_key not in mapping:
        return False
    try:
        mapping.pop(syn_key, None)
        _save_mapping(mapping)
        return True
    except Exception:
        return False

def list_groups() -> Dict[str, list[str]]:
    """Return synonym groups keyed by canonical form.

    This helper inverts the synonym mapping so that each canonical
    entity maps to a list of synonyms (including the canonical form
    itself).  The groups do not include duplicates and are sorted
    alphabetically.  If the mapping cannot be read, returns an
    empty dict.

    Returns:
        A dictionary mapping canonical strings to lists of synonyms.
    """
    mapping = _load_mapping()
    groups: Dict[str, list[str]] = {}
    for syn, canon in mapping.items():
        canon = canon.strip().lower()
        syn = syn.strip().lower()
        if not canon or not syn:
            continue
        groups.setdefault(canon, set()).add(syn)
    # Ensure each canonical is included as its own synonym
    for canon in list(groups.keys()):
        groups[canon].add(canon)
    # Convert sets to sorted lists
    out: Dict[str, list[str]] = {}
    for canon, syn_set in groups.items():
        out[canon] = sorted(syn_set)
    return out


def get_mapping() -> Dict[str, str]:
    """Return the entire synonym mapping.

    Returns:
        A dictionary of synonym → canonical form (both lowercase).  If
        the mapping cannot be read, returns an empty dict.
    """
    return _load_mapping()


def import_synonyms(data: object) -> int:
    """
    Import multiple synonym mappings at once.

    Args:
        data: A dictionary of synonym → canonical pairs or an iterable of
            `(synonym, canonical)` tuples/lists.  Strings are lower‑cased
            automatically.  Invalid entries (non‑string, empty) are
            skipped.

    Returns:
        The number of valid synonym mappings imported and persisted.
    """
    count = 0
    mapping: Dict[str, str] = _load_mapping()
    # Determine the type of input and iterate accordingly
    try:
        if isinstance(data, dict):
            items = data.items()
        else:
            # Assume iterable of pairs
            items = data
    except Exception:
        return 0
    for pair in items:
        try:
            if isinstance(pair, tuple) or isinstance(pair, list):
                syn, canon = pair
            else:
                syn, canon = pair, None
            syn_key = str(syn or "").strip().lower()
            canon_val = str(canon or "").strip().lower()
            if not syn_key or not canon_val:
                continue
            mapping[syn_key] = canon_val
            count += 1
        except Exception:
            continue
    # Persist the merged mapping
    if count > 0:
        _save_mapping(mapping)
    return count


def export_synonyms() -> Dict[str, str]:
    """Return a copy of the entire synonym mapping for export purposes.

    This helper simply wraps :func:`get_mapping` but ensures a new
    dictionary is returned to prevent accidental in‑place modifications.

    Returns:
        A copy of the current synonym mapping.
    """
    try:
        mapping = _load_mapping()
        return dict(mapping)
    except Exception:
        return {}