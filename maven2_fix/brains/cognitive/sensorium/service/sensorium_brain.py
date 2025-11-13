
from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Any

def _read_weights(root: Path):
    from api.utils import CFG  # type: ignore
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

HERE = Path(__file__).resolve().parent; BRAIN_ROOT = HERE.parent
def _counts():
    """Return a dictionary with the count of records in each memory tier.

    Invokes ``rotate_if_needed`` prior to counting to ensure that older
    records are rotated into deeper tiers before assessing memory health.
    """
    from api.memory import rotate_if_needed, ensure_dirs, count_lines  # type: ignore
    # Rotate memory before computing counts to mitigate overflow
    try:
        rotate_if_needed(BRAIN_ROOT)
    except Exception:
        pass
    t = ensure_dirs(BRAIN_ROOT)
    return {
        "stm": count_lines(t["stm"]),
        "mtm": count_lines(t["mtm"]),
        "ltm": count_lines(t["ltm"]),
        "cold": count_lines(t["cold"]),
    }
def _normalize(text: str) -> Dict[str, Any]:
    from api.memory import compute_success_average, ensure_dirs, append_jsonl, rotate_if_needed  # type: ignore
    # Read weights and compute a learned bias based on recent success history.
    w = _read_weights(BRAIN_ROOT)
    parse_bias = float(w.get("parse_priority", 0.5))
    # Compute learned bias from recent successes (range [0,1])
    try:
        learned_bias = compute_success_average(BRAIN_ROOT)
    except Exception:
        learned_bias = 0.0
    # Normalize the input string and detect simple type/language heuristics
    s = " ".join((text or "").split()).lower()
    is_ascii = all(ord(ch) < 128 for ch in s)
    has_digit = any(ch.isdigit() for ch in s)
    input_type = "text" if parse_bias >= 0.5 else ("number" if s.isdigit() else ("mix" if has_digit else "text"))
    lang = "english" if is_ascii else "unknown"
    # Augment weights with the learned bias for traceability
    try:
        w_with_bias = dict(w)
        w_with_bias["learned_bias"] = learned_bias
    except Exception:
        w_with_bias = w
        w_with_bias["learned_bias"] = learned_bias
    out = {
        "normalized": s,
        "type": input_type,
        "language": lang,
        "confidence": 0.35,
        "weights_used": w_with_bias
    }
    # Persist normalization results into STM and MTM tiers, tagging with a placeholder
    # success flag that will later be updated by the memory librarian.
    t = ensure_dirs(BRAIN_ROOT)
    try:
        append_jsonl(t["stm"], {"op": "NORMALIZE", "input": text, "output": out, "success": None})
        append_jsonl(t["mtm"], {"op": "NORMALIZE", "type": input_type, "lang": lang})
    except Exception:
        pass
    # Rotate records across tiers according to configured thresholds to prevent overflow
    try:
        rotate_if_needed(BRAIN_ROOT)
    except Exception:
        pass
    return out
def service_api(msg):
    from api.utils import generate_mid, success_response, error_response  # type: ignore
    op=(msg or {}).get("op"," ").upper(); mid=msg.get("mid") or generate_mid(); payload=msg.get("payload") or {}
    if op=="HEALTH": return success_response(op, mid, {"status":"operational","memory_health": _counts()})
    if op=="NORMALIZE": return success_response(op, mid, _normalize(str(payload.get("text",""))))
    return error_response(op, mid, "UNSUPPORTED_OP", op)

# Ensure the sensorium brain exposes a `handle` entry point
try:
    handle = service_api  # type: ignore[assignment]
    service_api = handle  # type: ignore[assignment]
except Exception:
    pass
