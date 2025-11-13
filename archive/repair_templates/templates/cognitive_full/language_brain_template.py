from __future__ import annotations

import time, json
from pathlib import Path
from typing import Dict, Any
from api.utils import generate_mid, success_response, error_response, CFG
from api.memory import ensure_dirs, append_jsonl, count_lines

def _read_weights(root: Path):
    p = root / "weights.json"
    if p.exists():
        try:
            w = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            w = CFG["weights_defaults"]
    else:
        w = CFG["weights_defaults"]
        p.write_text(json.dumps(w, indent=2), encoding="utf-8")
    return w

HERE = Path(__file__).resolve().parent
BRAIN_ROOT = HERE.parent

def _counts() -> Dict[str, int]:
    t = ensure_dirs(BRAIN_ROOT)
    return {"stm": count_lines(t["stm"]), "mtm": count_lines(t["mtm"]), "ltm": count_lines(t["ltm"]), "cold": count_lines(t["cold"])}

def _clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))

def _parse(text: str, delta: dict = None) -> dict:
    w = _read_weights(BRAIN_ROOT)
    try:
        d = float((delta or {}).get("verbosity_bias_delta", 0.0))
    except Exception:
        d = 0.0
    base_v = float(w.get("verbosity_bias", 0.5))
    eff_v = _clip(base_v + d, 0.0, 1.0)

    tone = (delta or {}).get("tone") or "neutral"
    words = [x for x in (text or "").strip().split() if x]
    subject = words[0].lower() if words else None
    verb = words[1].lower() if len(words) > 1 else None
    obj = " ".join(words[2:]).lower() if len(words) > 2 else None
    intent = "question" if (text or "").strip().endswith("?") else "statement"

    verbosity_hint = round(1.0 + (eff_v - 0.5), 2)
    out = {
        "subject": subject,
        "verb": verb,
        "object": obj,
        "intent": intent,
        "word_count": len(words),
        "tone": tone,
        "verbosity_hint": verbosity_hint,
        "weights_used": {"verbosity_bias": eff_v}
    }

    tiers = ensure_dirs(BRAIN_ROOT)
    now = time.time()
    append_jsonl(tiers["stm"], {
        "ts": now,
        "op": "ADJUST_WEIGHTS",
        "base": {"verbosity_bias": base_v},
        "delta": {"verbosity_bias": d},
        "effective": {"verbosity_bias": eff_v},
        "tone": tone
    })
    append_jsonl(tiers["stm"], {"ts": now, "op": "PARSE", "input": text, "output": out})
    append_jsonl(tiers["mtm"], {"ts": now, "op": "PARSE", "intent": intent})
    return out

def service_api(msg: Dict[str, Any]):
    op = (msg or {}).get("op"," ").upper()
    mid = msg.get("mid") or generate_mid()
    payload = msg.get("payload") or {}
    if op == "HEALTH":
        return success_response(op, mid, {"status":"operational","memory_health": _counts()})
    if op == "PARSE":
        return success_response(op, mid, _parse(str(payload.get("text","")), payload.get("delta") or {}))
    return error_response(op, mid, "UNSUPPORTED_OP", op)
