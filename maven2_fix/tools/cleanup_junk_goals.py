#!/usr/bin/env python3
"""Cleanup script for removing legacy junk goals.

This script scans the goal memory for tasks that are recognised as
artefacts of earlier segmentation bugs (e.g. single digits, colour
names, short question fragments) and marks them as completed.  A
summary of removed goals is written to ``reports/goal_cleanup/`` with
a timestamped filename.

Usage:

    python3 maven/tools/cleanup_junk_goals.py

Run this once to clean up existing junk goals.  The main pipeline
already prunes junk tasks during execution.
"""
from __future__ import annotations
import json
import re
import time
import sys
from pathlib import Path
from typing import List, Dict, Any

def _is_junk(title: str) -> bool:
    """Return True if the given goal title is considered junk.

    Heuristics match single numbers, isolated spectrum colour names,
    specific prefixes and very short question fragments.
    """
    try:
        t = str(title or "").strip().lower()
    except Exception:
        return False
    if not t:
        return False
    # Numeric
    if re.fullmatch(r"\d+", t):
        return True
    # Colour names
    if t in {"red", "orange", "yellow", "green", "blue", "indigo", "violet"}:
        return True
    # Known prefixes
    if t.startswith("numbers from") or t.startswith("what comes"):
        return True
    # Very short question fragments ending with a question mark
    if t.endswith("?") and len(t) <= 5:
        return True
    return False

def main() -> None:
    # Determine the Maven root relative to this script
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    # Import goal memory
    try:
        from brains.personal.memory import goal_memory  # type: ignore
    except Exception as e:
        print(f"Error: failed to import goal memory: {e}")
        return
    # Fetch all active goals
    try:
        active = goal_memory.get_goals(active_only=True)  # type: ignore[attr-defined]
    except Exception as e:
        print(f"Error: failed to read goals: {e}")
        return
    removed: List[Dict[str, Any]] = []
    kept: List[Dict[str, Any]] = []
    for g in active:
        title = str(g.get("title", ""))
        if _is_junk(title):
            gid = g.get("goal_id")
            if gid:
                try:
                    goal_memory.complete_goal(str(gid), success=True)  # type: ignore[attr-defined]
                    removed.append({"goal_id": gid, "title": title})
                    continue
                except Exception:
                    pass
        kept.append(g)
    # Write summary of removed goals
    if removed:
        try:
            report_dir = root / "reports" / "goal_cleanup"
            report_dir.mkdir(parents=True, exist_ok=True)
            ts = int(time.time())
            out_path = report_dir / f"removed_goals_{ts}.json"
            with open(out_path, "w", encoding="utf-8") as fh:
                json.dump(removed, fh, indent=2)
            print(f"Removed {len(removed)} junk goals.  Summary written to {out_path}.")
        except Exception:
            print(f"Removed {len(removed)} junk goals.")
    else:
        print("No junk goals found to remove.")

if __name__ == "__main__":
    main()
