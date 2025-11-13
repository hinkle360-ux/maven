
from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, List
import json

HERE = Path(__file__).resolve().parent
BRAIN_ROOT = HERE.parent

def _counts():
    from api.memory import ensure_dirs, count_lines  # type: ignore
    t = ensure_dirs(BRAIN_ROOT)
    return {"stm": count_lines(t["stm"]), "mtm": count_lines(t["mtm"]), "ltm": count_lines(t["ltm"]), "cold": count_lines(t["cold"])}

def _log_reflections(reflections: List[Dict[str, Any]]):
    from api.memory import ensure_dirs, append_jsonl  # type: ignore
    t = ensure_dirs(BRAIN_ROOT)
    for r in reflections or []:
        append_jsonl(t["stm"], {"op":"REFLECTION", "content": r.get("content",""), "confidence": r.get("confidence",0.5), "source": r.get("source","system_internal")})

def service_api(msg):
    from api.utils import generate_mid, success_response, error_response  # type: ignore
    op = (msg or {}).get("op"," ").upper()
    mid = msg.get("mid") or generate_mid()
    payload = msg.get("payload") or {}

    if op == "HEALTH":
        return success_response(op, mid, {"status": "operational", "memory_health": _counts()})

    if op == "LOG_REFLECTIONS":
        _log_reflections(payload.get("reflections") or [])
        return success_response(op, mid, {"logged": len(payload.get("reflections") or [])})

    if op == "SUMMARIZE":
        """
        Summarize recent system and self-DMN activity into a compact health dashboard.

        This operation reads the most recent run_*.json files from reports/system and
        the audit.jsonl from reports/self_dmn.  It aggregates governance decisions,
        memory usage, bank frequencies, popular topics and a sample of recent Q/A.
        The summary is written to reports/health_dashboard/bundle_<timestamp>.json.
        Optionally, older run logs are rotated, keeping only the last 500 to avoid
        excessive disk use.
        """
        # Determine project root and report directories
        try:
            project_root = Path(__file__).resolve().parents[4]
        except Exception:
            project_root = Path.cwd()
        sys_dir = project_root / "reports" / "system"
        self_dir = project_root / "reports" / "self_dmn"
        health_dir = project_root / "reports" / "health_dashboard"
        health_dir.mkdir(parents=True, exist_ok=True)
        # Determine window of runs to analyze
        try:
            window = int(payload.get("window", 50))
        except Exception:
            window = 50
        # Collect run files
        run_files: List[Path] = []
        try:
            for f in sys_dir.glob("run_*.json"):
                run_files.append(f)
        except Exception:
            run_files = []
        # Sort by modification time and keep last 'window'
        run_files = sorted(run_files, key=lambda p: p.stat().st_mtime)[-window:]
        summary = {
            "aggregated": {
                "runs_analyzed": len(run_files),
                "decisions": {"ALLOW": 0, "DENY": 0, "QUARANTINE": 0, "RECOMPUTE": 0},
                "bank_usage": {},
                "top_likes": [],
            },
            "samples": []
        }
        # Load personal top likes
        try:
            import importlib
            personal = importlib.import_module("brains.personal.service.personal_brain")
            top_res = personal.service_api({"op": "TOP_LIKES", "payload": {"limit": 5}})
            top_items = (top_res.get("payload") or {}).get("items") or []
            summary["aggregated"]["top_likes"] = [
                {"subject": item.get("subject"), "score_boost": item.get("score_boost")} for item in top_items
            ]
        except Exception:
            summary["aggregated"]["top_likes"] = []
        # Count governance decisions and bank usage, and collect Q/A samples
        for rf in run_files:
            try:
                data = json.loads(rf.read_text(encoding="utf-8"))
            except Exception:
                continue
            # decisions from governance
            try:
                decision = str(((data.get("stage_8b_governance") or {}).get("decision") or {}).get("decision", "")).upper()
            except Exception:
                decision = ""
            if decision in {"ALLOW", "DENY", "QUARANTINE"}:
                summary["aggregated"]["decisions"][decision] += 1
            # bank usage
            bank = (data.get("stage_9_storage") or {}).get("bank")
            if bank:
                summary["aggregated"]["bank_usage"][bank] = summary["aggregated"]["bank_usage"].get(bank, 0) + 1
            # sample Q/A: use original query and final answer if available
            oq = data.get("original_query")
            ans = data.get("final_answer") or data.get("stage_10_finalize", {}).get("text")
            if oq and ans:
                summary["samples"].append({"query": oq, "answer": ans})
        # Count recompute actions from self‑DMN audit
        try:
            audit_path = self_dir / "audit.jsonl"
            recompute_count = 0
            if audit_path.exists():
                with open(audit_path, "r", encoding="utf-8") as fh:
                    for ln in fh:
                        try:
                            obj = json.loads(ln.strip())
                        except Exception:
                            continue
                        st = str(obj.get("status") or "")
                        if st == "recompute" or st == "disputed":
                            recompute_count += 1
            summary["aggregated"]["decisions"]["RECOMPUTE"] = recompute_count
        except Exception:
            pass
        # Persist summary to health dashboard
        try:
            import random
            fname = health_dir / f"bundle_{random.randint(100000, 999999)}.json"
            with open(fname, "w", encoding="utf-8") as fh:
                json.dump(summary, fh, indent=2)
        except Exception:
            pass
        # Rotate old run logs if the count exceeds 500
        try:
            all_runs = sorted(sys_dir.glob("run_*.json"), key=lambda p: p.stat().st_mtime)
            if len(all_runs) > 500:
                excess = all_runs[: len(all_runs) - 500]
                for p in excess:
                    try:
                        p.unlink()
                    except Exception:
                        continue
        except Exception:
            pass
        return success_response(op, mid, {"summary": summary})

    return error_response(op, mid, "UNSUPPORTED_OP", op)

# Ensure the system_history brain exposes a `handle` entry point
try:
    handle = service_api  # type: ignore[assignment]
    service_api = handle  # type: ignore[assignment]
except Exception:
    pass
