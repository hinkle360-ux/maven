"""
Filesystem utility functions for Agent Executor
---------------------------------------------

This module provides simple helpers to read files, generate diffs and
apply new content with atomic backups.  The agent executor delegates
file operations through these functions to ensure consistency across
executions.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Tuple

# The agent tools are located under ``brains/agent/tools``.  To reach the Maven
# project root, go up four directories (tools -> agent -> brains -> maven).  Use
# that root to locate the shared ``reports/agent/backups`` directory.  If this
# file is moved, adjust the ``parents`` index accordingly.
BACKUP_ROOT = Path(__file__).resolve().parents[4] / "reports" / "agent" / "backups"
BACKUP_ROOT.mkdir(parents=True, exist_ok=True)


def read(path: str) -> str:
    """Read and return the contents of the given file.  Returns an empty string on error."""
    p = Path(path)
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return ""


def diff(path: str, new_text: str) -> str:
    """Compute a unified diff between the current contents of the file and the provided new text."""
    import difflib
    old_text = read(path)
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(old_lines, new_lines, fromfile=path, tofile=f"{path}.new", lineterm="")
    )


def apply(path: str, new_text: str) -> Tuple[str, str]:
    """Apply new_text to the file at the given path.  Returns a tuple (status, backup_path)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    backup_path = ""
    # Create backup if file exists
    if p.exists():
        ts = int(os.times().elapsed * 1000)
        backup = BACKUP_ROOT / f"{p.name}.{ts}.bak"
        try:
            shutil.copy2(p, backup)
            backup_path = str(backup)
        except Exception:
            backup_path = ""
    # Write new content atomically
    tmp_path = p.with_suffix(p.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as fh:
        fh.write(new_text)
    os.replace(tmp_path, p)
    return ("applied", backup_path)