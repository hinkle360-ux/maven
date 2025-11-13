"""
Tool Orchestrator
=================

This module provides a simple orchestrator for executing tasks using
registered tools.  Each task dictionary supplied by the task
decomposer specifies a ``task`` name which is mapped to a corresponding
tool.  For now, tools are stubs that return a placeholder result.
In future phases, this orchestrator will coordinate calls to the
cognitive brains, domain banks and external APIs.
"""

from __future__ import annotations

from typing import Dict, Any, Optional


class StubTool:
    """A placeholder tool that returns a fixed message."""
    def __init__(self, name: str) -> None:
        self.name = name

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "success": True,
            "result": f"Executed {self.name} task with args: {task}"
        }


class ToolOrchestrator:
    """Coordinate execution of tasks via a registry of tools."""

    def __init__(self) -> None:
        """Initialise the tool orchestrator and load policy configuration.

        The orchestrator constructs a registry of available tool stubs and
        reads an allow‑list and per‑tool resource limits from a
        configuration file.  The configuration file is expected at
        ``config/tools.json`` relative to the Maven project root and may
        contain the following keys:

        - ``allowed``: a list of tool names permitted for execution.  When
          specified, only these tools may be invoked.  If omitted or
          empty, the orchestrator falls back to the legacy
          ``tool_policy.json`` configuration or the full registry.
        - ``denied``: a list of tool names that are explicitly
          disallowed.  A denied tool will never be executed.
        - ``limits``: a mapping from tool name to an integer count
          representing the maximum number of times that tool may be
          executed in a single session.  Once the count is exceeded,
          additional calls will be rejected.

        Any errors during configuration loading are swallowed so as not
        to disrupt the orchestrator.  In that case, all registered tools
        are allowed and unlimited by default.
        """
        # Registry of available tools.  Keys are task names; values are
        # tool objects providing an ``execute`` method.  Populated with
        # stubs here; concrete implementations are registered elsewhere.
        self.tools: Dict[str, StubTool] = {
            "search_memory": StubTool("search_memory"),
            "search_knowledge_graph": StubTool("search_knowledge_graph"),
            "synthesize_findings": StubTool("synthesize_findings"),
            "store_results": StubTool("store_results"),
            "load_data": StubTool("load_data"),
            "apply_analysis": StubTool("apply_analysis"),
            "generate_report": StubTool("generate_report"),
            "plan_creation": StubTool("plan_creation"),
            "execute_creation": StubTool("execute_creation"),
            "review_creation": StubTool("review_creation"),
            # Additional tool names may be registered here (e.g., python_exec)
        }
        # Initialise allow/deny lists and limits
        self.allowed_tasks: set[str] = set()
        self.denied_tasks: set[str] = set()
        self.tool_limits: Dict[str, int] = {}
        self.tool_usage: Dict[str, int] = {}
        # Attempt to load extended tool policy from config/tools.json
        try:
            from pathlib import Path
            import json as _json
            # Determine the Maven project root (parents[4])
            root = Path(__file__).resolve().parents[4]
            cfg_path = root / "config" / "tools.json"
            data: Dict[str, Any] = {}
            if cfg_path.exists():
                with open(cfg_path, "r", encoding="utf-8") as fh:
                    data = _json.load(fh) or {}
            allowed = data.get("allowed") or []
            denied = data.get("denied") or []
            limits = data.get("limits") or {}
            # Normalise allow/deny lists
            self.allowed_tasks = {str(t).strip() for t in allowed if t}
            self.denied_tasks = {str(t).strip() for t in denied if t}
            # Convert limits to ints
            for name, val in limits.items():
                try:
                    self.tool_limits[str(name).strip()] = int(val)
                except Exception:
                    continue
        except Exception:
            # On error, fall back to legacy tool policy file
            try:
                from pathlib import Path
                import json as _json
                root = Path(__file__).resolve().parents[4]
                policy_path = root / "config" / "tool_policy.json"
                allowed: list[str] = []
                if policy_path.exists():
                    with open(policy_path, "r", encoding="utf-8") as fh:
                        data = _json.load(fh) or {}
                        allowed = data.get("allowed_tasks") or []
                if allowed:
                    self.allowed_tasks = {str(a).strip() for a in allowed if a}
                else:
                    self.allowed_tasks = set(self.tools.keys())
            except Exception:
                self.allowed_tasks = set(self.tools.keys())
        # If no explicit allowed list loaded, default to all registered tools
        if not self.allowed_tasks:
            self.allowed_tasks = set(self.tools.keys())
        # Remove any denied tools from the allowed set
        self.allowed_tasks -= self.denied_tasks

    def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single task by invoking the appropriate tool.

        Args:
            task: A dictionary describing the task to perform.  It must
                contain a ``task`` key whose value maps to a registered
                tool name.

        Returns:
            A dictionary with keys ``success`` and either ``result`` or
            ``error``.
        """
        tool_name = task.get("task")
        if not tool_name:
            return {"success": False, "error": "Task missing 'task' field"}
        # Normalise tool name
        try:
            name_norm = str(tool_name).strip()
        except Exception:
            name_norm = ""
        # Enforce deny list first
        if name_norm in self.denied_tasks:
            return {
                "success": False,
                "error": f"Task '{tool_name}' is explicitly denied by policy"
            }
        # Enforce allow list.  Disallowed tasks are not executed, even if a stub exists.
        if name_norm not in self.allowed_tasks:
            return {
                "success": False,
                "error": f"Task '{tool_name}' is not permitted by policy"
            }
        # Enforce per‑tool usage limits if configured
        try:
            limit = self.tool_limits.get(name_norm)
            if limit is not None:
                used = self.tool_usage.get(name_norm, 0)
                if used >= limit:
                    return {
                        "success": False,
                        "error": f"Tool '{tool_name}' usage limit reached ({used}/{limit})"
                    }
        except Exception:
            pass
        # Resolve the tool object
        tool = self.tools.get(name_norm)
        if not tool:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}
        # Execute the tool and record usage
        try:
            result = tool.execute(task)
            # Update usage count on success
            self.tool_usage[name_norm] = self.tool_usage.get(name_norm, 0) + 1
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}