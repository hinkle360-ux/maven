"""
Shell utility functions for Agent Executor
----------------------------------------

This module wraps subprocess invocation with sensible defaults and
timeouts.  The agent executor should use these helpers for all shell
commands to ensure consistent logging and error handling.
"""

from __future__ import annotations

import subprocess
import shlex
from pathlib import Path
from typing import Dict, Any


def run(cmd: str, cwd: str | None = None, timeout: int = 120) -> Dict[str, Any]:
    """
    Execute a shell command and return a result dictionary.  Prior to
    execution the command string is checked against a deny‑list of
    dangerous patterns (e.g. destructive system commands, pipes or
    redirection).  If any banned pattern is present, the command is
    rejected and an error is returned.  This provides a minimal
    safeguard against arbitrary command injection while still
    supporting benign introspection tasks (e.g. listing files).

    Parameters
    ----------
    cmd: str
        Command to execute.
    cwd: Optional[str]
        Working directory in which to execute the command.  Defaults to
        the Maven root directory (four levels up from this file).
    timeout: int
        Maximum time in seconds to allow the command to run.
    """
    # Determine project root for default working directory
    if cwd is None:
        cwd = str(Path(__file__).resolve().parents[4])
    try:
        # Load deny patterns from tool policy configuration.  If the
        # policy file cannot be read, fall back to a built‑in list.
        deny_patterns = []
        try:
            from pathlib import Path as _Path
            import json as _json
            policy_path = _Path(__file__).resolve().parents[4] / "config" / "tool_policy.json"
            if policy_path.exists():
                with open(policy_path, "r", encoding="utf-8") as fh:
                    data = _json.load(fh) or {}
                    dp = data.get("shell_policy", {}) or {}
                    deny_patterns = dp.get("deny_patterns") or []
        except Exception:
            deny_patterns = []
        if not deny_patterns:
            # Default deny patterns cover destructive or risky operations
            deny_patterns = [
                "rm ", " sudo", "reboot", "shutdown", "mkfs", "passwd",
                "wget", "curl", "ftp", "ssh", "|", ";", "&&", "||", ">"
            ]
        # Normalise command for scanning
        cmd_lc = str(cmd or "").lower()
        for pattern in deny_patterns:
            try:
                if pattern.strip() and pattern.strip().lower() in cmd_lc:
                    return {
                        "status": "error",
                        "error": f"Command contains banned pattern '{pattern.strip()}'."
                    }
            except Exception:
                continue
        # Execute the command safely using subprocess.  We avoid shell=True to
        # mitigate injection risks and rely on shlex.split for proper tokenisation.
        proc = subprocess.run(
            shlex.split(cmd), cwd=cwd, capture_output=True, text=True, timeout=timeout
        )
        return {
            "status": "completed",
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}