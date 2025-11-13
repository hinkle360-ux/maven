
from __future__ import annotations
import time
from pathlib import Path
from typing import Dict, Any, List
from api.utils import generate_mid, success_response, error_response
from api.memory import ensure_dirs, append_jsonl, count_lines

HERE = Path(__file__).resolve().parent
BRAIN_ROOT = HERE.parent

def _counts():
    t = ensure_dirs(BRAIN_ROOT)
    return {"stm": count_lines(t["stm"]), "mtm": count_lines(t["mtm"]), "ltm": count_lines(t["ltm"]), "cold": count_lines(t["cold"])}

def _log_reflections(reflections: List[Dict[str, Any]]):
    t = ensure_dirs(BRAIN_ROOT)
    now = time.time()
    for r in reflections or []:
        append_jsonl(t["stm"], {"ts": now, "op":"REFLECTION", "content": r.get("content",""), "confidence": r.get("confidence",0.5), "source": r.get("source","system_internal")})

def service_api(msg):
    op = (msg or {}).get("op"," ").upper()
    mid = msg.get("mid") or generate_mid()
    payload = msg.get("payload") or {}

    if op == "HEALTH":
        return success_response(op, mid, {"status": "operational", "memory_health": _counts()})

    if op == "LOG_REFLECTIONS":
        _log_reflections(payload.get("reflections") or [])
        return success_response(op, mid, {"logged": len(payload.get("reflections") or [])})

    return error_response(op, mid, "UNSUPPORTED_OP", op)
