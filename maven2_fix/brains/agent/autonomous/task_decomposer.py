"""
Task Decomposer
================

This module implements a simple task decomposer for high‑level goals.
Given a goal record, the decomposer analyses its type and returns a
sequence of sub‑tasks that can be executed by the agent.  The
decompositions defined here are placeholders; they can be expanded
with more sophisticated logic and domain knowledge in future phases.
"""

from __future__ import annotations

from typing import List, Dict, Any


class TaskDecomposer:
    """Break high‑level goals into executable sub‑tasks."""

    def decompose(self, goal: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Decompose a goal into a list of sub‑tasks.

        Args:
            goal: A goal record from the goal queue.

        Returns:
            A list of task dictionaries describing the actions to
            perform.  Each task dict should include a ``task`` key
            indicating the type of operation and additional parameters.
        """
        if not goal:
            return []
        goal_type = self._classify_goal(goal)
        if goal_type == "research":
            return self._decompose_research(goal)
        if goal_type == "analysis":
            return self._decompose_analysis(goal)
        if goal_type == "creation":
            return self._decompose_creation(goal)
        # Fallback to a generic decomposition that simply stores the
        # goal description.  This can be expanded to handle more
        # categories.
        return self._decompose_generic(goal)

    def _classify_goal(self, goal: Dict[str, Any]) -> str:
        """Classify a goal into broad categories.

        This helper uses simple keyword matching on the goal's title
        and description.  It is intentionally naive and should be
        replaced with a more robust classifier (e.g. machine
        learning) in the future.

        Args:
            goal: The goal record to classify.

        Returns:
            A string label such as ``research``, ``analysis`` or
            ``creation``.
        """
        title = str(goal.get("title", "")).lower()
        desc = str(goal.get("description", "")).lower()
        text = f"{title} {desc}"
        if any(word in text for word in ["research", "learn", "investigate"]):
            return "research"
        if any(word in text for word in ["analyze", "analyse", "evaluate", "test"]):
            return "analysis"
        if any(word in text for word in ["create", "build", "make", "develop"]):
            return "creation"
        return "generic"

    def _decompose_research(self, goal: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Decompose a research goal into a sequence of fine‑grained subtasks.

        A well‑structured research plan consists of several stages: defining
        the scope of the investigation, identifying trustworthy sources,
        setting success criteria, performing the actual searches and
        synthesising the findings.  This helper breaks a research goal
        down into a series of tasks that can be scheduled by the agent
        execution engine.  Additional metadata (e.g., estimated time or
        number of sources) may be attached by callers.
        """
        title = goal.get("title") or ""
        return [
            {"task": "define_scope", "query": title},
            {"task": "identify_sources", "sources": ["academic papers", "trusted blogs", "news articles"]},
            {"task": "set_success_criteria", "criteria": {"num_sources": 5, "depth": "medium"}},
            {"task": "search_memory", "query": title},
            {"task": "search_knowledge_graph", "topic": title},
            {"task": "synthesize_findings", "sources": ["memory", "kg"]},
            {"task": "store_results", "bank": "factual"},
        ]

    def _decompose_analysis(self, goal: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Example decomposition for an analysis goal."""
        # Placeholder: a real implementation would inspect goal metadata
        return [
            {"task": "load_data", "source": goal.get("data_source", "")},
            {"task": "apply_analysis", "method": goal.get("analysis_type", "")},
            {"task": "generate_report", "format": "summary"},
            {"task": "store_results", "bank": "theories_and_contradictions"},
        ]

    def _decompose_creation(self, goal: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Example decomposition for a creation goal."""
        # Placeholder: break down creative tasks (e.g. write, code, design)
        return [
            {"task": "plan_creation", "title": goal.get("title", "")},
            {"task": "execute_creation", "title": goal.get("title", "")},
            {"task": "review_creation", "title": goal.get("title", "")},
            {"task": "store_results", "bank": "factual"},
        ]

    def _decompose_generic(self, goal: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fallback decomposition that stores the goal as a fact."""
        return [
            {"task": "store_results", "bank": "factual", "title": goal.get("title", "")},
        ]