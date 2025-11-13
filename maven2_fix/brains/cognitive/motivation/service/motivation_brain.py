"""
Motivation Brain
================

This is a skeleton implementation of a simple motivation brain.  It introduces
a light‑weight mechanism for identifying opportunities (questions or knowledge
gaps) and formulating goals to address them.  The goal of this brain is to
support higher‑level autonomous behaviour by suggesting topics worth
investigating.  In the current implementation it does not depend on any
external libraries and returns empty sets by default.

Operations:

  SCORE_OPPORTUNITIES
      Examine the provided context or evidence and return a list of
      opportunity descriptors.  Each opportunity is a dict with fields
      ``kind``, ``target`` and ``score``.  Higher scores indicate more
      pressing opportunities.  If no evidence is provided the list is empty.

  FORMULATE_GOALS
      Convert a list of opportunity descriptors into high‑level goals.  Each
      goal is a dict with ``goal_id``, ``type``, ``target``, ``priority``
      and ``rationale``.  Goal identifiers are prefixed with ``MOT-`` and
      include a simple monotonic counter.

Example usage:

    from brains.cognitive.motivation.service.motivation_brain import service_api
    resp = service_api({"op": "SCORE_OPPORTUNITIES", "payload": {"evidence": {...}}})
    opps = resp.get("payload", {}).get("opportunities", [])
    goals = service_api({"op": "FORMULATE_GOALS", "payload": {"opportunities": opps}})

This module is intentionally conservative and will evolve as autonomy features
are refined.  For now it returns empty lists when no useful information is
present.
"""

from __future__ import annotations
from typing import Dict, Any, List
import itertools

_counter = itertools.count(1)

def _generate_goal_id() -> str:
    return f"MOT-{next(_counter):04d}"

def _score_opportunities(evidence: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Scan evidence for unanswered questions or gaps.

    This naive implementation looks for entries in the evidence with
    ``result_type`` set to "unanswered_question" and assigns a score based on
    the number of times the question has been asked.  An opportunity is a
    dict with keys ``kind``, ``target`` and ``score``.  If no suitable
    evidence is found an empty list is returned.
    """
    if not isinstance(evidence, dict):
        return []
    opps: List[Dict[str, Any]] = []
    results = (evidence.get("results") or []) if isinstance(evidence.get("results"), list) else []
    for rec in results:
        if not isinstance(rec, dict):
            continue
        # use a synthetic tag to mark unanswered questions; this can be
        # extended in future revisions
        if rec.get("result_type") == "unanswered_question":
            qtext = str(rec.get("query", "")).strip()
            if not qtext:
                continue
            # compute a simple score: the more times we've seen this question,
            # the higher the score.  Default to 1.0.
            try:
                count = int(rec.get("times", 1))
            except Exception:
                count = 1
            score = min(1.0, 0.1 * float(count)) + 0.5
            opps.append({"kind": "knowledge_gap", "target": qtext, "score": score})
    return opps

def _formulate_goals(opportunities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Transform opportunities into concrete goals.

    A goal summarises a high‑level action for the agent to pursue.  Each goal
    contains a unique ID, a goal type, target information, a priority (0..1)
    and a human‑readable rationale.  If no opportunities are provided, an
    empty list is returned.
    """
    if not isinstance(opportunities, list):
        return []
    goals: List[Dict[str, Any]] = []
    for opp in opportunities:
        if not isinstance(opp, dict):
            continue
        kind = opp.get("kind") or "unknown"
        target = opp.get("target") or ""
        score = float(opp.get("score", 0.5))
        gid = _generate_goal_id()
        goals.append({
            "goal_id": gid,
            "type": kind,
            "target": target,
            "priority": max(0.0, min(1.0, score)),
            "rationale": f"Address knowledge gap regarding '{target}'."
        })
    return goals

def service_api(msg: Dict[str, Any]) -> Dict[str, Any]:
    """Entry point for the motivation brain.

    Supports the following operations:

      - SCORE_OPPORTUNITIES: Identify potential knowledge gaps.
      - FORMULATE_GOALS: Construct concrete goals from opportunities.

    Unknown operations return an error response.
    """
    op = (msg or {}).get("op", "").upper()
    payload = (msg or {}).get("payload", {}) or {}
    if op == "SCORE_OPPORTUNITIES":
        evidence = payload.get("evidence") or {}
        opps = _score_opportunities(evidence)
        return {"ok": True, "op": op, "payload": {"opportunities": opps}}
    if op == "FORMULATE_GOALS":
        opps = payload.get("opportunities") or []
        goals = _formulate_goals(opps)
        return {"ok": True, "op": op, "payload": {"goals": goals}}
    # Step‑4: compute a motivation drive signal
    # SCORE_DRIVE produces a scalar in the range [0,1] representing the
    # current motivational drive based on success, affect and contradiction
    # counts passed in the context.  It reads weights from the global
    # configuration (motivation.weight_success, weight_affect,
    # weight_contradiction) with fallbacks.  Negative contributions from
    # contradictions reduce the drive.  The output is clamped to [0,1].
    if op == "SCORE_DRIVE":
        context = payload.get("context") or {}
        # Extract metrics from context; missing values default to 0
        try:
            success = float(context.get("success_count", 0.0))
        except Exception:
            success = 0.0
        try:
            affect = float(context.get("affect_score", 0.0))
        except Exception:
            affect = 0.0
        try:
            contradictions = float(context.get("contradictions", 0.0))
        except Exception:
            contradictions = 0.0
        # Load weighting parameters from global configuration
        try:
            from api.utils import CFG  # type: ignore
            weights = (CFG.get("motivation") or {})
            w_success = float(weights.get("weight_success", 0.4))
            w_affect = float(weights.get("weight_affect", 0.4))
            w_contra = float(weights.get("weight_contradiction", 0.2))
        except Exception:
            w_success = 0.4
            w_affect = 0.4
            w_contra = 0.2
        # Compute drive as weighted sum; contradictions lower motivation
        drive = (w_success * success) + (w_affect * affect) - (w_contra * contradictions)
        # Normalise into [0,1]
        try:
            drive = max(0.0, min(1.0, float(drive)))
        except Exception:
            drive = 0.0
        return {"ok": True, "op": op, "payload": {"drive": drive}}
    return {"ok": False, "op": op, "error": "unknown operation"}

# Ensure the motivation brain exposes a `handle` entry point
try:
    handle = service_api  # type: ignore[assignment]
    service_api = handle  # type: ignore[assignment]
except Exception:
    pass