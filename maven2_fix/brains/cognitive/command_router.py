"""
Command Router
==============

This module provides a lightweight command router for handling
command‑style inputs (e.g. ``--status`` or ``--cache purge``) within
Maven's cognitive pipeline.  When the language brain detects that the
user input is a command (via the ``--`` or ``/`` prefix), the memory
librarian can delegate the query to this router instead of invoking the
full reasoning pipeline.  The router looks up built‑in commands,
executes the corresponding handler functions and returns a short
message describing the result.  Unknown commands yield a structured
error message to avoid generic filler responses.

Each handler returns a dictionary with either a ``message`` key
containing a user‑friendly string or an ``error`` key describing
why the command could not be completed.  The memory librarian is
responsible for formatting this into the final answer and assigning
confidence.
"""

from __future__ import annotations

from typing import Dict, Any, List, Optional
import json
import os
from pathlib import Path


def _load_command_registry() -> Dict[str, Any]:
    """Load the command registry from ``config/commands.json``.

    Returns an empty dictionary if the file is missing or malformed.
    The registry is not strictly required by the router; handlers can
    be hardcoded below.  However, the file provides a structured
    reference for available commands and their descriptions.
    """
    try:
        # Determine the Maven project root by walking up from this file
        root = Path(__file__).resolve().parents[2]
        cfg_path = root / "config" / "commands.json"
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _handle_status() -> Dict[str, Any]:
    """Return a summary of the autonomous agent's state.

    The report includes whether the background agent daemon is running,
    the number of active goals and the total number of goals.  If the
    goal queue cannot be loaded, an error is returned instead of
    raising.
    """
    try:
        from brains.agent.autonomous.goal_queue import GoalQueue  # type: ignore
        # Instantiate the goal queue.  This reads goals from disk without
        # spawning or interacting with the agent daemon.
        queue = GoalQueue()
        active_goals = queue.load_goals(active_only=True)
        all_goals = queue.load_goals(active_only=False)
        # Determine the running state of the agent daemon if possible.
        running = False
        try:
            from brains.agent.autonomous.agent_daemon import AgentDaemon  # type: ignore
            # Do not start a new daemon thread; instead instantiate and
            # inspect the ``running`` attribute.  In typical usage the
            # agent daemon will set this flag to True when running.  If
            # instantiation raises, default to False.
            daemon = AgentDaemon()
            running = bool(getattr(daemon, "running", False))
        except Exception:
            running = False
        # Build a compact JSON report for the status.  This can be
        # pretty‑printed by the caller if desired.  Titles are
        # truncated to avoid overly long lists.
        report = {
            "running": running,
            "active_goals": len(active_goals),
            "total_goals": len(all_goals),
            "active_goal_titles": [g.get("title", g.get("goal_id")) for g in active_goals],
        }
        return {"message": json.dumps(report, ensure_ascii=False)}
    except Exception as e:
        return {"error": f"status_failed: {e}"}


def _handle_cache_purge() -> Dict[str, Any]:
    """Remove the fast cache file if it exists.

    Deleting the fast cache forces the pipeline to recompute answers on
    subsequent runs.  Any error during deletion is returned in the
    ``error`` key.
    """
    try:
        root = Path(__file__).resolve().parents[2]
        cache_path = root / "reports" / "fast_cache.jsonl"
        if cache_path.exists():
            cache_path.unlink()
            return {"message": "Fast cache purged."}
        else:
            return {"message": "Fast cache is already empty."}
    except Exception as e:
        return {"error": f"cache_purge_failed: {e}"}


def _handle_input(args: List[str]) -> Dict[str, Any]:
    """Placeholder handler for the ``input`` command.

    In a future implementation this function could ingest external
    knowledge or domain data into Maven.  Until then it simply
    returns an error indicating that the command is unsupported.
    """
    return {"error": "input_not_supported"}


