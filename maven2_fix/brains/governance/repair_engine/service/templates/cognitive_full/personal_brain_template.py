from __future__ import annotations
import time, json
from typing import Dict, Any
from api.utils import generate_mid, success_response, error_response
from api.memory import ensure_dirs, append_jsonl, count_lines
from pathlib import Path

HERE = Path(__file__).resolve().parent
PERSONAL_ROOT = HERE.parent  # .../brains/personal

def _counts():
    t = ensure_dirs(PERSONAL_ROOT)
    return {"stm": count_lines(t["stm"]), "mtm": count_lines(t["mtm"]), "ltm": count_lines(t["ltm"]), "cold": count_lines(t["cold"])}

def service_api(msg: Dict[str, Any]) -> Dict[str, Any]:
    op = (msg or {}).get("op"," ").upper()
    mid = msg.get("mid") or generate_mid()
    payload = msg.get("payload") or {}

    if op == "HEALTH":
        return success_response(op, mid, {"status":"operational","memory_health": _counts()})

    if op == "SCORE_BOOST":
        subj = str(payload.get("subject","")).strip().lower()
        # primitive stub: no preferences yet, always zero boost
        return success_response(op, mid, {"subject": subj, "boost": 0.0})

    if op == "WHY":
        subj = str(payload.get("subject",""))
        # primitive stub: emits empty hypothesis/signals
        return success_response(op, mid, {"subject": subj, "hypothesis": None, "signals": []})

    return error_response(op, mid, "UNSUPPORTED_OP", op)
