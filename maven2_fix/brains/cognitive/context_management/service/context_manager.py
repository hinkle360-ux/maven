"""
Context Management
===================

This module implements simple context management utilities for the
Maven cognitive architecture.  Context refers to the mutable
pipeline state that accumulates information across stages and turns.
Without management, context can grow indefinitely and bias future
decisions.  The functions here implement basic temporal decay and
reconstruction heuristics.

Features include:

* ``apply_decay`` – reduce the influence of old numeric fields by
  multiplying them by a decay factor.
* ``reconstruct_context`` – merge a list of prior context snapshots
  into a fresh context, preferring newer values and combining lists.

These helpers are intentionally lightweight.  They can be extended
in future releases to support more sophisticated decay functions
(e.g. exponential, contextual) or to persist and retrieve context
across sessions.
"""

from __future__ import annotations

from typing import Any, Dict, List, Iterable


def apply_decay(ctx: Dict[str, Any], decay: float = 0.9) -> Dict[str, Any]:
    """Apply temporal decay to numeric fields in a context dictionary.

    Numeric values (ints or floats) are multiplied by the provided
    decay factor, reducing their magnitude over time.  Nested
    dictionaries are decayed recursively.  Non‑numeric fields are
    preserved unchanged.

    Args:
        ctx: The context dictionary to decay.
        decay: A multiplicative factor between 0 and 1.  Values
            closer to zero cause faster forgetting.
    Returns:
        A new dictionary with decayed values; the original context is
        not modified.
    """
    if not isinstance(ctx, dict):
        return {}
    decayed: Dict[str, Any] = {}
    for key, value in ctx.items():
        if isinstance(value, dict):
            decayed[key] = apply_decay(value, decay)
        elif isinstance(value, (int, float)):
            decayed[key] = value * decay
        else:
            decayed[key] = value
    return decayed


def reconstruct_context(history: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Reconstruct a context from a sequence of prior contexts.

    When resuming a long session, it may be necessary to combine
    multiple context snapshots (e.g. from previous turns) into a
    single current context.  This function iterates through the
    provided contexts in order, merging their keys.  Later contexts
    override earlier ones for scalar values.  For lists, values are
    concatenated.  Nested dictionaries are merged recursively.

    Args:
        history: An iterable of context dictionaries ordered from
            oldest to newest.
    Returns:
        A single context dictionary representing the merged result.
    """
    merged: Dict[str, Any] = {}
    for ctx in history:
        if not isinstance(ctx, dict):
            continue
        for key, value in ctx.items():
            if key not in merged:
                merged[key] = value
            else:
                existing = merged[key]
                # If both are dicts, merge recursively
                if isinstance(existing, dict) and isinstance(value, dict):
                    merged[key] = reconstruct_context([existing, value])
                # If both are lists, append new items
                elif isinstance(existing, list) and isinstance(value, list):
                    merged[key] = existing + value
                # Otherwise, prefer the newer value
                else:
                    merged[key] = value
    return merged