def route_command(command_text: str) -> Dict[str, Any]:
    """Dispatch a command string to the appropriate handler.

    The input should begin with a ``--`` or ``/`` prefix.  Leading
    prefix characters are stripped before lookup.  If a subcommand is
    present (e.g. ``cache purge``), the first and second tokens are
    considered separately.  Unknown commands or subcommands result in
    an ``error`` entry describing the failure.

    Args:
        command_text: The raw command string as entered by the user.

    Returns:
        A dictionary with either a ``message`` or ``error`` key.
    """
    try:
        if not command_text:
            return {"error": "empty_command"}
        # Split tokens by whitespace.  Do not strip trailing whitespace
        # on the entire command so that commands like "--cache purge" are
        # parsed correctly.
        tokens = command_text.strip().split()
        if not tokens:
            return {"error": "empty_command"}
        # Remove leading dashes or slashes from the first token.  Allow
        # multiple leading prefixes (e.g. "--status" or "/status").
        cmd = tokens[0].lstrip("-/")
        cmd_lower = cmd.lower()
        # ------------------------------------------------------------------
        # Natural‑language command pre‑processing.  In addition to CLI
        # commands beginning with "--" or "/", the memory librarian may
        # route spoken imperatives such as "you say hello" or "say hi"
        # through this router.  To support these social actions, detect
        # second‑person prefixes ("you" or "u") and remap the command to
        # the next token.  For example, "you say hello" is treated as
        # "say hello".  The remainder of the tokens are passed as
        # arguments.  This enables simple etiquette triggers without
        # polluting the core command namespace.
        args: List[str] = []
        try:
            if cmd_lower in ("you", "u") and len(tokens) > 1:
                cmd_lower = tokens[1].lower()
                args = tokens[2:]
            else:
                args = tokens[1:]
        except Exception:
            args = tokens[1:]
        # ------------------------------------------------------------------
        # Handle built‑in commands.  Additional commands can be
        # registered in config/commands.json without changing this code.
        if cmd_lower in ("status", "agent_status"):
            return _handle_status()
        if cmd_lower == "cache":
            # Determine subcommand if present.  Accept synonyms for purge.
            sub = args[0].lower() if args else ""
            if sub in ("purge", "clear", "reset"):
                return _handle_cache_purge()
            # Unknown subcommand; provide explicit guidance
            return {"error": f"unknown_cache_command: {sub or 'missing_subcommand'}"}
        if cmd_lower == "input":
            # The input command expects at least one argument (e.g. a file path).
            # If no arguments are provided, return a clarifying message instead
            # of an error to avoid triggering high‑effort fallback later in the
            # pipeline.  When arguments are present, pass them to the
            # placeholder handler.
            if not args:
                return {
                    "message": "The input command requires a file path. Example: --input /path/to/file"
                }
            return _handle_input(args)
        # ------------------------------------------------------------------
        # Social speech act: say/speak.  Respond by echoing the provided
        # phrase, capitalising the first letter and preserving the rest.
        # When the phrase appears to be a common greeting or thanks, add
        # an exclamation mark to convey warmth.  Record the behavioural
        # rule in a JSONL file under reports/behavior_rules.jsonl to
        # enable future learning of social patterns.  Errors during
        # storage are ignored to avoid breaking command routing.
        if cmd_lower in ("say", "speak", "tell"):
            phrase = " ".join(args).strip()
            if not phrase:
                return {"error": "nothing_to_say"}
            # Persist the rule for learning behavioural patterns
            try:
                root = Path(__file__).resolve().parents[2]
                beh_file = root / "reports" / "behavior_rules.jsonl"
                beh_file.parent.mkdir(parents=True, exist_ok=True)
                rec = {
                    "cmd": cmd_lower,
                    "phrase": phrase
                }
                with open(beh_file, "a", encoding="utf-8") as fh:
                    import json as _json
                    fh.write(_json.dumps(rec) + "\n")
            except Exception:
                pass
            # Compose a friendly response
            # Basic capitalisation
            resp = phrase[0].upper() + phrase[1:] if phrase else phrase
            # Add warmth for common salutations or thanks
            try:
                pl = phrase.lower()
            except Exception:
                pl = phrase
            if pl in ("hello", "hi", "hey", "good morning", "good afternoon", "good evening"):
                # Add an exclamation for enthusiasm and a follow‑up question
                resp = resp.rstrip("!") + "! How can I assist you?"
            elif "thank" in pl:
                # Respond politely to thanks
                resp = resp.rstrip("!") + "! You're welcome."
            return {"message": resp}
        # ------------------------------------------------------------------
        # Unknown command
        return {"error": f"unknown_command: {cmd_lower}"}
    except Exception as exc:
        return {"error": f"command_router_failure: {exc}"}
