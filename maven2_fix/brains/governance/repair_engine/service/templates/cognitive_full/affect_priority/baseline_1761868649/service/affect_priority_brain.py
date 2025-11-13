
from __future__ import annotations
import time, json
from pathlib import Path
from typing import Dict, Any
from api.utils import generate_mid, success_response, error_response
from api.memory import ensure_dirs, append_jsonl, count_lines, rotate_if_needed

HERE = Path(__file__).resolve().parent
BRAIN_ROOT = HERE.parent

def _counts():
    t = ensure_dirs(BRAIN_ROOT)
    return {"stm": count_lines(t["stm"]), "mtm": count_lines(t["mtm"]), "ltm": count_lines(t["ltm"]), "cold": count_lines(t["cold"])}

def service_api(msg):
    op = (msg or {}).get("op"," ").upper()
    mid = msg.get("mid") or generate_mid()
    payload = msg.get("payload") or {}
    if op == "HEALTH":
        return success_response(op, mid, {"status":"operational","memory_health": _counts()})
    return error_response(op, mid, "UNSUPPORTED_OP", op)
