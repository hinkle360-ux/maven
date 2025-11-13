from __future__ import annotations
import importlib.util, sys, time, json
from pathlib import Path
from typing import Dict, Any

LIB_FILE = Path(__file__).resolve()
SERVICE_DIR = LIB_FILE.parent
COG_ROOT = SERVICE_DIR.parent.parent
MAVEN_ROOT = COG_ROOT.parent.parent
sys.path.insert(0, str(MAVEN_ROOT))

from api.utils import generate_mid, success_response, error_response, write_report, CFG
from api.memory import ensure_dirs, count_lines

def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod

def _bank_module(name: str):
    svc = MAVEN_ROOT / "brains" / "domain_banks" / name / "service" / f"{name}_bank.py"
    return _load_module(svc, f"bank_{name}_service")

def _brain_module(name: str):
    svc = COG_ROOT / name / "service" / f"{name}_brain.py"
    return _load_module(svc, f"brain_{name}_service")

def _gov_module():
    svc = MAVEN_ROOT / "brains" / "governance" / "policy_engine" / "service" / "policy_engine.py"
    return _load_module(svc, "policy_engine_service")

def _repair_module():
    svc = MAVEN_ROOT / "brains" / "governance" / "repair_engine" / "service" / "repair_engine.py"
    return _load_module(svc, "repair_engine_service")

def _personal_module():
    svc = MAVEN_ROOT / "brains" / "personal" / "service" / "personal_brain.py"
    return _load_module(svc, "personal_brain_service")

def _retrieve_from_banks(query: str, k: int = 5) -> Dict[str, Any]:
    banks = ["arts","science","history","economics","geography","language_arts","law","math","philosophy","technology"]
    results = []; searched = []
    for b in banks:
        try:
            r = _bank_module(b).service_api({"op":"RETRIEVE","payload":{"query": query, "limit": k}})
            if r.get("ok"):
                pay = r.get("payload") or {}; rr = pay.get("results") or []
                for item in rr:
                    if isinstance(item, dict) and "source_bank" not in item: item["source_bank"] = b
                results.extend(rr); searched.append(b)
        except Exception: pass
    return {"results": results, "banks": searched}

def _scan_counts(root: Path) -> Dict[str, Dict[str, int]]:
    from api.memory import tiers_for
    out = {}
    brains = ["sensorium","planner","language","pattern_recognition","reasoning","affect_priority","personality","self_dmn","system_history","memory_librarian"]
    for brain in brains:
        broot = root / brain
        t = tiers_for(broot)
        out[brain] = { tier: count_lines(path) for tier, path in t.items() }
    try:
        personal_root = MAVEN_ROOT / "brains" / "personal"
        t = tiers_for(personal_root)
        out["personal"] = { tier: count_lines(path) for tier, path in t.items() }
    except Exception:
        out["personal"] = {}
    return out

