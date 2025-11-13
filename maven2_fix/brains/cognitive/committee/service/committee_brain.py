
# (Removed early alias to satisfy future import constraints; alias defined at end)
"""
Committee Brain
===============

This module introduces a simple committee mechanism for aggregating
decisions from multiple cognitive subsystems.  It mirrors how a group
of internal voices might reach a consensus when presented with a
question or proposed action.  Each member contributes a decision
(propose/approve/deny/abstain) and a confidence score; the committee
then aggregates these into a single decision and an overall
confidence.

Operations:

  CONSULT
      Accepts a list of ``votes`` where each vote is a dict with
      ``decision`` (str) and ``confidence`` (float).  Recognised
      decisions are "propose", "approve", "deny" and "abstain".  The
      aggregate decision is the majority decision weighted by
      confidence.  Confidence is scaled by the number of votes.

Example usage:

    from brains.cognitive.committee.service.committee_brain import service_api
    resp = service_api({"op": "CONSULT", "payload": {
        "votes": [
          {"decision": "approve", "confidence": 0.8},
          {"decision": "propose", "confidence": 0.6},
          {"decision": "deny", "confidence": 0.4},
        ]
    }})
    result = resp.get("payload")

The committee does not carry out any side effects; it only returns
aggregated judgments.
"""

from __future__ import annotations
from typing import Dict, Any, List

# Step‑2 integration: import memory librarian service to store committee decisions.
try:
    # Lazy import to avoid mandatory dependency in environments without the librarian.
    from brains.cognitive.memory_librarian.service.memory_librarian import service_api as mem_service_api  # type: ignore
except Exception:
    mem_service_api = None  # type: ignore

def _aggregate_votes(votes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate votes into a single decision and confidence.

    The algorithm sums confidence scores for each decision category
    (propose/approve are treated as positive, deny as negative) and
    normalises by the total confidence.  Abstentions are ignored.

    Returns a dict with keys ``decision`` and ``confidence``.
    """
    if not votes:
        return {"decision": "abstain", "confidence": 0.0}
    pos = 0.0
    neg = 0.0
    total_conf = 0.0
    for v in votes:
        try:
            conf = float(v.get("confidence", 0.0))
        except Exception:
            conf = 0.0
        dec = str(v.get("decision", "abstain")).lower()
        if dec in {"propose", "approve"}:
            pos += conf
        elif dec == "deny":
            neg += conf
        # abstain contributions don't affect pos/neg but count toward total
        total_conf += conf
    if total_conf <= 0:
        return {"decision": "abstain", "confidence": 0.0}
    # compute final decision
    if pos > neg:
        final_dec = "approve" if pos >= (neg + pos) * 0.75 else "propose"
        conf = pos / total_conf
    elif neg > pos:
        final_dec = "deny"
        conf = neg / total_conf
    else:
        final_dec = "abstain"
        conf = 0.0
    return {"decision": final_dec, "confidence": round(conf, 3)}

def service_api(msg: Dict[str, Any]) -> Dict[str, Any]:
    """Main entry point for committee operations.

    Only supports CONSULT for now.  Returns an error for unknown operations.
    """
    op = (msg or {}).get("op", "").upper()
    payload = (msg or {}).get("payload", {}) or {}
    if op == "CONSULT":
        votes = payload.get("votes") or []
        if not isinstance(votes, list):
            votes = []
        result = _aggregate_votes(votes)
        # Step‑2: Store the aggregated committee decision in working memory.
        try:
            if mem_service_api is not None:
                # Use a generic key derived from the aggregated decision to enable later recall.
                key = "committee:" + result.get("decision", "unknown")
                mem_service_api({
                    "op": "WM_PUT",
                    "payload": {
                        "key": key,
                        "value": result,
                        "tags": ["committee", "decision"],
                        # use the committee confidence as the working memory confidence
                        "confidence": float(result.get("confidence", 0.0)),
                        # default TTL of 5 minutes to allow opportunistic recall
                        "ttl": 300.0,
                    }
                })
        except Exception:
            # Any errors in WM integration should be non‑blocking
            pass
        return {"ok": True, "op": op, "payload": result}
    return {"ok": False, "op": op, "error": "unknown operation"}

# Ensure the committee brain exposes a `handle` entry point
try:
    handle = service_api  # type: ignore[assignment]
    service_api = handle  # type: ignore[assignment]
except Exception:
    pass