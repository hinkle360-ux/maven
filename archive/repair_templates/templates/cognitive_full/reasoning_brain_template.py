from __future__ import annotations
import time, json
from pathlib import Path
from typing import Dict, Any, List
from api.utils import generate_mid, success_response, error_response
from api.memory import ensure_dirs, append_jsonl, count_lines
from api.utils import CFG

HERE = Path(__file__).resolve().parent
BRAIN_ROOT = HERE.parent

BASE_TRUE = 0.7
BASE_THEORY = 0.4

def _read_weights(root: Path):
    p = root / "weights.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return CFG.get("weights_defaults", {})
    w = CFG.get("weights_defaults", {})
    p.write_text(json.dumps(w, indent=2), encoding="utf-8")
    return w

def _counts():
    t = ensure_dirs(BRAIN_ROOT)
    return {"stm": count_lines(t["stm"]), "mtm": count_lines(t["mtm"]), "ltm": count_lines(t["ltm"]), "cold": count_lines(t["cold"])}

def _evaluate_fact(payload: Dict[str, Any]) -> Dict[str, Any]:
    proposed = payload.get("proposed_fact") or {}
    evidence = payload.get("evidence")
    w = _read_weights(BRAIN_ROOT)
    parse_bias = float(w.get("parse_priority", 0.5))

    th_true = min(0.95, max(0.05, BASE_TRUE + (0.05 if parse_bias > 0.55 else (-0.05 if parse_bias < 0.45 else 0.0))))
    th_theory = min(th_true - 0.05, max(0.05, BASE_THEORY + (0.05 if parse_bias > 0.55 else (-0.05 if parse_bias < 0.45 else 0.0))))
    conf = float(proposed.get("confidence", 0.5))

    # Evidence details
    items: List[dict] = []
    if isinstance(evidence, dict):
        items = evidence.get("results") or []
    ids, banks = [], []
    for it in items:
        if isinstance(it, dict):
            rid = it.get("id") or it.get("record_id") or it.get("stored_id")
            if rid: ids.append(rid)
            b = it.get("bank") or it.get("domain") or it.get("source_bank")
            if b: banks.append(b)
    ev_summary = {"count": len(items), "ids": ids[:20], "banks": list(dict.fromkeys(banks))[:10]}

    has_retrieved = ev_summary["count"] > 0
    if has_retrieved and conf >= th_theory:
        mode = "RETRIEVED"; route = "factual"; verification_level = 'validated'
        inference_method = "direct_retrieval"
        explanation = "Validated using prior stored records."
        source_records = ids[:10]
    elif conf >= th_theory:
        mode = "EDUCATED_GUESS"; route = "working_theories"; verification_level = "educated_guess"
        # Minimal, explicit methodology
        inference_method = "contextual_similarity"
        explanation = "No direct memory hit; inferred from patterns and thresholds."
        source_records = ids[:10]  # may be empty
    else:
        mode = "UNKNOWN"; route = None; verification_level = "unknown"
        inference_method = "insufficient_evidence"
        explanation = "Confidence below theory threshold; not enough information."
        source_records = []

    verdict = "TRUE" if (mode == "RETRIEVED" and conf >= th_true) else ("THEORY" if mode == "EDUCATED_GUESS" else "REJECT")

    out = {
        "verdict": verdict,
        "mode": mode,
        "confidence": conf,
        "route": route,
        "verification_level": verification_level,
        "thresholds": {"true": th_true, "theory": th_theory},
        "weights_used": w,
        "evidence": ev_summary,
        "inference_method": inference_method,
        "source_records": source_records,
        "rationale": ("Based on retrieved memory evidence." if mode == "RETRIEVED"
                      else ("Inference from available signals." if mode == "EDUCATED_GUESS"
                            else "Not enough information to answer.")),
        "explanation": explanation
    }

    tiers = ensure_dirs(BRAIN_ROOT)
    now = time.time()
    append_jsonl(tiers["stm"], {"ts": now, "op": "EVALUATE_FACT", "input": proposed, "output": out})
    append_jsonl(tiers["mtm"], {"ts": now, "op": "EVALUATE_FACT", "verdict": verdict, "mode": mode, "conf": conf})
    return out

def service_api(msg):
    op = (msg or {}).get("op"," ").upper()
    mid = msg.get("mid") or generate_mid()
    payload = msg.get("payload") or {}
    if op == "HEALTH":
        return success_response(op, mid, {"status":"operational","memory_health": _counts()})
    if op == "EVALUATE_FACT":
        return success_response(op, mid, _evaluate_fact(payload))
    return error_response(op, mid, "UNSUPPORTED_OP", op)
