"""
Identity Inferencer
===================

This module infers stable self‑traits from runtime signals such as
reflection logs and system metrics.  It reads the agent's reflection
logs (e.g. ``reports/reflection/turn_*.jsonl``) and other internal
metrics to propose trait deltas that describe Maven's identity.

The inferencer is deliberately conservative: it does not directly
modify the identity snapshot.  Instead it writes any proposed trait
changes to a sidecar file adjacent to this module so that the
governance layer can review and approve them.  A simple API is
provided for triggering inference and retrieving proposals.

The implementation here is intentionally lightweight.  It stubs out
metric extraction and uses a trivial rule set.  This scaffolding
allows future extensions to incorporate richer behavioural analysis
without blocking current upgrades.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, Any

from api.utils import generate_mid, success_response, error_response


def _reports_dir() -> Path:
    """Return the base reports directory relative to the project root."""
    # This file lives in brains/personal/service; climb up to the
    # project root to locate the reports folder.
    return Path(__file__).resolve().parents[3] / "reports"


def _extract_metrics() -> Dict[str, float]:
    """Extract simple metrics from reflection logs.

    The current implementation acts as a placeholder and does not
    actually parse log files.  It returns an empty dict.  Future
    implementations may compute statistics such as the ratio of slow
    vs. fast reasoning routes or the frequency of reflection events.
    """
    # TODO: implement actual metric extraction by reading
    # reports/reflection/turn_*.jsonl and other sources.
    return {}


def compute_proposals() -> Dict[str, Any]:
    """Compute trait change proposals based on runtime metrics.

    Returns a mapping from trait names to proposed weight deltas.  An
    empty mapping indicates no change is recommended.  This function
    encapsulates the rules that infer how Maven's behaviour implies
    identity traits.  For example, a high rate of slow-path reasoning
    might increment the ``deliberative_thinker`` trait.
    """
    metrics = _extract_metrics()
    proposals: Dict[str, Any] = {}
    # Example rules (commented out until metrics are implemented):
    # if metrics.get("slow_path_rate", 0.0) >= 0.35:
    #     proposals["deliberative_thinker"] = proposals.get("deliberative_thinker", 0.0) + 0.1
    # if metrics.get("reflection_present_rate", 0.0) >= 0.90:
    #     proposals["learns_through_reflection"] = proposals.get("learns_through_reflection", 0.0) + 0.1
    # if metrics.get("approved_imaginations_per_100", 0.0) >= 10:
    #     proposals["proactive_forecaster"] = proposals.get("proactive_forecaster", 0.0) + 0.1
    return proposals


def _write_proposals(proposals: Dict[str, Any]) -> None:
    """Persist proposals to a local JSON file for governance review."""
    p = Path(__file__).with_suffix(".proposals.json")
    try:
        record = {
            "timestamp": time.time(),
            "proposals": proposals,
        }
        p.write_text(json.dumps(record, indent=2), encoding="utf-8")
    except Exception:
        # Silently ignore write errors to avoid crashing the agent
        pass


def service_api(msg: Dict[str, Any]) -> Dict[str, Any]:
    """Entry point for identity inference operations.

    Supported operations:

    * ``PROPOSE`` – run inference and return proposed trait deltas.  A
      sidecar file with the proposals and timestamp is also written to
      disk for governance review.

    Unsupported operations return an error response.
    """
    op = (msg or {}).get("op", "").upper()
    mid = msg.get("mid") or generate_mid()
    if op == "PROPOSE":
        proposals = compute_proposals()
        _write_proposals(proposals)
        return success_response(op, mid, {"proposals": proposals})
    return error_response(op, mid, "UNSUPPORTED_OP", op)