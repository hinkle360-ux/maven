
from __future__ import annotations
import json, time, glob
from pathlib import Path
from typing import Dict, Any, List
from api.utils import generate_mid, success_response, error_response
from api.memory import ensure_dirs, append_jsonl, count_lines

HERE = Path(__file__).resolve().parent
BRAIN_ROOT = HERE.parent

def _counts():
    t = ensure_dirs(BRAIN_ROOT)
    return {"stm": count_lines(t["stm"]), "mtm": count_lines(t["mtm"]), "ltm": count_lines(t["ltm"]), "cold": count_lines(t["cold"])}

def _load_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _analyze_reports(project_root: Path, window:int=10) -> Dict[str, Any]:
    system_dir = project_root / "reports" / "system"
    bias_dir = project_root / "reports" / "bias_audit"
    repairs_dir = project_root / "reports" / "governance" / "repairs"

    runs = sorted(system_dir.glob("run_*.json"))[-window:]
    quarantines = 0; allows = 0; denies = 0
    stores = 0
    for rp in runs:
        data = _load_json(rp)
        gov = (data.get("stage_8b_governance") or {})
        dec = (gov.get("decision") or {}).get("decision")
        if dec == "QUARANTINE":
            quarantines += 1
        elif dec == "ALLOW":
            allows += 1
            if "stage_9_storage" in data and "stored_id" in (data["stage_9_storage"] or {}):
                stores += 1
        elif dec == "DENY":
            denies += 1

    bias_files = sorted(bias_dir.glob("bias_*.jsonl"))[-window:]
    bias_samples = 0; avg_explain = 0.0; avg_verbosity = 0.0; avg_parse = 0.0
    for bp in bias_files:
        try:
            with open(bp, "r", encoding="utf-8") as f:
                for ln in f:
                    bias_samples += 1
                    try:
                        obj = json.loads(ln.strip())
                    except Exception:
                        continue
                    b = obj.get("bias") or {}
                    avg_explain += float((b.get("planner") or {}).get("explain_bias", 0.5))
                    avg_verbosity += float((b.get("language") or {}).get("verbosity_bias", 0.5))
                    avg_parse += float((b.get("reasoning") or {}).get("parse_priority", 0.5))
        except Exception:
            continue
    if bias_samples:
        avg_explain /= bias_samples; avg_verbosity /= bias_samples; avg_parse /= bias_samples

    repair_files = sorted(repairs_dir.glob("repairs_*.jsonl"))[-window:]
    repair_events = 0
    for rp in repair_files:
        try:
            with open(rp, "r", encoding="utf-8") as f:
                for _ in f:
                    repair_events += 1
        except Exception:
            continue

    return {
        "window": window,
        "counts": {
            "runs": len(runs),
            "allows": allows, "denies": denies, "quarantines": quarantines,
            "stores": stores, "repairs": repair_events
        },
        "averages": {
            "explain_bias": round(avg_explain, 3),
            "verbosity_bias": round(avg_verbosity, 3),
            "parse_priority": round(avg_parse, 3)
        }
    }

def _draft_reflections(metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
    c = metrics.get("counts", {}); a = metrics.get("averages", {}); w = metrics.get("window", 10)
    items = []
    items.append({"content": f"Over the last {w} runs, governance allowed {c.get('allows',0)} and quarantined {c.get('quarantines',0)}.", "confidence": 0.8, "source": "system_internal"})
    items.append({"content": f"{c.get('stores',0)} facts were stored successfully.", "confidence": 0.8, "source": "system_internal"})
    items.append({"content": f"Average explain_bias {a.get('explain_bias',0.5):.2f}, verbosity_bias {a.get('verbosity_bias',0.5):.2f}, parse_priority {a.get('parse_priority',0.5):.2f}.", "confidence": 0.8, "source": "system_internal"})
    if c.get("repairs",0) > 0:
        items.append({"content": f"Repair engine executed {c['repairs']} actions in the last {w} runs.", "confidence": 0.8, "source": "system_internal"})
    return items

def service_api(msg):
    op = (msg or {}).get("op"," ").upper()
    mid = msg.get("mid") or generate_mid()
    payload = msg.get("payload") or {}

    if op == "HEALTH":
        return success_response(op, mid, {"status": "operational", "memory_health": _counts()})

    if op == "ANALYZE_INTERNAL":
        project_root = Path(__file__).resolve().parents[4]
        metrics = _analyze_reports(project_root, int(payload.get("window",10)))
        t = ensure_dirs(BRAIN_ROOT); append_jsonl(t["stm"], {"ts": time.time(), "op":"ANALYZE_INTERNAL", "metrics": metrics})
        return success_response(op, mid, {"metrics": metrics})

    if op == "DRAFT_REFLECTIONS":
        metrics = payload.get("metrics") or {}
        drafts = _draft_reflections(metrics)
        t = ensure_dirs(BRAIN_ROOT); append_jsonl(t["stm"], {"ts": time.time(), "op":"DRAFT_REFLECTIONS", "drafts": drafts})
        return success_response(op, mid, {"drafts": drafts})

    return error_response(op, mid, "UNSUPPORTED_OP", op)
