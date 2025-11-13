"""
Replanner Brain
===============

This module provides a simple re‑planning mechanism for incomplete goals.  It
accepts a list of goals (as persisted in the personal goal memory) and
attempts to break compound tasks into smaller, more manageable actions.  The
replanner is intentionally conservative: it only splits goal titles on
conjunctions like "and" or "then" and discards empty segments.  When new
sub‑goals are generated they are added to the goal memory for future
execution.

Operations
----------

    REPLAN
        Given a list of goal dictionaries, return a list of newly created
        sub‑goals.  Each dictionary in the payload should include at least a
        ``title`` field.  Additional fields are ignored.  If no goals are
        provided or no splits are possible, an empty list is returned.

Example::

    from brains.cognitive.planner.service.replanner_brain import service_api
    goals = [ {"goal_id": "123", "title": "gather data and analyze it"} ]
    resp = service_api({"op": "REPLAN", "payload": {"goals": goals}})
    # resp["payload"]["new_goals"] might be something like
    # [ {"goal_id": "NEW-0001", "title": "gather data"}, {"goal_id": "NEW-0002", "title": "analyze it"} ]

The replanner uses the same ``goal_memory`` module as the planner to persist
new goals.  If goal memory is unavailable, replanning silently degrades to
returning the original goals unchanged.
"""

from __future__ import annotations

from typing import Dict, Any, List
import itertools

# Counter for assigning IDs to new sub‑goals.  New goals are prefixed with
# "REP-" to distinguish them from planner goals.  This is purely cosmetic and
# does not impact scheduling.
_replan_counter = itertools.count(1)


def _split_goal_title(title: str) -> List[str]:
    """Split a goal title on conjunctions and commas.

    Returns a list of non‑empty segments.  Only splits when multiple segments
    are detected.  If the title contains no conjunctions or only yields a
    single segment, the original title is returned in a single‑element list.

    Args:
        title: The goal title to split.

    Returns:
        A list of one or more strings representing sub‑tasks.
    """
    try:
        import re
        # Normalise whitespace
        t = (title or "").strip()
        # First detect conditional pattern: if X then Y
        cond_match = re.search(r"\bif\s+(.+?)\s+then\s+(.+)", t, flags=re.IGNORECASE)
        if cond_match:
            cond = cond_match.group(1).strip()
            act = cond_match.group(2).strip()
            out: List[str] = []
            if cond:
                out.append(cond)
            if act:
                out.append(act)
            return out if out else [t]
        # Otherwise split on "and"/"then"/commas
        parts = [p.strip() for p in re.split(r"\b(?:and|then)\b|,", t, flags=re.IGNORECASE) if p and p.strip()]
        if len(parts) <= 1:
            return [t]
        return parts
    except Exception:
        return [title or ""]


def service_api(msg: Dict[str, Any]) -> Dict[str, Any]:
    """Entry point for the replanner brain.

    Supports the ``REPLAN`` operation which takes a list of goal dictionaries
    and returns new sub‑goals for any compound goal titles.  New goals are
    written to the personal goal memory.  Unknown operations return an
    error.

    Args:
        msg: A message dictionary containing an ``op`` key and optional
            ``payload``.

    Returns:
        A response dictionary with ``ok`` status and operation name.  On
        success, the payload contains a list of new goals under ``new_goals``.
        On failure, ``error`` describes the issue.
    """
    op = (msg or {}).get("op", "").upper()
    payload = (msg or {}).get("payload", {}) or {}
    if op != "REPLAN":
        return {"ok": False, "op": op, "error": "unsupported_operation"}
    goals = payload.get("goals") or []
    new_goals: List[Dict[str, Any]] = []
    # Import goal memory lazily to avoid dependency issues when unused
    try:
        from brains.personal.memory import goal_memory  # type: ignore
    except Exception:
        goal_memory = None  # type: ignore
    for g in goals:
        title = str(g.get("title", "")).strip()
        if not title:
            continue
        parts = _split_goal_title(title)
        # Only split if multiple parts are returned.  When splitting, we
        # chain the resulting sub‑goals by specifying a dependency on
        # the immediately preceding sub‑goal.  The first segment has
        # no dependencies.  Each sub‑goal is persisted via the goal
        # memory and the returned record's identifier is used to set
        # dependencies for subsequent segments.
        if len(parts) > 1:
            # Determine if a conditional split should set conditions on
            # subsequent goals.  When the original title matches "if X then Y",
            # we apply a "success" condition to Y.  Otherwise, all parts
            # are unconditional.
            try:
                import re
                t = str(title).strip()
                cond_match = re.search(r"\bif\s+(.+?)\s+then\s+(.+)", t, flags=re.IGNORECASE)
                if cond_match:
                    cond_flags: List[Optional[str]] = [None, "success"]
                else:
                    cond_flags = [None for _ in parts]
            except Exception:
                cond_flags = [None for _ in parts]
            prev_id: str | None = None
            for part, cond_flag in zip(parts, cond_flags):
                created_rec: Dict[str, Any] | None = None
                # Persist the new goal in personal memory if available
                if goal_memory is not None:
                    try:
                        rec = goal_memory.add_goal(
                            part,
                            depends_on=[prev_id] if prev_id else None,
                            condition=cond_flag,
                        )
                        created_rec = rec
                        prev_id = rec.get("goal_id") if isinstance(rec, dict) else prev_id
                    except Exception:
                        created_rec = None
                # Create a new goal dict for return.  Use the created
                # record's goal_id if available; otherwise fall back to
                # synthetic REP prefix
                if created_rec and isinstance(created_rec, dict) and created_rec.get("goal_id"):
                    new_goal_id = created_rec["goal_id"]
                else:
                    new_goal_id = f"REP-{next(_replan_counter):04d}"
                new_goal = {
                    "goal_id": new_goal_id,
                    "title": part,
                    "status": "pending",
                }
                new_goals.append(new_goal)
    return {"ok": True, "op": op, "payload": {"new_goals": new_goals}}

# Ensure the replanner brain exposes a `handle` entry point
try:
    handle = service_api  # type: ignore[assignment]
    service_api = handle  # type: ignore[assignment]
except Exception:
    pass