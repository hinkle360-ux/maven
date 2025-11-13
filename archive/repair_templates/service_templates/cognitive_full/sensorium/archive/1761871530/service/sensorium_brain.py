
from __future__ import annotations
import time, json
from pathlib import Path
from typing import Dict, Any
from api.utils import generate_mid, success_response, error_response
from api.memory import ensure_dirs, append_jsonl, count_lines

from pathlib import Path
import json
from api.utils import CFG

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

HERE = Path(__file__).resolve().parent; BRAIN_ROOT = HERE.parent
def _counts(): t=ensure_dirs(BRAIN_ROOT); return {"stm": count_lines(t["stm"]), "mtm": count_lines(t["mtm"]), "ltm": count_lines(t["ltm"]), "cold": count_lines(t["cold"])}
def _normalize(text: str) -> Dict[str, Any]:
    w = _read_weights(BRAIN_ROOT); parse_bias = float(w.get("parse_priority",0.5))
    s=" ".join((text or "").split()).lower()
    is_ascii=all(ord(ch)<128 for ch in s); has_digit=any(ch.isdigit() for ch in s)
    input_type="text" if parse_bias>=0.5 else ("number" if s.isdigit() else ("mix" if has_digit else "text"))
    lang="english" if is_ascii else "unknown"
    out={"normalized": s, "type": input_type, "language": lang, "confidence": 0.35, "weights_used": w}
    t=ensure_dirs(BRAIN_ROOT); now=time.time(); append_jsonl(t["stm"], {"ts":now,"op":"NORMALIZE","input":text,"output":out}); append_jsonl(t["mtm"], {"ts":now,"op":"NORMALIZE","type":input_type,"lang":lang}); return out
def service_api(msg):
    op=(msg or {}).get("op"," ").upper(); mid=msg.get("mid") or generate_mid(); payload=msg.get("payload") or {}
    if op=="HEALTH": return success_response(op, mid, {"status":"operational","memory_health": _counts()})
    if op=="NORMALIZE": return success_response(op, mid, _normalize(str(payload.get("text",""))))
    return error_response(op, mid, "UNSUPPORTED_OP", op)
