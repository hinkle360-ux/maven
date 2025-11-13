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


def service_api(msg: Dict[str, Any]) -> Dict[str, Any]:
    """Entry point for the self‑review brain.

    Supported operations:

      - RECOMMEND_TUNING: Analyse trace files and suggest parameter
        adjustments.  Payload may specify ``trace_path`` (defaults to
        'reports/trace_graph.jsonl').
    """
    op = (msg or {}).get("op", "").upper()
    payload = (msg or {}).get("payload", {}) or {}
    if op == "RECOMMEND_TUNING":
        trace_path = payload.get("trace_path")
        if not trace_path:
            # derive default path: locate project root and trace file
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