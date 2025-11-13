"""Goal Memory Module
======================

This module provides simple helpers for persisting and retrieving
long‑horizon goals.  Goals represent tasks or objectives that may span
multiple sessions.  Each goal is stored as a JSON object with an
identifier, title, optional description, creation time, completion flag
and completion timestamp.  Goals are persisted to a JSONL file on
disk so that they survive across runs.

Functions:

    add_goal(title, description=None) -> dict:
        Create a new goal record and append it to the goals file.  Returns
        the created record.

    get_goals(active_only=False) -> list[dict]:
        Retrieve all stored goals.  If ``active_only`` is True, only
        return goals that have not yet been completed.

    complete_goal(goal_id) -> dict | None:
        Mark the goal with the given ``goal_id`` as completed.  Returns the
        updated record or ``None`` if the goal does not exist.

The underlying storage file is ``goals.jsonl`` in the same directory
as this module.  Each line in the file is a JSON object representing
one goal.
"""

from __future__ import annotations
import json
import time
import uuid
from pathlib import Path
from typing import List, Dict, Optional, Any


# Determine the path to the goals file relative to this module.  This
# module lives in ``brains/personal/memory/goal_memory.py``.  Storing
# the file alongside the module ensures it persists within the same
# package.  We avoid referencing higher directories to keep the
# dependency simple and reduce coupling to the overall project layout.
_GOALS_PATH: Path = Path(__file__).resolve().with_name("goals.jsonl")


def _read_all() -> List[dict]:
    """Return a list of all goal records from disk.

    If the goals file does not exist or is unreadable, return an empty
    list.  Each record is a dict parsed from JSON.

    Returns:
        List of goal dictionaries.
    """
    if not _GOALS_PATH.exists():
        return []
    records: List[dict] = []
    try:
        with _GOALS_PATH.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if isinstance(rec, dict):
                        records.append(rec)
                except Exception:
                    # Skip malformed lines rather than failing
                    continue
    except Exception:
        return []
    return records


def _write_all(records: List[dict]) -> None:
    """
    Write the given list of goal records to disk atomically.

    To improve crash safety, this helper writes to a temporary file
    first then replaces the original ``goals.jsonl``.  This reduces
    the chance of leaving a partially written file if the process is
    interrupted.  Errors are silently ignored.

    Args:
        records: List of goal dictionaries to write.
    """
    try:
        _GOALS_PATH.parent.mkdir(parents=True, exist_ok=True)
        import os, uuid, json as _json
        tmp_path = _GOALS_PATH.parent / f".{_GOALS_PATH.name}.{uuid.uuid4().hex}.tmp"
        # Write all records to the temp file
        with tmp_path.open("w", encoding="utf-8") as fh:
            for rec in records:
                try:
                    _json.dump(rec, fh)
                    fh.write("\n")
                except Exception:
                    continue
        # Atomically replace the original file
        try:
            os.replace(tmp_path, _GOALS_PATH)
        except Exception:
            # On failure, attempt to remove the temp file
            try:
                os.remove(tmp_path)
            except Exception:
                pass
    except Exception:
        # Ignore all errors to avoid crashing the system
        pass


