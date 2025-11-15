"""
self_review_brain.py
====================

This module provides a very simple self‑review brain for Maven.  Its
purpose is to analyse past traces of cognition, identify potential
improvements to heuristics or thresholds, and suggest parameter tuning.
The current implementation is intentionally conservative and acts as
a placeholder for future learning capabilities.  It reads the graph
trace files and looks for repeated low‑confidence answers or long
processing times to recommend deeper reasoning or reduced retry limits.

Operations:

  RECOMMEND_TUNING
      Accept a payload with optional ``traces`` path and returns a
      dictionary of suggested parameter adjustments.  Each suggestion
      includes ``parameter``, ``current_value``, ``suggested_value`` and a
      human‑readable ``reason``.  If no tuning is recommended the
      returned list is empty.

Unknown operations will produce an error response.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional


def _analyse_traces(trace_path: str) -> List[Dict[str, Any]]:
    """Analyse the trace file and produce tuning suggestions.

    This naive implementation looks for runs where confidence is below
    0.5 and suggests increasing the reasoning depth.  If average
    processing time exceeds a threshold it suggests lowering the number
    of retries.  The analysis is intentionally simple and should be
    expanded in future iterations.
    """
    suggestions: List[Dict[str, Any]] = []
    try:
        with open(trace_path, "r", encoding="utf-8") as f:
            records = [json.loads(line) for line in f]
    except Exception:
        return suggestions
    # compute average confidence from any payloads that contain confidence
    confidences: List[float] = []
    durations: List[float] = []
    for rec in records:
        visits = rec.get("visits") or []
        for _, output in visits:
            if isinstance(output, dict) and "confidence" in output:
                try:
                    confidences.append(float(output["confidence"]))
                except Exception:
                    pass
            if isinstance(output, dict) and "duration" in output:
                try:
                    durations.append(float(output["duration"]))
                except Exception:
                    pass
    # Suggest deeper reasoning if average confidence is low
    if confidences:
        avg_conf = sum(confidences) / len(confidences)
        if avg_conf < 0.5:
            suggestions.append({
                "parameter": "reasoning_depth",
                "current_value": "default",
                "suggested_value": "increase",
                "reason": f"Average confidence {avg_conf:.2f} is low; consider deeper passes.",
            })
    # Suggest fewer retries if average duration is high
    if durations:
        avg_dur = sum(durations) / len(durations)
        if avg_dur > 2.0:  # seconds threshold
            suggestions.append({
                "parameter": "max_retries",
                "current_value": "default",
                "suggested_value": "decrease",
                "reason": f"Average processing duration {avg_dur:.2f}s is high; reduce retries.",
            })
    return suggestions


def _review_turn(
    query: str,
    plan: Dict[str, Any],
    thoughts: List[Dict[str, Any]],
    answer: str,
    metadata: Dict[str, Any]
) -> Dict[str, Any]:
    """Review a complete turn and decide on action.

    Args:
        query: The user's query
        plan: The plan that was generated
        thoughts: List of thought synthesis outputs
        answer: The final answer text
        metadata: Additional metadata (confidences, memories, intents)

    Returns:
        Dictionary with verdict, issues, recommended_action, and notes
    """
    issues: List[Dict[str, str]] = []
    verdict = "ok"

    confidences = metadata.get("confidences", {})
    used_memories = metadata.get("used_memories", [])
    intents = metadata.get("intents", [])

    try:
        final_confidence = float(confidences.get("final", 0.8))
    except Exception:
        final_confidence = 0.8

    try:
        reasoning_confidence = float(confidences.get("reasoning", 0.8))
    except Exception:
        reasoning_confidence = 0.8

    if final_confidence < 0.3:
        issues.append({
            "code": "LOW_CONFIDENCE",
            "message": f"Final confidence {final_confidence:.2f} is very low"
        })
        verdict = "major_issue"

    elif final_confidence < 0.5:
        issues.append({
            "code": "LOW_CONFIDENCE",
            "message": f"Final confidence {final_confidence:.2f} is below threshold"
        })
        if verdict == "ok":
            verdict = "minor_issue"

    if not answer or len(str(answer).strip()) < 5:
        issues.append({
            "code": "INCOMPLETE",
            "message": "Answer is missing or too short"
        })
        verdict = "major_issue"

    if plan and not thoughts:
        steps = plan.get("steps", [])
        if len(steps) > 0:
            issues.append({
                "code": "INCOMPLETE",
                "message": "Plan had steps but no thoughts were generated"
            })
            verdict = "major_issue"

    answer_lower = str(answer).lower()
    hedges = ["maybe", "possibly", "might", "perhaps", "i think", "probably"]
    hedge_count = sum(1 for h in hedges if h in answer_lower)
    if hedge_count > 3:
        issues.append({
            "code": "EXCESSIVE_HEDGING",
            "message": f"Answer contains {hedge_count} hedge words"
        })
        if verdict == "ok":
            verdict = "minor_issue"

    if "TODO" in answer or "FIXME" in answer:
        issues.append({
            "code": "INCOMPLETE",
            "message": "Answer contains TODO or FIXME markers"
        })
        verdict = "major_issue"

    if verdict == "major_issue":
        if final_confidence < 0.4 or not answer:
            recommended_action = "ask_clarification"
        else:
            recommended_action = "revise"
    elif verdict == "minor_issue":
        recommended_action = "accept"
    else:
        recommended_action = "accept"

    notes = f"Reviewed turn with {len(issues)} issue(s). Confidence: {final_confidence:.2f}"

    return {
        "verdict": verdict,
        "issues": issues,
        "recommended_action": recommended_action,
        "notes": notes
    }

def service_api(msg: Dict[str, Any]) -> Dict[str, Any]:
    """Entry point for the self‑review brain.

    Supported operations:

      - REVIEW_TURN: Review a complete turn and recommend action
      - RECOMMEND_TUNING: Analyse trace files and suggest parameter
        adjustments.  Payload may specify ``trace_path`` (defaults to
        'reports/trace_graph.jsonl').
    """
    op = (msg or {}).get("op", "").upper()
    payload = (msg or {}).get("payload", {}) or {}

    if op == "REVIEW_TURN":
        query = str(payload.get("query", ""))
        plan = payload.get("plan", {})
        thoughts = payload.get("thoughts", [])
        answer = str(payload.get("answer", ""))
        metadata = payload.get("metadata", {})

        review_result = _review_turn(query, plan, thoughts, answer, metadata)

        return {
            "ok": True,
            "op": op,
            "payload": review_result
        }

    if op == "RECOMMEND_TUNING":
        trace_path = payload.get("trace_path")
        if not trace_path:
            current_dir = os.path.dirname(__file__)
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
            trace_path = os.path.join(project_root, "reports", "trace_graph.jsonl")
        suggestions = _analyse_traces(trace_path)
        return {"ok": True, "op": op, "payload": {"suggestions": suggestions}}

    return {"ok": False, "op": op, "error": "unknown operation"}

# Ensure the self_review brain exposes a `handle` entry point
try:
    handle = service_api  # type: ignore[assignment]
    service_api = handle  # type: ignore[assignment]
except Exception:
    pass