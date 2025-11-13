from __future__ import annotations
from typing import Dict, Any, List
from api.utils import generate_mid, success_response, error_response


def service_api(msg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Simple arbitration service for coordinating outputs from multiple brains.

    The council brain accepts an ``ARBITRATE`` operation with a payload
    containing a list of candidate responses.  Each candidate should be a
    dictionary with at least a ``confidence`` field.  The council selects
    the candidate with the highest confidence and returns it as the decision.
    Unsupported operations return an error.
    """
    op = (msg or {}).get("op", "").upper()
    mid = msg.get("mid") or generate_mid()
    payload = msg.get("payload") or {}
    if op == "ARBITRATE":
        cands: List[Dict[str, Any]] = payload.get("candidates") or []
        if not isinstance(cands, list) or not cands:
            return success_response(op, mid, {"decision": None})
        best: Dict[str, Any] | None = None
        best_conf: float = float("-inf")
        for cand in cands:
            try:
                conf = float(cand.get("confidence", 0.0) or 0.0)
            except Exception:
                conf = 0.0
            if conf > best_conf:
                best_conf = conf
                best = cand
        return success_response(op, mid, {"decision": best})
    return error_response(op, mid, "UNSUPPORTED_OP", op)

# Ensure the council brain exposes a `handle` entry point
try:
    handle = service_api  # type: ignore[assignment]
    service_api = handle  # type: ignore[assignment]
except Exception:
    pass