def add_goal(
    title: str,
    description: Optional[str] = None,
    *,
    depends_on: Optional[List[str]] = None,
    condition: Optional[str] = None,
    parent_id: Optional[str] = None,
    deadline_ts: Optional[float] = None,
    progress: Optional[float] = None,
    metrics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create and persist a new goal.

    A goal represents a long‑horizon task that may span multiple
    sessions.  In addition to the title and description, callers may
    specify a list of goal identifiers that this goal depends on.  A
    dependent goal will not be eligible for autonomous execution until
    all of its dependencies have been marked as completed.  The
    ``depends_on`` field is persisted alongside the goal record.

    Args:
        title: A short description of the goal.  Leading and trailing
            whitespace is stripped.
        description: Optional longer description of the goal.
        depends_on: Optional list of goal IDs that must be completed
            before this goal can be executed.  Duplicate identifiers
            are removed.
        condition: Optional condition flag for this goal.  When
            specified, the goal will only become eligible for
            autonomous execution if the conditions of its dependencies
            are satisfied.  Valid values are ``"success"`` (run
            only if all dependencies completed successfully),
            ``"failure"`` (run only if dependencies completed but
            failed), or None (default) for unconditional execution.

    Returns:
        The goal record that was created.  Persistence errors are
        swallowed silently; the returned record will still include the
        generated identifier and provided fields.
    """
    now = time.time()
    # ------------------------------------------------------------------
    # Duplicate goal suppression
    #
    # Before creating a new goal, scan the existing goal file for any
    # record whose title normalises to the same string as the proposed
    # title.  Normalisation removes whitespace and punctuation and
    # converts to lower case.  If a matching goal is found, return
    # that record instead of creating a duplicate.  This prevents
    # self‑repair mechanisms from spawning dozens of identical tasks
    # (e.g. "Verify QA: What is 2+2?" vs "Verify QA: What is 2 + 2").
    try:
        import re as _re_norm
        norm_new = _re_norm.sub(r"[^a-z0-9]", "", (title or "").lower())
        existing_rec = None
        if _GOALS_PATH.exists():
            with _GOALS_PATH.open("r", encoding="utf-8") as _fh:
                for _line in _fh:
                    if not _line.strip():
                        continue
                    try:
                        _rec = json.loads(_line)
                    except Exception:
                        continue
                    try:
                        _t = str(_rec.get("title", "")).strip().lower()
                    except Exception:
                        _t = ""
                    if not _t:
                        continue
                    _norm = _re_norm.sub(r"[^a-z0-9]", "", _t)
                    if _norm == norm_new:
                        existing_rec = _rec
                        break
        if existing_rec:
            # Return the existing record without modification
            return existing_rec
    except Exception:
        # On any error (e.g., IO), fall back to creating a new goal
        pass
    # Normalise the depends_on list: remove None/empty values and
    # duplicates while preserving order.  If depends_on is None, store
    # an empty list in the record.
    dep_ids: List[str] = []
    if depends_on:
        seen: set[str] = set()
        for dep in depends_on:
            if not dep or not isinstance(dep, str):
                continue
            if dep in seen:
                continue
            seen.add(dep)
            dep_ids.append(dep)
    # Compute a priority score for this goal.  The score can be provided
    # externally via the metrics dict under the 'priority' key.  When
    # absent, infer a priority based on the description or title.  A
    # simple heuristic assigns high priority (2) to goals containing
    # 'AUTO_REPAIR', medium (1) to those starting with 'DELEGATED_TO:',
    # and low (0) otherwise.  The autonomy brain will incorporate
    # this field when scheduling goals.
    try:
        explicit_priority = None
        # metrics may be provided and contain priority
        if metrics and isinstance(metrics, dict) and "priority" in metrics:
            explicit_priority = metrics.get("priority")
        if explicit_priority is None:
            # Inspect title and description for cues
            t_up = str((title or "")).strip().upper()
            d_up = str((description or "")).strip().upper()
            if "AUTO_REPAIR" in t_up or "AUTO_REPAIR" in d_up:
                explicit_priority = 2
            elif t_up.startswith("DELEGATED_TO:") or d_up.startswith("DELEGATED_TO:"):
                explicit_priority = 1
            else:
                explicit_priority = 0
    except Exception:
        explicit_priority = 0
    # Build the new goal record.  Persist the explicit priority in both
    # the root-level field and inside the metrics dict so that the
    # autonomous scheduler can sort by metrics['priority'].  When
    # ``metrics`` already contains a priority value, it is left intact
    # to allow callers to override the heuristic.  Otherwise, the
    # computed explicit_priority is inserted.
    _metrics: Dict[str, Any] = metrics.copy() if isinstance(metrics, dict) else {}
    # Populate the priority in metrics if not provided
    try:
        if "priority" not in _metrics or _metrics.get("priority") is None:
            _metrics["priority"] = explicit_priority
    except Exception:
        _metrics["priority"] = explicit_priority
    rec: Dict[str, Any] = {
        "goal_id": str(uuid.uuid4()),
        "title": (title or "").strip(),
        "description": (description or "").strip(),
        "created_at": now,
        "completed": False,
        "completed_at": None,
        "depends_on": dep_ids,
        "condition": (condition or None),
        "success": None,
        "parent_id": parent_id or None,
        "deadline_ts": deadline_ts if deadline_ts else None,
        "progress": float(progress) if progress is not None else None,
        "metrics": _metrics,
        # Retain a root-level priority field for backwards compatibility
        "priority": explicit_priority,
    }
    # Cycle detection: verify that adding this goal does not introduce
    # dependency cycles.  Build an adjacency map of existing goals and
    # perform DFS to see if the new goal is reachable from any of its
    # dependencies.  A cycle occurs when a dependency leads back to
    # this goal.
    try:
        existing = _read_all()
        # adjacency: node -> list of dependencies
        adj: Dict[str, List[str]] = {}
        for g in existing:
            gid = g.get("goal_id")
            deps = g.get("depends_on", []) or []
            if gid:
                adj[str(gid)] = [str(d) for d in deps if d]
        # include the new goal dependencies in the graph
        adj[rec["goal_id"]] = [str(d) for d in dep_ids]
        def _has_path(start: str, target: str, visited: set[str]) -> bool:
            if start == target:
                return True
            if start in visited:
                return False
            visited.add(start)
            for nxt in adj.get(start, []):
                if _has_path(nxt, target, visited):
                    return True
            return False
        cycle = False
        for dep in dep_ids:
            if _has_path(dep, rec["goal_id"], set()):
                cycle = True
                break
        if cycle:
            # Mark the record with an error and do not persist
            rec["cycle_error"] = True
            rec["error_message"] = "Cyclic dependency detected; goal not added."
            return rec
    except Exception:
        # On any exception, proceed without cycle detection
        pass
    # Persist the new goal atomically.  Read existing, append and write.
    try:
        records = existing + [rec] if 'existing' in locals() else _read_all() + [rec]
        _write_all(records)
    except Exception:
        # If writing fails, return the record without persisting
        return rec
    return rec


def get_goals(active_only: bool = False) -> List[Dict[str, Any]]:
    """Return all stored goals.

    Args:
        active_only: If True, only return goals that are not completed.
            Defaults to False.

    Returns:
        A list of goal records.  If no goals are stored, returns an
        empty list.
    """
    records = _read_all()
    if active_only:
        return [rec for rec in records if not rec.get("completed", False)]
    return records


def complete_goal(goal_id: str, *, success: bool = True) -> Optional[Dict[str, Any]]:
    """Mark the specified goal as completed.

    Args:
        goal_id: The identifier of the goal to complete.
        success: If True, mark the goal as completed successfully;
            if False, mark it as completed unsuccessfully.  This
            success flag is used by dependent goals with conditional
            execution.

    Returns:
        The updated goal record if found and updated, else None.
    """
    if not goal_id:
        return None
    records = _read_all()
    updated: Optional[Dict[str, Any]] = None
    now = time.time()
    for rec in records:
        if rec.get("goal_id") == goal_id:
            rec["completed"] = True
            rec["completed_at"] = now
            rec["success"] = bool(success)
            updated = rec
            # Do not break; update all matching IDs (though there should
            # typically be only one).
    # Rewrite the file with updated records.  Overwrite even if the
    # goal wasn't found so that any other write operations persist.
    _write_all(records)
    return updated

# ------------------------------------------------------------------------------
# Additional helper functions for goal introspection
#
def get_goal(goal_id: str) -> Optional[Dict[str, Any]]:
    """Return the goal record with the given identifier.

    This helper scans all stored goals and returns the first record
    whose ``goal_id`` matches the provided value.  If no matching goal
    is found, returns None.  Callers should treat the returned
    dictionary as read‑only and avoid mutating it directly.

    Args:
        goal_id: Unique identifier of the goal to fetch.

    Returns:
        The goal dictionary if found, else None.
    """
    if not goal_id:
        return None
    records = _read_all()
    for rec in records:
        if rec.get("goal_id") == goal_id:
            return rec
    return None


def get_dependency_chain(goal_id: str) -> List[Dict[str, Any]]:
    """Return the chain of dependency records for the given goal.

    Starting from the specified goal, this function walks backwards
    through the ``depends_on`` fields to build an ordered list of
    dependency records.  The list starts with the immediate
    dependencies of the given goal and continues until there are no
    further dependencies.  Cycles are ignored (repeated IDs are
    skipped).  If a dependency cannot be found, it is omitted.

    Args:
        goal_id: Identifier of the goal for which to compute the
            dependency chain.

    Returns:
        A list of goal records representing the chain of dependencies.
        The order is from closest (direct) dependency to the most
        distant ancestor.  If the goal has no dependencies or the
        identifier is invalid, returns an empty list.
    """
    chain: List[Dict[str, Any]] = []
    seen: set[str] = set()
    # Start from the given goal and accumulate dependencies
    current_id = goal_id
    while current_id:
        rec = get_goal(current_id)
        if not rec:
            break
        deps = rec.get("depends_on") or []
        # We only follow the first dependency if multiple are listed
        # for the purposes of a simple chain.  This avoids combinatorial
        # explosion; callers can inspect the record for the full list.
        next_id: Optional[str] = None
        for dep_id in deps:
            if dep_id and dep_id not in seen:
                next_id = dep_id
                seen.add(dep_id)
                # Append the dependency record to the chain
                dep_rec = get_goal(dep_id)
                if dep_rec:
                    chain.append(dep_rec)
                break
        if not next_id:
            break
        current_id = next_id
    return chain


def summary() -> Dict[str, Any]:
    """Return a summary of stored goals by status and category.

    The summary includes counts of total, active and completed goals,
    as well as a breakdown by category inferred from the ``description``
    prefix.  Categories correspond to common patterns such as
    ``AUTO_REPAIR`` for self‑repair tasks, ``DELEGATED_TO:<peer>`` for
    delegated tasks, and ``SELF_REVIEW`` for self‑improvement tasks.
    ``GENERAL`` is used for all other goals.  The summary also
    includes the list of active goal IDs.

    Returns:
        A dictionary containing counts and lists summarising the goal
        memory.
    """
    records = _read_all()
    total = len(records)
    active = 0
    completed = 0
    categories: Dict[str, int] = {}
    active_ids: List[str] = []
    for rec in records:
        if rec.get("completed", False):
            completed += 1
        else:
            active += 1
            goal_id = rec.get("goal_id")
            if goal_id:
                active_ids.append(goal_id)
        # Determine category based on description prefix
        descr = (rec.get("description") or "").strip().upper()
        cat = "GENERAL"
        if descr.startswith("AUTO_REPAIR"):
            cat = "AUTO_REPAIR"
        elif descr.startswith("DELEGATED_TO"):
            cat = "DELEGATED"
        elif descr.startswith("SELF_REVIEW"):
            cat = "SELF_REVIEW"
        categories[cat] = categories.get(cat, 0) + 1
    return {
        "total": total,
        "active": active,
        "completed": completed,
        "categories": categories,
        "active_ids": active_ids,
    }

# ------------------------------------------------------------------------------
# Extended helper functions for hierarchical goals and scheduling

def children_of(parent_id: str) -> List[Dict[str, Any]]:
    """Return a list of goals whose parent_id matches the given id.

    This helper scans all stored goals and returns those whose
    ``parent_id`` field equals the provided identifier.  The returned
    list may be empty if no children exist.  Children goals may have
    their own dependencies or conditions.

    Args:
        parent_id: The parent goal identifier to search for.

    Returns:
        A list of goal records that are children of the specified parent.
    """
    if not parent_id:
        return []
    records = _read_all()
    children: List[Dict[str, Any]] = []
    for rec in records:
        if rec.get("parent_id") == parent_id:
            children.append(rec)
    return children


def set_deadline(goal_id: str, deadline_ts: float) -> Optional[Dict[str, Any]]:
    """Set or update the deadline for the specified goal.

    Args:
        goal_id: Identifier of the goal to update.
        deadline_ts: Absolute timestamp (seconds since epoch) representing
            the deadline.  If None or not finite, the deadline will be removed.

    Returns:
        The updated goal record if found, else None.
    """
    if not goal_id:
        return None
    records = _read_all()
    updated: Optional[Dict[str, Any]] = None
    for rec in records:
        if rec.get("goal_id") == goal_id:
            if deadline_ts is None or not isinstance(deadline_ts, (int, float)):
                rec["deadline_ts"] = None
            else:
                rec["deadline_ts"] = float(deadline_ts)
            updated = rec
            break
    _write_all(records)
    return updated


def update_progress(goal_id: str, progress: float, *, metrics: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Update progress and optionally metrics for a goal.

    Progress values are clamped between 0.0 and 1.0.  Metrics provided
    must be a dictionary of JSON‑serialisable values; any non‑dict
    metrics are ignored.  If metrics is provided, it will be merged
    with existing metrics, overwriting duplicate keys.

    Args:
        goal_id: Identifier of the goal to update.
        progress: New progress value (0.0–1.0).
        metrics: Optional dictionary of additional metrics to store.

    Returns:
        The updated goal record if found, else None.
    """
    if not goal_id:
        return None
    try:
        progress_val = float(progress)
    except Exception:
        progress_val = None
    # Clamp progress between 0 and 1
    if progress_val is not None:
        if progress_val < 0.0:
            progress_val = 0.0
        elif progress_val > 1.0:
            progress_val = 1.0
    records = _read_all()
    updated: Optional[Dict[str, Any]] = None
    for rec in records:
        if rec.get("goal_id") == goal_id:
            if progress_val is not None:
                rec["progress"] = progress_val
            if metrics and isinstance(metrics, dict):
                # Merge metrics dictionaries
                existing = rec.get("metrics") if isinstance(rec.get("metrics"), dict) else {}
                merged = existing.copy()
                for k, v in metrics.items():
                    try:
                        json.dumps({k: v})
                        merged[k] = v
                    except Exception:
                        continue
                rec["metrics"] = merged
            updated = rec
            break
    _write_all(records)
    return updated