def service_api(msg: Dict[str, Any]) -> Dict[str, Any]:
    op = (msg or {}).get("op"," ").upper()
    mid = msg.get("mid") or generate_mid()
    payload = msg.get("payload") or {}

    if op == "RUN_PIPELINE":
        text = str(payload.get("text","")); conf = float(payload.get("confidence", 0.8))

        # Personality snapshot
        try:
            from brains.cognitive.personality.service import personality_brain
            prefs = personality_brain._read_preferences()
        except Exception:
            prefs = {"prefer_explain": True, "tone": "neutral", "verbosity_target": 1.0}
        ctx = {"original_query": text, "timestamp": time.time(), "personality_snapshot": prefs}

        # Stage 1b Personality proposal → governance
        suggestion = {}
        try:
            from brains.cognitive.personality.service import personality_brain
            sug = personality_brain.service_api({"op":"ADAPT_WEIGHTS_SUGGEST"}) or {}
            suggestion = (sug.get("payload") or {}).get("suggestion") or {}
        except Exception:
            suggestion = {}
        try:
            gov = _gov_module()
            adj_enf = gov.service_api({"op":"ENFORCE","payload":{"action":"ADJUST_WEIGHTS","payload": suggestion}})
            approved = bool((adj_enf.get("payload") or {}).get("allowed"))
        except Exception:
            approved = False
        ctx["stage_1b_personality_adjustment"] = {"proposal": suggestion, "approved": approved}

        # S1..S4
        s = _brain_module("sensorium").service_api({"op":"NORMALIZE","payload":{"text": text}})
        p = _brain_module("planner").service_api({"op":"PLAN","payload":{"text": text, "delta": (suggestion.get("planner") if approved else {})}})
        l = _brain_module("language").service_api({"op":"PARSE","payload":{"text": text, "delta": (suggestion.get("language") if approved else {})}})
        try:
            pr = _brain_module("pattern_recognition").service_api({"op":"ANALYZE","payload":{"text": text}})
        except Exception:
            pr = {"ok": True, "payload": {"skipped": True}}

        ctx["stage_1_sensorium"] = s.get("payload", {})
        ctx["stage_2_planner"] = p.get("payload", {})
        if not ctx["stage_2_planner"]:
            ctx["stage_2_planner"] = {
                "goal": f"Satisfy user request: {text}",
                "intents": ["retrieve_relevant_memories","compose_response"],
                "notes": "Planner fallback: source=Librarian safeguard"
            }
        ctx["stage_3_language"] = l.get("payload", {})
        ctx["stage_4_pattern_recognition"] = pr.get("payload", {})

        # Stage 2R — Memory-first retrieval
        mem = _retrieve_from_banks(text, k=5)
        ctx["stage_2R_memory"] = mem

        ctx["stage_0_weights_used"] = {
            "sensorium": ctx["stage_1_sensorium"].get("weights_used"),
            "planner": ctx["stage_2_planner"].get("weights_used"),
            "language": ctx["stage_3_language"].get("weights_used"),
        }

        # Validate + governance
        proposed = {"content": text, "confidence": conf, "source": "user_input"}
        v = _brain_module("reasoning").service_api({"op":"EVALUATE_FACT","payload":{"proposed_fact": proposed, "evidence": ctx.get("stage_2R_memory")}})
        ctx["stage_8_validation"] = v.get("payload", {})

        bias_profile = {
            "planner": ctx["stage_2_planner"].get("weights_used"),
            "language": ctx["stage_3_language"].get("weights_used"),
            "reasoning": ctx["stage_8_validation"].get("weights_used"),
            "personality": prefs,
            "adjustment_proposal": suggestion
        }
        gov = _gov_module()
        enf = gov.service_api({"op":"ENFORCE","payload":{"action":"STORE","payload": proposed, "bias_profile": bias_profile}})
        ctx["stage_8b_governance"] = enf.get("payload", {})
        allowed = enf.get("payload", {}).get("allowed", False)

        # Simple bank route
        def _route_bank(text: str) -> str:
            s = text.lower()
            if any(w in s for w in ["gravity","atom","cell","physics","chemistry","mitosis","blue sky","light","scatter"]): return "science"
            if any(w in s for w in ["born","died","founded","established"]): return "history"
            return "arts"
        bank = _route_bank(text)

        # Dedup guard
        def _is_duplicate(evidence, content: str) -> bool:
            try:
                for it in (evidence or {}).get("results", []):
                    if isinstance(it, dict) and str(it.get("content","")).strip().lower() == str(content).strip().lower():
                        return True
            except Exception:
                pass
            return False
        duplicate = _is_duplicate(ctx.get("stage_2R_memory"), proposed.get("content",""))

        # Store with mode-aware routing + resolve theories on factual
        mode = ctx["stage_8_validation"].get("mode")
        if allowed:
            if duplicate:
                ctx["stage_9_storage"] = {"skipped": True, "reason": "duplicate_evidence"}
            elif mode == "RETRIEVED":
                fact_payload = {**proposed, "validated_by":"reasoning", "verification_level":"factual"}
                st = _bank_module(bank).service_api({"op":"STORE","payload":{"fact": fact_payload}})
                if not st.get("ok"):
                    _repair_module().service_api({"op":"REPAIR","payload":{"rule":"missing_bank","target": (Path(__file__).resolve().parents[4] / "brains" / "domain_banks" / bank)}})
                    st = _bank_module(bank).service_api({"op":"STORE","payload":{"fact": fact_payload}})
                try:
                    _bank_module("theories_and_contradictions").service_api({"op":"RESOLVE_MATCHES","payload":{"content": proposed.get("content","")}})
                except Exception:
                    pass
                ctx["stage_9_storage"] = {"bank": bank, **(st.get("payload") or {})}
            elif mode == "EDUCATED_GUESS":
                try:
                    tac = _bank_module("theories_and_contradictions").service_api({"op":"STORE_THEORY","payload":{"fact": {**proposed, "source_brain":"reasoning", "verification_level":"educated_guess"}}})
                    ctx["stage_9_storage"] = {"bank": "theories_and_contradictions", **(tac.get("payload") or {})}
                except Exception as e:
                    ctx["stage_9_storage"] = {"bank": "theories_and_contradictions", "error": str(e)}
            else:
                try:
                    tac = _bank_module("theories_and_contradictions").service_api({"op":"STORE_CONTRADICTION","payload":{"fact": {**proposed, "source_brain":"reasoning", "status":"open", "verification_level":"unknown"}}})
                    ctx["stage_9_storage"] = {"bank": "theories_and_contradictions", **(tac.get("payload") or {})}
                except Exception as e:
                    ctx["stage_9_storage"] = {"bank": "theories_and_contradictions", "error": str(e)}
        else:
            ctx["stage_9_storage"] = {"skipped": True, "reason": "governance_denied_or_validation_reject"}

        # Stage 10 Personality feedback
        try:
            from brains.cognitive.personality.service import personality_brain
            fb = {
                "goal": ctx["stage_2_planner"].get("goal"),
                "tone": ctx["stage_3_language"].get("tone"),
                "verbosity_hint": ctx["stage_3_language"].get("verbosity_hint"),
                "decision": (ctx["stage_8b_governance"].get("decision") or {}).get("decision"),
                "bank": ctx.get("stage_9_storage", {}).get("bank")
            }
            personality_brain.service_api({"op":"LEARN_FROM_RUN","payload": fb})
            ctx["stage_10_personality_feedback"] = {"logged": True}
        except Exception as e:
            ctx["stage_10_personality_feedback"] = {"logged": False, "error": str(e)}

        # Stage 11 — Personal Brain (boost + why + signals)
        try:
            per_boost = _personal_module().service_api({"op": "SCORE_BOOST", "payload": {"subject": text}})
            per_why = _personal_module().service_api({"op": "WHY", "payload": {"subject": text}})
            ctx["stage_11_personal_influence"] = {
                **(per_boost.get("payload") or {}),
                "why": (per_why.get("payload") or {}).get("hypothesis"),
                "signals": (per_why.get("payload") or {}).get("signals", [])
            }
        except Exception as e:
            ctx["stage_11_personal_influence"] = {"error": str(e)}

        # Post-run: System History and Self-DMN lightweight logs (non-blocking)
        try:
            hist = _brain_module("system_history")
            hist.service_api({"op":"LOG_RUN_SUMMARY","payload":{
                "ts": int(time.time()),
                "text": text,
                "mode": ctx["stage_8_validation"].get("mode"),
                "bank": ctx.get("stage_9_storage", {}).get("bank"),
                "personal_boost": (ctx.get("stage_11_personal_influence") or {}).get("boost", 0.0)
            }})
            ctx["stage_12_system_history"] = {"logged": True}
        except Exception as e:
            ctx["stage_12_system_history"] = {"logged": False, "error": str(e)}

        try:
            sdmn = _brain_module("self_dmn")
            met = sdmn.service_api({"op":"ANALYZE_INTERNAL","payload":{"window": 10}})
            ctx["stage_13_self_dmn"] = {"metrics": (met.get("payload") or {}).get("metrics")}
        except Exception as e:
            ctx["stage_13_self_dmn"] = {"error": str(e)}

        write_report("system", f"run_{int(time.time())}.json", json.dumps(ctx, indent=2))
        return success_response(op, mid, {"context": ctx})

    if op == "HEALTH_CHECK":
        counts = _scan_counts(COG_ROOT); rotated = []; limit = CFG["rotation"]["stm_records"] * 2; rep = _repair_module()
        for brain, tiers in counts.items():
            stm_count = int(tiers.get("stm", 0))
            if stm_count > limit:
                if brain == "personal":
                    stm_path = (MAVEN_ROOT / "brains" / "personal" / "memory" / "stm" / "records.jsonl").resolve()
                else:
                    stm_path = (COG_ROOT / brain / "memory" / "stm" / "records.jsonl").resolve()
                rep.service_api({"op":"REPAIR","payload":{"rule":"memory_overflow","target": str(stm_path)}})
                rotated.append({"brain": brain, "stm_count": stm_count, "rule":"memory_overflow"})
        write_report("system", f"health_{int(time.time())}.json", json.dumps({"counts": counts, "rotations": rotated}, indent=2))
        return success_response(op, mid, {"rotations": rotated, "counts": counts})

    return error_response(op, mid, "UNSUPPORTED_OP", op)
