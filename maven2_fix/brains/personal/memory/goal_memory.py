"""Goal Memory Module Wrapper
============================

This module provides a thin wrapper around the runtime goal_memory
implementation.  It re-exports all public functions to maintain
compatibility with existing imports throughout the codebase.

The actual implementation lives in runtime_memory/personal/memory/goal_memory.py.
This wrapper allows code to import from brains.personal.memory.goal_memory
without duplicating the implementation.
"""

from __future__ import annotations

# Import all public functions from the runtime implementation
import sys
from pathlib import Path

# Add runtime_memory to the Python path if not already present
_runtime_path = Path(__file__).resolve().parents[4] / "runtime_memory"
if str(_runtime_path) not in sys.path:
    sys.path.insert(0, str(_runtime_path))

try:
    from personal.memory.goal_memory import (
        add_goal,
        get_goals,
        complete_goal,
        get_goal,
        get_dependency_chain,
        summary,
        children_of,
        set_deadline,
        update_progress,
    )

    # Re-export all functions
    __all__ = [
        "add_goal",
        "get_goals",
        "complete_goal",
        "get_goal",
        "get_dependency_chain",
        "summary",
        "children_of",
        "set_deadline",
        "update_progress",
    ]
except ImportError as e:
    # If runtime implementation cannot be imported, provide stubs
    # to prevent cascading failures
    import warnings
    warnings.warn(
        f"Could not import goal_memory from runtime_memory: {e}. "
        "Using stub implementation.",
        RuntimeWarning
    )

    from typing import Any, Dict, List, Optional

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
        """Stub implementation: returns a minimal goal record."""
        import uuid
        import time
        return {
            "goal_id": str(uuid.uuid4()),
            "title": (title or "").strip(),
            "description": (description or "").strip(),
            "created_at": time.time(),
            "completed": False,
            "stub": True,
        }

    def get_goals(active_only: bool = False) -> List[Dict[str, Any]]:
        """Stub implementation: returns empty list."""
        return []

    def complete_goal(goal_id: str, *, success: bool = True) -> Optional[Dict[str, Any]]:
        """Stub implementation: returns None."""
        return None

    def get_goal(goal_id: str) -> Optional[Dict[str, Any]]:
        """Stub implementation: returns None."""
        return None

    def get_dependency_chain(goal_id: str) -> List[Dict[str, Any]]:
        """Stub implementation: returns empty list."""
        return []

    def summary() -> Dict[str, Any]:
        """Stub implementation: returns empty summary."""
        return {
            "total": 0,
            "active": 0,
            "completed": 0,
            "categories": {},
            "active_ids": [],
            "stub": True,
        }

    def children_of(parent_id: str) -> List[Dict[str, Any]]:
        """Stub implementation: returns empty list."""
        return []

    def set_deadline(goal_id: str, deadline_ts: float) -> Optional[Dict[str, Any]]:
        """Stub implementation: returns None."""
        return None

    def update_progress(
        goal_id: str,
        progress: float,
        *,
        metrics: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Stub implementation: returns None."""
        return None

    __all__ = [
        "add_goal",
        "get_goals",
        "complete_goal",
        "get_goal",
        "get_dependency_chain",
        "summary",
        "children_of",
        "set_deadline",
        "update_progress",
    ]
