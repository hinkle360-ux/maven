
from __future__ import annotations
import time, json
from pathlib import Path
from typing import Dict, Any
from api.utils import generate_mid, success_response, error_response
from api.memory import ensure_dirs, append_jsonl

HERE = Path(__file__).resolve().parent
BRAIN_ROOT = HERE.parent

def service_api(msg: Dict[str, Any]) -> Dict[str, Any]:
    op = (msg or {}).get("op"," ").upper()
    mid = msg.get("mid") or generate_mid()
    payload = msg.get("payload") or {}
    if op == "HEALTH":
        t = ensure_dirs(BRAIN_ROOT)
        append_jsonl(t["stm"], {"ts": time.time(), "op":"HEALTH"})
        return success_response(op, mid, {"status":"operational","ts": int(time.time())})
    return error_response(op, mid, "UNSUPPORTED_OP", op)
