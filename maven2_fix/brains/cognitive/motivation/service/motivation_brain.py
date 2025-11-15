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
import json
from pathlib import Path

_counter = itertools.count(1)

_DEFAULT_STATE = {
    "helpfulness": 0.8,
    "truthfulness": 0.9,
    "curiosity": 0.5,
    "self_improvement": 0.5
}

def _get_state_path() -> Path:
    """Get the path to the motivation state file."""
    here = Path(__file__).resolve().parent
    return here.parent / "memory" / "motivation_state.json"

def _load_motivation_state() -> Dict[str, float]:
    """Load current motivation state from disk."""
    try:
        state_path = _get_state_path()
        if state_path.exists():
            data = json.loads(state_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else _DEFAULT_STATE.copy()
    except Exception:
        pass
    return _DEFAULT_STATE.copy()

def _save_motivation_state(state: Dict[str, float]) -> None:
    """Save motivation state to disk."""
    try:
        state_path = _get_state_path()
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass

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

      - GET_STATE: Return current motivation drive vector
      - ADJUST_STATE: Modify motivation drives with bounded deltas
      - EVALUATE_QUERY: Compute motivation weights for a specific query
      - SCORE_OPPORTUNITIES: Identify potential knowledge gaps
      - FORMULATE_GOALS: Construct concrete goals from opportunities
      - SCORE_DRIVE: Compute overall motivation drive signal

    Unknown operations return an error response.
    """
    op = (msg or {}).get("op", "").upper()
    payload = (msg or {}).get("payload", {}) or {}

    if op == "GET_STATE":
        state = _load_motivation_state()
        return {"ok": True, "op": op, "payload": state}

    if op == "ADJUST_STATE":
        deltas = payload.get("deltas", {})
        current_state = _load_motivation_state()

        for key, delta in deltas.items():
            if key in current_state:
                try:
                    delta_val = float(delta)
                    delta_val = max(-0.2, min(0.2, delta_val))
                    new_val = current_state[key] + delta_val
                    current_state[key] = max(0.0, min(1.0, new_val))
                except Exception:
                    pass

        _save_motivation_state(current_state)
        return {"ok": True, "op": op, "payload": current_state}

    if op == "EVALUATE_QUERY":
        query = str(payload.get("query", ""))
        context = payload.get("context", {})

        state = _load_motivation_state()
        weights = state.copy()

        query_lower = query.lower()
        if any(word in query_lower for word in ["why", "how", "explain"]):
            weights["curiosity"] = min(1.0, weights.get("curiosity", 0.5) + 0.2)
            weights["truthfulness"] = min(1.0, weights.get("truthfulness", 0.9) + 0.1)

        if "help" in query_lower or "please" in query_lower:
            weights["helpfulness"] = min(1.0, weights.get("helpfulness", 0.8) + 0.15)

        if any(word in query_lower for word in ["improve", "better", "enhance"]):
            weights["self_improvement"] = min(1.0, weights.get("self_improvement", 0.5) + 0.2)

        uncertainty = context.get("uncertainty", 0.0)
        if uncertainty > 0.7:
            weights["truthfulness"] = min(1.0, weights.get("truthfulness", 0.9) + 0.1)

        return {"ok": True, "op": op, "payload": {"weights": weights, "base_state": state}}

    if op == "SCORE_OPPORTUNITIES":
        evidence = payload.get("evidence") or {}
        opps = _score_opportunities(evidence)
        return {"ok": True, "op": op, "payload": {"opportunities": opps}}

    if op == "FORMULATE_GOALS":
        opps = payload.get("opportunities") or []
        goals = _formulate_goals(opps)
        return {"ok": True, "op": op, "payload": {"goals": goals}}

    if op == "SCORE_DRIVE":
        context = payload.get("context") or {}
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
        drive = (w_success * success) + (w_affect * affect) - (w_contra * contradictions)
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