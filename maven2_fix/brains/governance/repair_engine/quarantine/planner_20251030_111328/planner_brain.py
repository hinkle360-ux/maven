
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

def _plan(text: str, delta: dict = None) -> dict:
    w = _read_weights(BRAIN_ROOT)
    try:
        d = float((delta or {}).get("explain_bias_delta", 0.0))
    except Exception:
        d = 0.0
    base_explain = float(w.get("explain_bias", 0.5))
    eff_explain = _clip(base_explain + d, 0.0, 1.0)

    t = (text or "").strip().lower()
    if t.endswith("?"):
        goal = "answer_question" if eff_explain < 0.55 else "explain"
    else:
        goal = "explain" if eff_explain >= 0.55 else "respond"

    out = {
        "goal": goal,
        "constraints": ["primitive", "short"],
        "timestamp": time.time(),
        "weights_used": {"explain_bias": eff_explain}
    }

    tiers = ensure_dirs(BRAIN_ROOT)
    now = time.time()
    append_jsonl(tiers["stm"], {
        "ts": now,
        "op": "ADJUST_WEIGHTS",
        "base": {"explain_bias": base_explain},
        "delta": {"explain_bias": d},
        "effective": {"explain_bias": eff_explain}
    })
    append_jsonl(tiers["stm"], {"ts": now, "op": "PLAN", "input": text, "output": out})
    append_jsonl(tiers["mtm"], {"ts": now, "op": "PLAN", "goal": goal})
    return out

def service_api(msg: Dict[str, Any]):
    op = (msg or {}).get("op"," ").upper()
    mid = msg.get("mid") or generate_mid()
    payload = msg.get("payload") or {}
    if op == "HEALTH":
        return success_response(op, mid, {"status":"operational","memory_health": _counts()})
    if op == "PLAN":
        return success_response(op, mid, _plan(str(payload.get("text","")), payload.get("delta") or {}))
    return error_response(op, mid, "UNSUPPORTED_OP", op)

# Ensure the quarantined planner brain exposes a `handle` entry point
try:
    handle = service_api  # type: ignore[assignment]
    service_api = handle  # type: ignore[assignment]
except Exception:
    pass
