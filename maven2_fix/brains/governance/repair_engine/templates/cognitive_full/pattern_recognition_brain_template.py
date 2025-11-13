
from __future__ import annotations
import re, time
from typing import Dict, Any
from pathlib import Path
from api.utils import generate_mid, success_response, error_response
from api.memory import ensure_dirs, append_jsonl, count_lines

HERE = Path(__file__).resolve().parent
BRAIN_ROOT = HERE.parent

def _counts():
    t = ensure_dirs(BRAIN_ROOT)
    return {
        "stm": count_lines(t["stm"]),
        "mtm": count_lines(t["mtm"]),
        "ltm": count_lines(t["ltm"]),
        "cold": count_lines(t["cold"]),
    }

def _analyze(text: str) -> Dict[str, Any]:
    s = (text or "").strip()
    words = [w for w in re.findall(r"[A-Za-z0-9']+", s)]
    repeats = sorted({w for w in words if words.count(w) > 1})
    has_digit = any(c.isdigit() for c in s)
    has_punct = any(c in ".?!,;:" for c in s)
    length = len(s); unique_words = len(set(words))
    avg_word_len = round(sum(len(w) for w in words) / len(words), 2) if words else 0.0
    shape = {
        "has_digit": has_digit,
        "has_punctuation": has_punct,
        "length": length,
        "word_count": len(words),
        "unique_words": unique_words,
        "avg_word_len": avg_word_len,
        "repeating_words": repeats[:5],
    }
    out = {"features": shape, "confidence": 0.4, "timestamp": time.time()}
    # log to memory like other brains
    tiers = ensure_dirs(BRAIN_ROOT)
    now = time.time()
    append_jsonl(tiers["stm"], {"ts": now, "op": "ANALYZE", "input": s, "output": out})
    append_jsonl(tiers["mtm"], {"ts": now, "op": "ANALYZE", "word_count": len(words)})
    return out

def service_api(msg: Dict[str, Any]) -> Dict[str, Any]:
    op = (msg or {}).get("op"," ").upper()
    mid = msg.get("mid") or generate_mid()
    payload = msg.get("payload") or {}

    if op == "HEALTH":
        return success_response(op, mid, {"status": "operational", "memory_health": _counts()})
    if op == "ANALYZE":
        return success_response(op, mid, _analyze(str(payload.get("text",""))))
    return error_response(op, mid, "UNSUPPORTED_OP", op)
