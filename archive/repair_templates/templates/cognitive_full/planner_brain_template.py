from __future__ import annotations
import time, json
from pathlib import Path
from typing import Dict, Any
from api.utils import generate_mid, success_response, error_response
from api.memory import ensure_dirs, append_jsonl

HERE = Path(__file__).resolve().parent
BRAIN_ROOT = HERE.parent

def _guess_intents_targets(text: str):
    text_l = (text or "").lower()
    intents = []
    targets = []
    # intents (very light heuristics)
    if any(w in text_l for w in ["show", "display", "find", "search", "retrieve"]):
        intents.append("retrieve_relevant_memories")
    if any(w in text_l for w in ["explain", "why", "how"]):
        intents.append("compose_explanation")
    if not intents:
        intents.append("compose_response")
    # targets/entities
    toks = [t.strip(",.!?") for t in (text or "").split()]
    for t in toks:
        if t and (t[0].isupper() or t.lower() in ("paris","eiffel","tower","photos")):
            targets.append(t)
    # dedupe preserving order
    seen=set(); targets = [x for x in targets if not (x in seen or seen.add(x))]
    return intents, targets

def service_api(msg: Dict[str, Any]) -> Dict[str, Any]:
    op = (msg or {}).get("op"," ").upper()
    mid = msg.get("mid") or generate_mid()
    payload = msg.get("payload") or {}
    if op == "HEALTH":
        t = ensure_dirs(BRAIN_ROOT)
        append_jsonl(t["stm"], {"ts": time.time(), "op":"HEALTH"})
        return success_response(op, mid, {"status":"operational","ts": int(time.time())})
    return error_response(op, mid, "UNSUPPORTED_OP", op)