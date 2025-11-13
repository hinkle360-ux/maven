
from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Any

HERE = Path(__file__).resolve().parent
BRAIN_ROOT = HERE.parent

PREFS_DEFAULT = {"prefer_explain": True, "tone": "neutral", "verbosity_target": 1.0}

def _prefs_path() -> Path:
    return BRAIN_ROOT / "preferences.json"

def _read_preferences() -> dict:
    p = _prefs_path()
    if not p.exists():
        p.write_text(json.dumps(PREFS_DEFAULT, indent=2), encoding="utf-8")
        return dict(PREFS_DEFAULT)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return dict(PREFS_DEFAULT)

def _counts() -> Dict[str, int]:
    """Return a mapping of record counts for each memory tier after rotation."""
    from api.memory import rotate_if_needed, ensure_dirs, count_lines  # type: ignore
    # Rotate memory before computing counts to avoid overflow warnings
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

def _load_aggregate() -> Dict[str, Any]:
    agg_path = BRAIN_ROOT / "memory" / "mtm" / "aggregate.json"
    if not agg_path.exists():
        return {}
    try:
        return json.loads(agg_path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _save_aggregate(agg: Dict[str, Any]) -> None:
    agg_path = BRAIN_ROOT / "memory" / "mtm" / "aggregate.json"
    agg_path.parent.mkdir(parents=True, exist_ok=True)
    agg_path.write_text(json.dumps(agg, indent=2), encoding="utf-8")

def _update_aggregate_from_run(payload: Dict[str, Any]) -> Dict[str, Any]:
    agg = _load_aggregate() or {"total_runs": 0, "allowed": 0, "denied": 0, "quarantined": 0,
                                "tone_stats": {}, "goal_stats": {}}
    tone = (payload.get("tone") or "unknown")
    goal = (payload.get("goal") or "unknown")
    decision = (payload.get("decision") or "ALLOW")
    agg["total_runs"] = int(agg.get("total_runs", 0)) + 1
    if str(decision).upper() == "ALLOW":
        agg["allowed"] = int(agg.get("allowed", 0)) + 1
    elif str(decision).upper() == "DENY":
        agg["denied"] = int(agg.get("denied", 0)) + 1
    else:
        agg["quarantined"] = int(agg.get("quarantined", 0)) + 1
    agg.setdefault("tone_stats", {})
    agg.setdefault("goal_stats", {})
    agg["tone_stats"][tone] = int(agg["tone_stats"].get(tone, 0)) + 1
    agg["goal_stats"][goal] = int(agg["goal_stats"].get(goal, 0)) + 1
    _save_aggregate(agg)
    return agg

def _clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))

def _suggest_from_aggregate(agg: Dict[str, Any], prefs: Dict[str, Any]) -> Dict[str, Any]:
    # Always return a structured proposal when we have at least 10 runs
    total = int(agg.get("total_runs", 0) or 0)
    if total < 10:
        return {"planner": {"explain_bias_delta": 0.0},
                "language": {"verbosity_bias_delta": 0.0, "tone": prefs.get("tone", "neutral")}}

    goals = agg.get("goal_stats", {}) or {}
    tones = agg.get("tone_stats", {}) or {}
    respond = int(goals.get("respond", 0))
    explain = int(goals.get("explain", 0))
    # We also count 'answer_question' as respond-style
    respond += int(goals.get("answer_question", 0))
    respond_ratio = respond / total if total else 0.0
    explain_ratio = explain / total if total else 0.0

    # Planner: nudge toward balance using tiny, bounded steps
    if explain_ratio >= 0.70:
        planner_delta = +0.05
    elif respond_ratio >= 0.70:
        planner_delta = -0.05
    else:
        planner_delta = 0.0

    # Language: move bias toward target (default 1.0 means neutral)
    target = float(prefs.get("verbosity_target", 1.0) or 1.0)
    if target > 1.0:
        lang_delta = +min(0.10, target - 1.0)
    elif target < 1.0:
        lang_delta = -min(0.10, 1.0 - target)
    else:
        # If neutral target, derive a mild delta from tone prevalence
        lang_delta = 0.05 if (tones.get("neutral", 0) / total if total else 0) >= 0.60 else 0.0

    # Tone suggestion = majority tone if it clears 60%
    tone_suggest = None
    if tones:
        top_tone, top_ct = max(tones.items(), key=lambda kv: kv[1])
        if (top_ct / total) >= 0.60:
            tone_suggest = top_tone
    proposal = {
        "planner": {"explain_bias_delta": _clip(planner_delta, -0.10, +0.10)},
        "language": {"verbosity_bias_delta": _clip(lang_delta, -0.10, +0.10)}
    }
    if tone_suggest:
        proposal["language"]["tone"] = tone_suggest
    return proposal

def service_api(msg: Dict[str, Any]) -> Dict[str, Any]:
    from api.utils import generate_mid, success_response, error_response  # type: ignore
    from api.memory import ensure_dirs, append_jsonl, rotate_if_needed  # type: ignore
    op = (msg or {}).get("op"," ").upper()
    mid = msg.get("mid") or generate_mid()
    payload = msg.get("payload") or {}

    if op == "HEALTH":
        return success_response(op, mid, {"status":"operational","memory_health": _counts()})

    if op == "PREFERENCES_SNAPSHOT":
        return success_response(op, mid, {"preferences": _read_preferences()})

    if op == "LEARN_FROM_RUN":
        # primitive logging
        t = ensure_dirs(BRAIN_ROOT)
        rec = {
            "goal": payload.get("goal"),
            "tone": payload.get("tone"),
            "verbosity": payload.get("verbosity_hint"),
            "decision": payload.get("decision"),
            "bank": payload.get("bank")
        }
        append_jsonl(t["stm"], rec)
        # update aggregate directly
        agg = _update_aggregate_from_run(payload)
        append_jsonl(t["stm"], {"op": "AGG_UPDATE", "aggregate_total_runs": agg.get("total_runs", 0)})
        # Rotate records to prevent personality STM overflow
        try:
            rotate_if_needed(BRAIN_ROOT)
        except Exception:
            pass
        return success_response(op, mid, {"logged": True, "aggregate_total_runs": agg.get("total_runs", 0)})

    if op == "ADAPT_WEIGHTS_SUGGEST":
        agg = _load_aggregate()
        prefs = _read_preferences()
        suggestion = _suggest_from_aggregate(agg, prefs)
        t = ensure_dirs(BRAIN_ROOT)
        append_jsonl(t["stm"], {"op": "ADAPT_SUGGEST", "suggestion": suggestion})
        # Rotate records to manage memory after suggestion logging
        try:
            rotate_if_needed(BRAIN_ROOT)
        except Exception:
            pass
        return success_response(op, mid, {"suggestion": suggestion})

    return error_response(op, mid, "UNSUPPORTED_OP", op)

# Ensure the personality brain exposes a `handle` entry point
try:
    handle = service_api  # type: ignore[assignment]
    service_api = handle  # type: ignore[assignment]
except Exception:
    pass
