from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Any
import re

# Deferred import for affect modulation.  Importing inside the PLAN
# operation avoids circular dependencies when the affect brain itself
# imports the planner.  We guard failures gracefully.
import importlib

HERE = Path(__file__).resolve().parent
BRAIN_ROOT = HERE.parent

def _guess_intents_targets(text: str):
    text_l = (text or "").lower()
    intents = []
    targets = []
    # intents (very light heuristics)
    if any(w in text_l for w in ["show", "display", "find", "search", "retrieve"]):
        intents.append("retrieve_relevant_memories")
    if any(w in text_l for w in ["explain", "why", "how"]):
        intents.append("compose_explanation")
    if not intents:
        intents.append("compose_response")
    # targets/entities
    toks = [t.strip(",.!?") for t in (text or "").split()]
    for t in toks:
        if t and (t[0].isupper() or t.lower() in ("paris","eiffel","tower","photos")):
            targets.append(t)
    # dedupe preserving order
    seen=set(); targets = [x for x in targets if not (x in seen or seen.add(x))]
    return intents, targets

def service_api(msg: Dict[str, Any]) -> Dict[str, Any]:
    from api.utils import generate_mid, success_response, error_response  # type: ignore
    from api.memory import ensure_dirs, append_jsonl, rotate_if_needed, compute_success_average  # type: ignore
    op = (msg or {}).get("op"," ").upper()
    mid = msg.get("mid") or generate_mid()
    payload = msg.get("payload") or {}

    # ------------------------------------------------------------------
    # Step‑4: handshake from working memory
    # PLAN_FROM_WM creates a single goal entry based on a WM event.  When
    # an entry contains tags=["plan"], a goal identifier prefixed with
    # WM_PLAN: is returned and a governance audit entry may be recorded.  The
    # implementation is deliberately simple: only one goal is created per
    # invocation and duplicate calls with the same key do not create
    # multiple goals.  The ledger location is reused from existing plan
    # storage to maintain consistency.
    if op == "PLAN_FROM_WM":
        entry = payload.get("entry") or {}
        key = str(entry.get("key", ""))
        # Create a deterministic goal ID for this WM entry
        goal_id = f"WM_PLAN:{key}"
        # Append to the system goals ledger if not already present
        try:
            root = Path(__file__).resolve().parents[4]
            ledger_path = root / "reports" / "system" / "goals.json"
            ledger_path.parent.mkdir(parents=True, exist_ok=True)
            existing: list[Any] = []
            if ledger_path.exists():
                try:
                    existing = json.loads(ledger_path.read_text(encoding="utf-8"))
                except Exception:
                    existing = []
            # Check if goal already exists
            exists = any(isinstance(g, dict) and g.get("goal_id") == goal_id for g in existing)
            if not exists:
                # Persist new goal with minimal information
                rec = {"goal_id": goal_id, "source": "PLAN_FROM_WM"}
                existing.append(rec)
                with open(ledger_path, "w", encoding="utf-8") as fh:
                    json.dump(existing, fh, indent=2)
        except Exception:
            pass
        return success_response(op, mid, {"goal": goal_id})
    # Health check
    if op == "HEALTH":
        t = ensure_dirs(BRAIN_ROOT)
        append_jsonl(t["stm"], {"op": "HEALTH"})
        # Rotate memory to prevent overflow of planner logs
        try:
            rotate_if_needed(BRAIN_ROOT)
        except Exception:
            pass
        return success_response(op, mid, {"status": "operational"})
    # Generate a basic plan for user requests and track long‑term goals.
    if op == "PLAN":
        text = str(payload.get("text", ""))
        intent = str(payload.get("intent", "")).upper()
        context = payload.get("context") or {}
        motivation = payload.get("motivation")

        # Affect modulation: score the input text to derive valence,
        # arousal and priority delta.  Defer import to runtime to avoid
        # circular dependencies.
        affect: Dict[str, Any] = {}
        try:
            ap_mod = importlib.import_module(
                "brains.cognitive.affect_priority.service.affect_priority_brain"
            )
            aff_res = ap_mod.service_api({"op": "SCORE", "payload": {"text": text}})
            affect = aff_res.get("payload") or {}
        except Exception:
            affect = {}

        # Step 2: Determine plan structure based on intent
        plan_id = f"plan_{int(importlib.import_module('time').time() * 1000)}"
        steps: list[Dict[str, Any]] = []
        priority = 0.5
        can_parallelize = False

        # Simple Q&A (simple_fact_query, question)
        if intent in ("SIMPLE_FACT_QUERY", "QUESTION", "QUERY"):
            steps = [
                {"id": "s1", "kind": "retrieve", "target": "personal_memory", "status": "pending"},
                {"id": "s2", "kind": "reason", "status": "pending"},
                {"id": "s3", "kind": "compose_answer", "status": "pending"},
            ]
            priority = 0.7

        # Explain / Why / How
        elif intent in ("EXPLAIN", "WHY", "HOW"):
            steps = [
                {"id": "s1", "kind": "retrieve", "target": "all_banks", "status": "pending"},
                {"id": "s2", "kind": "reason", "target": "chain_facts", "status": "pending"},
                {"id": "s3", "kind": "compose_explanation", "status": "pending"},
            ]
            priority = 0.8

        # Compare ("compare A and B")
        elif intent == "COMPARE":
            # Extract comparison targets from text if possible
            text_lower = text.lower()
            targets_a = []
            targets_b = []
            if " and " in text_lower:
                parts = text_lower.split(" and ", 1)
                # Extract nouns/entities from each part
                import re
                targets_a = re.findall(r'\b[A-Za-z]+\b', parts[0])[-3:] if parts[0] else []
                targets_b = re.findall(r'\b[A-Za-z]+\b', parts[1])[:3] if len(parts) > 1 else []

            steps = [
                {"id": "s1", "kind": "retrieve", "target": "subject_a", "subjects": targets_a, "status": "pending"},
                {"id": "s2", "kind": "retrieve", "target": "subject_b", "subjects": targets_b, "status": "pending"},
                {"id": "s3", "kind": "reason", "target": "highlight_differences", "status": "pending"},
                {"id": "s4", "kind": "compose_comparison", "status": "pending"},
            ]
            priority = 0.85

        # User command ("do X", "summarize", "analyze this")
        elif intent in ("COMMAND", "REQUEST", "ANALYZE"):
            steps = [
                {"id": "s1", "kind": "interpret_command", "status": "pending"},
                {"id": "s2", "kind": "retrieve", "target": "relevant_context", "status": "pending"},
                {"id": "s3", "kind": "act", "target": "action_engine", "status": "pending"},
                {"id": "s4", "kind": "compose_result", "status": "pending"},
            ]
            priority = 0.9
            can_parallelize = False

        # Preference/identity queries
        elif intent in ("PREFERENCE_QUERY", "IDENTITY_QUERY", "RELATIONSHIP_QUERY"):
            steps = [
                {"id": "s1", "kind": "retrieve", "target": "personal_memory", "status": "pending"},
                {"id": "s2", "kind": "reason", "status": "pending"},
                {"id": "s3", "kind": "compose_answer", "status": "pending"},
            ]
            priority = 0.75

        # Unknown or unsupported intent
        else:
            if intent:
                steps = [
                    {"id": "s1", "kind": "fail", "reason": "unsupported_intent", "intent": intent, "status": "pending"}
                ]
            else:
                # No intent provided - create a generic plan
                intents, targets = _guess_intents_targets(text)
                steps = [
                    {"id": "s1", "kind": "retrieve", "target": "general", "status": "pending"},
                    {"id": "s2", "kind": "reason", "status": "pending"},
                    {"id": "s3", "kind": "compose_response", "status": "pending"},
                ]
            priority = 0.5

        # Add backward compatibility fields (intents/targets)
        intents, targets = _guess_intents_targets(text)

        plan: Dict[str, Any] = {
            "plan_id": plan_id,
            "goal": f"Satisfy user request: {text}",
            "steps": steps,
            "priority": priority,
            "can_parallelize": can_parallelize,
            "intent": intent,
            "intents": intents,  # Backward compatibility
            "targets": targets,  # Backward compatibility
            "notes": "Step 2 planner: real multi-step plan"
        }
        # Record affect metrics in the plan
        if affect:
            plan["affect"] = affect
            # Derive a high‑level mood indicator from valence
            try:
                val = float(affect.get("valence", 0.0))
            except Exception:
                val = 0.0
            if val > 0.2:
                mood = "upbeat"
            elif val < -0.2:
                mood = "cautious"
            else:
                mood = "neutral"
            plan["mood"] = mood
        # Incorporate a learned bias into the plan based on recent success history.
        try:
            learned_bias = compute_success_average(BRAIN_ROOT)
        except Exception:
            learned_bias = 0.0
        # Adjust learned bias using the affect‑derived priority delta if available
        try:
            delta = float(affect.get("priority_delta", 0.0))
        except Exception:
            delta = 0.0
        plan["learned_bias"] = learned_bias + delta
        # Persist the plan to the memory tiers for traceability.  A placeholder
        # success field is included so that the memory librarian can mark
        # successful plans after reasoning verdicts.
        try:
            t = ensure_dirs(BRAIN_ROOT)
            append_jsonl(t["stm"], {"op": "PLAN", "input": text, "plan": plan, "success": None})
            append_jsonl(t["mtm"], {"op": "PLAN", "intents": intents, "targets": targets})
            rotate_if_needed(BRAIN_ROOT)
        except Exception:
            pass
        # Persist the plan to the goals ledger for long‑term tracking
        try:
            # Ascend to the Maven root to locate reports/system
            root = Path(__file__).resolve().parents[4]
            ledger_path = root / "reports" / "system" / "goals.json"
            ledger_path.parent.mkdir(parents=True, exist_ok=True)
            goals_data: list[Any] = []
            if ledger_path.exists():
                try:
                    with open(ledger_path, "r", encoding="utf-8") as f:
                        goals_data = json.load(f)
                except Exception:
                    goals_data = []
            goals_data.append({"plan": plan})
            with open(ledger_path, "w", encoding="utf-8") as f:
                json.dump(goals_data, f, indent=2)
        except Exception:
            # Ignore failures to persist goals
            pass

        # Split the request into sub‑tasks and record each as a persistent goal.
        # STEP 2: Only do this if steps weren't already set by intent-based planning
        if not steps or (len(steps) == 1 and steps[0].get("kind") == "fail"):
            try:
                # First, detect simple conditional patterns of the form
                # Detect conditional patterns and sequence instructions into sub‑goals.  We
                # handle three forms:
                #   1) "if X then Y" → second goal runs on success of first.
                #   2) "if not X then Y" or "if X fails then Y" → second goal runs on
                #      failure of first.
                #   3) "unless X, Y" (or "unless X then Y") → equivalent to
                #      "if not X then Y".
                segments: list[str] = []
                conditions: list[Optional[str]] = []
                # Pattern for "unless" conditions
                unless_match = re.search(r"\bunless\s+(.+?)\s*(?:,\s*|\s+then\s+)(.+)", text, flags=re.IGNORECASE)
                # Pattern for generic "if X then Y"
                cond_match = re.search(r"\bif\s+(.+?)\s+then\s+(.+)", text, flags=re.IGNORECASE)
                if unless_match:
                    cond_part = unless_match.group(1).strip()
                    action_part = unless_match.group(2).strip()
                    if cond_part:
                        segments.append(cond_part)
                        conditions.append(None)
                    if action_part:
                        segments.append(action_part)
                        # For "unless", the action triggers on failure of the condition
                        conditions.append("failure")
                elif cond_match:
                    cond_part = cond_match.group(1).strip()
                    action_part = cond_match.group(2).strip()
                    trigger = "success"
                    # If the condition includes negation or mentions failure, set trigger to failure
                    if re.search(r"\bnot\b", cond_part, flags=re.IGNORECASE) or re.search(r"fail", cond_part, flags=re.IGNORECASE):
                        trigger = "failure"
                    if cond_part:
                        segments.append(cond_part)
                        conditions.append(None)
                    if action_part:
                        segments.append(action_part)
                        conditions.append(trigger)
                else:
                    # Split by sequencing conjunctions for simple lists of tasks
                    raw_segments = [s.strip() for s in re.split(
                        r"\b(?:and|then|after|before|once\s+you\s+have|once\s+you\'ve|once)\b|,",
                        text,
                        flags=re.IGNORECASE,
                    ) if s and s.strip()]
                    segments = raw_segments
                    conditions = [None for _ in segments]
                # Only record goals when more than one segment is detected
                # NOTE: This sets plan["steps"] to a list of strings for backward compatibility
                # In Step 2, we prefer structured step dicts, so only use this fallback
                # when no structured steps were created above
                if len(segments) > 1:
                    plan["steps"] = segments
                    # Also update the "steps" variable for goal memory below
                    steps = segments
                try:
                    from brains.personal.memory import goal_memory  # type: ignore
                    prev_id: str | None = None
                    # The first segment becomes the parent goal; all
                    # subsequent segments are children of the first to
                    # construct a hierarchical plan.  The previous
                    # segment ID still determines the linear dependency.
                    root_id: str | None = None
                    for seg, cond in zip(segments, conditions):
                        try:
                            parent_arg = None
                            depends_arg = None
                            # The first segment has no dependencies; we
                            # treat it as the root.  Subsequent segments
                            # depend on the immediate previous goal.  We no
                            # longer assign a parent_id for sub‑goals to
                            # avoid conflicting hierarchy and dependency
                            # specifications.
                            if prev_id:
                                depends_arg = [prev_id]
                            # Create the goal.  Only depends_on is used for
                            # sequencing; parent_id is not specified for
                            # sub‑goals to simplify the structure.
                            rec = goal_memory.add_goal(
                                seg,
                                depends_on=depends_arg,
                                condition=cond,
                                parent_id=None,
                            )
                            if isinstance(rec, dict) and rec.get("goal_id"):
                                if root_id is None:
                                    root_id = rec["goal_id"]
                                prev_id = rec["goal_id"]
                        except Exception:
                            continue
                except Exception:
                    pass
            except Exception:
                pass
        return success_response(op, mid, plan)
    # Unsupported operations
    return error_response(op, mid, "UNSUPPORTED_OP", op)

# ---------------------------------------------------------------------------
# Handle wrapper for planner entry point
# ---------------------------------------------------------------------------

# Save reference to original service_api implementation
_service_api_impl = service_api

def handle(msg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle function that calls the planner service implementation.

    This wrapper provides a consistent entry point name across all
    cognitive service modules.

    Args:
        msg: Request dictionary with 'op' and optional 'payload'

    Returns:
        Response dictionary from planner service
    """
    return _service_api_impl(msg)

# Service API entry point
service_api = handle