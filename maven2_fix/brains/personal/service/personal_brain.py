from __future__ import annotations
import json, time, uuid, math
from typing import Any, Dict, List
from pathlib import Path
import sys

# ===== Placement =====
HERE = Path(__file__).resolve().parent
BRAIN_ROOT = HERE.parent  # .../personal/
PROJECT_ROOT = BRAIN_ROOT
while PROJECT_ROOT.name not in ["personal", "maven"] and PROJECT_ROOT.parent != PROJECT_ROOT:
    PROJECT_ROOT = PROJECT_ROOT.parent
MAVEN_ROOT = PROJECT_ROOT.parent if PROJECT_ROOT.name == "personal" else PROJECT_ROOT
sys.path.append(str(MAVEN_ROOT))

# Shared utils
try:
    from api.utils import generate_mid, success_response, error_response
except Exception:
    def generate_mid() -> str: return f"MID-{int(time.time()*1000)}"
    def success_response(op, mid, payload): return {"ok": True, "op": op, "mid": mid, "payload": payload}
    def error_response(op, mid, code, message): return {"ok": False, "op": op, "mid": mid, "error": {"code": code, "message": message}}

# ===== Memory tiers (JSONL) =====
TIERS = {
    "stm": BRAIN_ROOT / "memory" / "stm" / "prefs.jsonl",
    "mtm": BRAIN_ROOT / "memory" / "mtm" / "prefs.jsonl",
    "ltm": BRAIN_ROOT / "memory" / "ltm" / "prefs.jsonl",
    "cold": BRAIN_ROOT / "memory" / "cold" / "archive.jsonl",
    "logs": BRAIN_ROOT / "memory" / "stm" / "logs.jsonl",
}
for p in TIERS.values():
    p.parent.mkdir(parents=True, exist_ok=True)

def _append_jsonl(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj) + "\n")

def _counts() -> Dict[str, int]:
    c = {}
    for k, p in TIERS.items():
        if p.exists():
            with p.open("r", encoding="utf-8") as f:
                c[k] = sum(1 for _ in f)
        else:
            c[k] = 0
    return c

# ===== Preference primitives =====
def _make_pref(subject: str, valence: float, intensity: float, source: str, note: str|None=None) -> dict:
    now = time.time()
    return {
        "id": str(uuid.uuid4()),
        "ts": now,
        "subject": subject.strip(),
        "valence": max(-1.0, min(1.0, float(valence))),
        "intensity": max(0.0, min(1.0, float(intensity))),
        "confidence": 0.6,
        "stability_half_life_days": 180,
        "origin": source or "self_report",
        "signals": [{"ts": now, "source": source, "weight": float(intensity)}],
        "hypothesis": note or "",
        "explanations": [],
        "last_updated": now,
        "privacy_tags": ["personal", "exportable:false"],
    }

def _key(s: str) -> str:
    return " ".join(s.lower().split())

def _load_all() -> List[dict]:
    out: List[dict] = []
    for path in [TIERS["ltm"], TIERS["mtm"], TIERS["stm"]]:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                try: out.append(json.loads(line))
                except Exception: continue
    return out

def _upsert(subject: str, delta_valence: float, intensity: float, source: str, note: str|None=None) -> dict:
    subj_key = _key(subject)
    allrecs = _load_all()
    latest_by_subject = {}
    for r in allrecs:
        latest_by_subject[_key(r.get("subject",""))] = r
    if subj_key in latest_by_subject:
        r = latest_by_subject[subj_key]
        days = (time.time() - r.get("last_updated", r.get("ts", 0))) / 86400.0
        decay = min(0.25, max(0.0, days / 365.0))
        new_valence = max(-1.0, min(1.0, r.get("valence", 0.0) * (1.0 - decay) + delta_valence * intensity))
        agree = (r.get("valence", 0.0) * new_valence) >= 0
        conf = r.get("confidence", 0.6)
        conf = max(0.0, min(1.0, conf + (0.05 if agree else -0.07)))
        r.update({
            "valence": new_valence,
            "intensity": max(0.0, min(1.0, (r.get("intensity", 0.5) + intensity) / 2.0)),
            "confidence": conf,
            "last_updated": time.time(),
        })
        r.setdefault("signals", []).append({"ts": time.time(), "source": source, "weight": float(intensity), "note": note or ""})
    else:
        r = _make_pref(subject, delta_valence, intensity, source, note)
    _append_jsonl(TIERS["stm"], r)
    return r

def _boost(subject: str) -> float:
    subj_key = _key(subject)
    latest = {}
    for r in _load_all():
        latest[_key(r.get("subject",""))] = r
    r = latest.get(subj_key)
    if not r:
        return 0.0
    age_days = (time.time() - r.get("last_updated", r.get("ts", 0))) / 86400.0
    freshness = max(0.6, 1.0 - min(0.5, age_days / 365.0))
    raw = r.get("valence", 0.0) * r.get("intensity", 0.5) * r.get("confidence", 0.6) * freshness
    return max(-0.25, min(0.25, raw))

def _top_likes(limit: int = 10) -> List[dict]:
    latest = {}
    for r in _load_all():
        latest[_key(r.get("subject",""))] = r
    scored = [( _boost(r.get("subject","")), r) for r in latest.values()]
    scored.sort(key=lambda t: t[0], reverse=True)
    return [dict(r, score_boost=round(b, 4)) for b, r in scored[:max(1, int(limit))]]

def _why(subject: str) -> dict:
    subj_key = _key(subject)
    latest = {}
    for r in _load_all():
        latest[_key(r.get("subject",""))] = r
    r = latest.get(subj_key)
    if not r:
        return {"subject": subject, "found": False, "signals": []}
    return {"subject": r["subject"], "found": True, "valence": r["valence"], "intensity": r["intensity"],
            "confidence": r["confidence"], "signals": r.get("signals", []), "hypothesis": r.get("hypothesis","")}

def _export(filter_tags: List[str] | None) -> List[dict]:
    out = []
    tags = set([t.strip() for t in (filter_tags or []) if t.strip()])
    for r in _load_all():
        priv = set(r.get("privacy_tags", []))
        if "exportable:false" in priv and not tags:
            continue
        if tags and not (tags & priv):
            continue
        out.append(r)
    return out

# ===== service_api =====
def service_api(msg: Dict[str, Any]) -> Dict[str, Any]:
    op = (msg or {}).get("op"," ").upper()
    mid = msg.get("mid") or generate_mid()
    payload = msg.get("payload") or {}
    try:
        if op == "HEALTH":
            # Report supported operations.  Include new goal memory ops when
            # available.  The list is used by tests and monitoring tools
            # to introspect the capabilities of the personal brain.
            return success_response(op, mid, {"status": "operational", "type": "personal_brain", "memory_health": _counts(), "ops": [
                # Preference recording
                "RECORD_LIKE","RECORD_DISLIKE","REINFORCE","SET_PRIVACY",
                "TOP_LIKES","WHY","SCORE_BOOST","EXPORT",
                # Goal management
                "ADD_GOAL","GET_GOALS","COMPLETE_GOAL",
                # Topic statistics
                "TOPIC_STATS","TOPIC_TRENDS",
                # Knowledge graph operations
                "ADD_FACT","QUERY_FACT","LIST_FACTS",
                "LIST_RELATIONS","GROUP_KG_BY_RELATION",
                "UPDATE_FACT","REMOVE_FACT","QUERY_RELATION",
                "IMPORT_FACTS","EXPORT_FACTS",
                # Meta confidence and statistics
                "META_CONFIDENCE",
                "META_STATS",
                "META_TRENDS",
                "FACT_COUNT",
                # QA memory search
                "SEARCH_QA",
                # Synonym mapping operations
                "ADD_SYNONYM",
                "GET_CANONICAL",
                "LIST_SYNONYMS",
                "REMOVE_SYNONYM",
                "LIST_SYNONYM_GROUPS",
                # Knowledge graph search
                "SEARCH_KG",
                # Canonical knowledge graph search
                "SEARCH_KG_CANONICAL",
                # Extended KG operations (V2)
                "ADD_RELATION","REMOVE_RELATION","LIST_RULES","ADD_RULE","RUN_INFERENCE","EXPORT_KG_V2","IMPORT_KG_V2",
                # Synonym search
                "SEARCH_SYNONYMS",
                # Canonical QA memory search
                "SEARCH_QA_CANONICAL",
                # QA memory summarization
                "SUMMARIZE_QA",
                # Goal summary
                "GOAL_SUMMARY",
                # Goal introspection
                "GET_GOAL",
                "GOAL_DEPENDENCIES",
                # Hierarchical goal operations
                "GET_GOAL_TREE",
                "SET_DEADLINE",
                "UPDATE_PROGRESS",
                # Domain statistics and classification
                "DOMAIN_STATS",
                # User knowledge operations
                "USER_KNOWLEDGE_STATS",
                "RESET_USER_KNOWLEDGE",
                # User profile operations
                "UPDATE_PROFILE","GET_PROFILE","GET_ATTRIBUTE",
                # Diagnostics
                "INTROSPECT",
                # Synonym import/export
                "IMPORT_SYNONYMS","EXPORT_SYNONYMS",
                # User mood operations
                "GET_MOOD","UPDATE_MOOD","RESET_MOOD",
                # Safety rules operations
                "LIST_SAFETY_RULES","ADD_SAFETY_RULE","RESET_SAFETY_RULES"
            ]})
        if op == "RECORD_LIKE":
            r = _upsert(str(payload.get("subject","")).strip(), +1.0, float(payload.get("intensity", 0.6)), payload.get("source","self_report"), payload.get("note"))
            return success_response(op, mid, {"record": r, "boost": _boost(r["subject"])})

        if op == "RECORD_DISLIKE":
            r = _upsert(str(payload.get("subject","")).strip(), -1.0, float(payload.get("intensity", 0.6)), payload.get("source","self_report"), payload.get("note"))
            return success_response(op, mid, {"record": r, "boost": _boost(r["subject"])})

        if op == "REINFORCE":
            r = _upsert(str(payload.get("subject","")).strip(), float(payload.get("delta", 0.2)), float(payload.get("weight", 0.2)), payload.get("source","behavior"))
            return success_response(op, mid, {"record": r, "boost": _boost(r["subject"])})

        if op == "SET_PRIVACY":
            subj = str(payload.get("subject","")).strip()
            tags = [t.strip() for t in (payload.get("tags") or []) if t and isinstance(t, str)]
            _append_jsonl(TIERS["stm"], {"ts": time.time(), "subject": subj, "privacy_update": tags})
            return success_response(op, mid, {"subject": subj, "tags": tags})

        if op == "TOP_LIKES":
            limit = int(payload.get("limit", 10))
            return success_response(op, mid, {"items": _top_likes(limit)})

        if op == "WHY":
            return success_response(op, mid, _why(str(payload.get("subject",""))))

        if op == "SCORE_BOOST":
            return success_response(op, mid, {"subject": payload.get("subject"), "boost": _boost(str(payload.get("subject","")))})

        # --- Goal memory operations ----------------------------------------
        # These operations allow the agent or user to persist and manage
        # long‑horizon goals.  Goals can be added, listed and marked
        # complete via the personal brain API.  Goals are stored in a
        # JSONL file maintained by the goal_memory module.  See
        # brains/personal/memory/goal_memory.py for implementation details.
        try:
            # Lazily import the goal memory helper.  The import is inside
            # this block to avoid mandatory dependency when goal memory is
            # unused or missing.
            from brains.personal.memory import goal_memory  # type: ignore
        except Exception:
            goal_memory = None  # type: ignore

        if op == "ADD_GOAL":
            if goal_memory is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Goal memory not available")
            title = str(payload.get("title",""))
            description = payload.get("description")
            rec = goal_memory.add_goal(title, description)
            return success_response(op, mid, {"goal": rec})

        if op == "GET_GOALS":
            if goal_memory is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Goal memory not available")
            active_only = bool(payload.get("active_only", False))
            items = goal_memory.get_goals(active_only=active_only)
            return success_response(op, mid, {"goals": items})

        if op == "COMPLETE_GOAL":
            if goal_memory is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Goal memory not available")
            goal_id = str(payload.get("goal_id", ""))
            if not goal_id:
                return error_response(op, mid, "INVALID_REQUEST", "goal_id is required")
            # Default to success=True when marking a goal complete via the API.
            rec = goal_memory.complete_goal(goal_id, success=True)
            if rec is None:
                return error_response(op, mid, "NOT_FOUND", f"Goal {goal_id} not found")
            return success_response(op, mid, {"goal": rec})

        # --- Goal introspection operations -----------------------------------
        # Fetch details for a single goal by its identifier.  Useful for
        # debugging goal chains or providing detailed information about a
        # pending task.
        if op == "GET_GOAL":
            if goal_memory is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Goal memory not available")
            goal_id = str(payload.get("goal_id", "")).strip()
            if not goal_id:
                return error_response(op, mid, "INVALID_REQUEST", "goal_id is required")
            rec = goal_memory.get_goal(goal_id)
            if rec is None:
                return error_response(op, mid, "NOT_FOUND", f"Goal {goal_id} not found")
            return success_response(op, mid, {"goal": rec})

        # Return the dependency chain for a given goal.  The chain is
        # returned as a list of goal records, ordered from the immediate
        # dependency to the most distant.  If the goal has no
        # dependencies or does not exist, an empty list is returned.
        if op == "GOAL_DEPENDENCIES":
            if goal_memory is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Goal memory not available")
            goal_id = str(payload.get("goal_id", "")).strip()
            if not goal_id:
                return error_response(op, mid, "INVALID_REQUEST", "goal_id is required")
            deps = goal_memory.get_dependency_chain(goal_id)
            return success_response(op, mid, {"dependencies": deps})

        # Return a hierarchical tree of goals starting from the given parent.
        # This operation builds a nested structure where each node includes
        # its goal record and its children.  It is useful for visualising
        # compound tasks broken into sub‑tasks.  If the parent goal is
        # missing, an empty structure is returned.
        if op == "GET_GOAL_TREE":
            if goal_memory is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Goal memory not available")
            root_id = str(payload.get("goal_id", "")).strip()
            if not root_id:
                return error_response(op, mid, "INVALID_REQUEST", "goal_id is required")
            root = goal_memory.get_goal(root_id)
            if not root:
                return success_response(op, mid, {"tree": None})
            # Build tree recursively
            def build_tree(node_id: str) -> Dict[str, Any]:
                node_rec = goal_memory.get_goal(node_id) or {}
                children = goal_memory.children_of(node_id)
                return {
                    "goal": node_rec,
                    "children": [build_tree(child.get("goal_id")) for child in children if child.get("goal_id")]
                }
            tree = build_tree(root_id)
            return success_response(op, mid, {"tree": tree})

        # Update or set a deadline on a goal.  The deadline may be
        # provided as a Unix timestamp (seconds since epoch) or an ISO
        # 8601 string (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS).  If omitted or
        # invalid, the deadline is removed.
        if op == "SET_DEADLINE":
            if goal_memory is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Goal memory not available")
            goal_id = str(payload.get("goal_id", "")).strip()
            if not goal_id:
                return error_response(op, mid, "INVALID_REQUEST", "goal_id is required")
            deadline = payload.get("deadline")
            ts: Optional[float] = None
            if deadline is not None:
                # Attempt to parse numeric timestamp
                try:
                    ts = float(deadline)
                except Exception:
                    # Try ISO format parse
                    try:
                        from datetime import datetime
                        # Replace 'T' with space for flexibility
                        deadline_str = str(deadline).replace("T", " ").strip()
                        # Try date only (no time) or full datetime
                        if len(deadline_str) == 10:
                            dt = datetime.fromisoformat(deadline_str)
                        else:
                            # Try to parse with both date and time
                            dt = datetime.fromisoformat(deadline_str)
                        ts = dt.timestamp()
                    except Exception:
                        ts = None
            rec = goal_memory.set_deadline(goal_id, ts)  # type: ignore[arg-type]
            if rec is None:
                return error_response(op, mid, "NOT_FOUND", f"Goal {goal_id} not found")
            return success_response(op, mid, {"goal": rec})

        # Update progress for a goal and optionally merge metrics.  Progress
        # must be between 0 and 1.  Metrics should be a JSON object.
        if op == "UPDATE_PROGRESS":
            if goal_memory is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Goal memory not available")
            goal_id = str(payload.get("goal_id", "")).strip()
            if not goal_id:
                return error_response(op, mid, "INVALID_REQUEST", "goal_id is required")
            try:
                prog = float(payload.get("progress", 0.0))
            except Exception:
                prog = 0.0
            metrics = payload.get("metrics")
            if metrics is not None and not isinstance(metrics, dict):
                metrics = None
            rec = goal_memory.update_progress(goal_id, prog, metrics=metrics)  # type: ignore[arg-type]
            if rec is None:
                return error_response(op, mid, "NOT_FOUND", f"Goal {goal_id} not found")
            return success_response(op, mid, {"goal": rec})

        # --- Topic statistics -------------------------------------------------
        # Return aggregated topic counts across questions.  Topic statistics
        # provide insight into frequently asked subjects and support cross‑
        # episode learning.  If the topic_stats helper cannot be imported,
        # return an unsupported operation error.
        if op == "TOPIC_STATS":
            try:
                from brains.personal.memory import topic_stats  # type: ignore
            except Exception:
                topic_stats = None  # type: ignore
            if topic_stats is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Topic statistics not available")
            limit = int(payload.get("limit", 10))
            items = topic_stats.get_stats(limit)
            return success_response(op, mid, {"topics": items})

        # --- Trending topics -------------------------------------------------
        # Return the most frequent topics (alias for TOPIC_STATS).
        if op == "TOPIC_TRENDS":
            try:
                from brains.personal.memory import topic_stats  # type: ignore
            except Exception:
                topic_stats = None  # type: ignore
            if topic_stats is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Topic statistics not available")
            limit = int(payload.get("limit", 10))
            items = topic_stats.get_stats(limit)
            return success_response(op, mid, {"topics": items})

        # --- Semantic memory operations (knowledge graph) --------------------
        # Allow the agent or user to persist simple facts (subject, relation, object)
        # into a knowledge graph, query existing facts, and list recent facts.
        try:
            from brains.personal.memory import knowledge_graph  # type: ignore
        except Exception:
            knowledge_graph = None  # type: ignore

        if op == "ADD_FACT":
            # Add a new fact triple to the knowledge graph
            if knowledge_graph is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Knowledge graph not available")
            subject = str(payload.get("subject", "")).strip()
            relation = str(payload.get("relation", "")).strip()
            obj = str(payload.get("object", "")).strip()
            if not (subject and relation and obj):
                return error_response(op, mid, "INVALID_REQUEST", "subject, relation and object are required")
            try:
                knowledge_graph.add_fact(subject, relation, obj)
            except Exception:
                pass
            return success_response(op, mid, {"added": True})

        if op == "QUERY_FACT":
            # Query the knowledge graph for a subject + relation
            if knowledge_graph is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Knowledge graph not available")
            subject = str(payload.get("subject", "")).strip()
            relation = str(payload.get("relation", "")).strip()
            if not (subject and relation):
                return error_response(op, mid, "INVALID_REQUEST", "subject and relation are required")
            try:
                ans = knowledge_graph.query_fact(subject, relation)
            except Exception:
                ans = None
            return success_response(op, mid, {"answer": ans})

        if op == "LIST_FACTS":
            # List the most recent facts from the knowledge graph
            if knowledge_graph is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Knowledge graph not available")
            try:
                limit = int(payload.get("limit", 10))
            except Exception:
                limit = 10
            try:
                items = knowledge_graph.list_facts(limit)
            except Exception:
                items = []
            return success_response(op, mid, {"facts": items})

        # --- Synonym mapping operations --------------------------------------
        # Provide a simple interface to map informal terms or nicknames to
        # canonical subject names.  This enables the knowledge graph to
        # answer questions phrased via synonyms (e.g. "the red planet" → "mars").
        try:
            from brains.personal.memory import synonyms  # type: ignore
        except Exception:
            synonyms = None  # type: ignore

        if op == "ADD_SYNONYM":
            # Add or update a synonym mapping (synonym → canonical).
            # Expect ``synonym`` and ``canonical`` in the payload.
            if synonyms is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Synonym mapping not available")
            syn = str(payload.get("synonym", "")).strip()
            canon = str(payload.get("canonical", "")).strip()
            if not (syn and canon):
                return error_response(op, mid, "INVALID_REQUEST", "synonym and canonical are required")
            try:
                synonyms.update_synonym(syn, canon)
                return success_response(op, mid, {"updated": True})
            except Exception:
                return error_response(op, mid, "ERROR", "failed to update synonym")

        if op == "GET_CANONICAL":
            # Return the canonical form for a given term.  If no mapping
            # exists, return the lower‑cased term itself.  Expect
            # ``term`` in payload.
            if synonyms is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Synonym mapping not available")
            term = str(payload.get("term", "")).strip()
            if not term:
                return error_response(op, mid, "INVALID_REQUEST", "term is required")
            try:
                canon = synonyms.get_canonical(term)
            except Exception:
                canon = term.strip().lower()
            return success_response(op, mid, {"canonical": canon})

        if op == "LIST_SYNONYMS":
            # Return the entire synonym mapping.  Useful for inspection or
            # debugging.  The mapping keys and values are lower‑cased.
            if synonyms is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Synonym mapping not available")
            try:
                mapping = synonyms.get_mapping()
            except Exception:
                mapping = {}
            return success_response(op, mid, {"synonyms": mapping})

        if op == "REMOVE_SYNONYM":
            # Remove a synonym mapping.  Requires a ``synonym`` field in the payload.
            if synonyms is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Synonym mapping not available")
            syn = str(payload.get("synonym", "")).strip()
            if not syn:
                return error_response(op, mid, "INVALID_REQUEST", "synonym is required")
            try:
                removed = synonyms.remove_synonym(syn)
            except Exception:
                removed = False
            return success_response(op, mid, {"removed": bool(removed)})

        if op == "LIST_SYNONYM_GROUPS":
            # Return groups of synonyms keyed by canonical form.  The groups
            # include the canonical term itself.  Useful for understanding
            # clusters of related terms.
            if synonyms is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Synonym mapping not available")
            try:
                groups = synonyms.list_groups()
            except Exception:
                groups = {}
            return success_response(op, mid, {"groups": groups})

        # --- Domain confidence statistics -----------------------------------
        # Return meta‑confidence statistics across domains (topics).  The
        # meta_confidence helper tracks successes and failures to compute
        # confidence adjustments.  If the helper is unavailable, return an
        # unsupported op error.
        if op == "META_CONFIDENCE" or op == "META_STATS":
            try:
                from brains.personal.memory import meta_confidence  # type: ignore
            except Exception:
                meta_confidence = None  # type: ignore
            if meta_confidence is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Meta confidence not available")
            try:
                limit = int(payload.get("limit", 10))
            except Exception:
                limit = 10
            stats = meta_confidence.get_stats(limit)
            return success_response(op, mid, {"domains": stats})

        # --- Domain confidence trends --------------------------------------
        # Return the domains with the highest and lowest confidence adjustments.
        # This operation surfaces which topics Maven has been excelling at
        # recently (positive adjustments) and which it struggles with
        # (negative adjustments).  The result contains two lists: "improved"
        # and "declined", each sorted by the magnitude of the adjustment.
        if op == "META_TRENDS":
            try:
                from brains.personal.memory import meta_confidence  # type: ignore
            except Exception:
                meta_confidence = None  # type: ignore
            if meta_confidence is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Meta confidence not available")
            try:
                limit = int(payload.get("limit", 5))
            except Exception:
                limit = 5
            stats = meta_confidence.get_stats(1000)
            # Partition into positives and negatives
            improved = [rec for rec in stats if rec.get("adjustment", 0) > 0]
            declined = [rec for rec in stats if rec.get("adjustment", 0) < 0]
            # Sort by adjustment magnitude
            improved.sort(key=lambda r: r.get("adjustment", 0), reverse=True)
            declined.sort(key=lambda r: r.get("adjustment", 0))
            return success_response(op, mid, {
                "improved": improved[:max(1, limit)],
                "declined": declined[:max(1, limit)]
            })

        # --- Knowledge graph statistics -------------------------------------
        # Return a simple count of facts stored in the knowledge graph.  This
        # provides a quick overview of how many semantic entries have been
        # accumulated.  The meta op FACT_COUNT can be used to monitor growth
        # of the semantic memory over time.
        if op == "FACT_COUNT":
            try:
                from brains.personal.memory import knowledge_graph  # type: ignore
            except Exception:
                knowledge_graph = None  # type: ignore
            if knowledge_graph is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Knowledge graph not available")
            try:
                facts = knowledge_graph.list_facts(0)  # return all
                count = len(facts)
            except Exception:
                count = 0
            return success_response(op, mid, {"count": count})

        # --- QA memory search -------------------------------------------
        # Search the cross‑episode QA memory for past questions or answers
        # containing the query string.  This helps the agent recall
        # information from previous sessions and supports near‑perfect
        # retention by exposing relevant history.  The search is
        # case‑insensitive and returns a limited number of matches.
        if op == "SEARCH_QA":
            query = str(payload.get("query", "")).strip().lower()
            try:
                limit = int(payload.get("limit", 10))
            except Exception:
                limit = 10
            if not query:
                return error_response(op, mid, "INVALID_REQUEST", "query is required")
            results: List[Dict[str, Any]] = []
            try:
                qa_path = MAVEN_ROOT / "reports" / "qa_memory.jsonl"
                if qa_path.exists():
                    with qa_path.open("r", encoding="utf-8") as fh:
                        for line in fh:
                            if len(results) >= max(1, limit):
                                break
                            try:
                                rec = json.loads(line)
                            except Exception:
                                continue
                            if not isinstance(rec, dict):
                                continue
                            q = str(rec.get("question", "")).lower()
                            a = str(rec.get("answer", "")).lower()
                            if query in q or query in a:
                                results.append({"question": rec.get("question"), "answer": rec.get("answer"), "ts": rec.get("timestamp")})
                return success_response(op, mid, {"matches": results})
            except Exception as ex:
                return error_response(op, mid, "ERROR", str(ex))

        # --- Knowledge graph search --------------------------------------
        # Search the semantic knowledge graph for facts containing the
        # query string.  This operation returns a list of triples
        # (subject, relation, object) where the query appears in any
        # of the fields.  The search is case‑insensitive and the
        # number of results is bounded by `limit`.  It does not
        # modify the knowledge graph.
        if op == "SEARCH_KG":
            q = str(payload.get("query", "")).strip().lower()
            try:
                limit = int(payload.get("limit", 10))
            except Exception:
                limit = 10
            if not q:
                return error_response(op, mid, "INVALID_REQUEST", "query is required")
            try:
                from brains.personal.memory import knowledge_graph  # type: ignore
            except Exception:
                knowledge_graph = None  # type: ignore
            if knowledge_graph is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Knowledge graph not available")
            matches: List[Dict[str, str]] = []
            try:
                # list_facts(0) returns all facts
                facts = knowledge_graph.list_facts(0)
                q_lower = q.lower()
                for fact in facts:
                    if len(matches) >= max(1, limit):
                        break
                    try:
                        subj = str(fact.get("subject", "")).lower()
                        rel = str(fact.get("relation", "")).lower()
                        obj = str(fact.get("object", "")).lower()
                    except Exception:
                        continue
                    if (q_lower in subj) or (q_lower in rel) or (q_lower in obj):
                        matches.append({"subject": fact.get("subject"), "relation": fact.get("relation"), "object": fact.get("object")})
                return success_response(op, mid, {"matches": matches})
            except Exception as ex:
                return error_response(op, mid, "ERROR", str(ex))

        # --- Canonical knowledge graph search --------------------------------
        # Search the semantic knowledge graph for facts where the query
        # matches either the subject or object after applying synonym
        # canonicalisation.  This operation uses the synonym mapping to
        # normalise both the query and the stored facts.  It returns
        # triples (subject, relation, object) whose canonical subject or
        # object equals the canonical query.  The search is case‑
        # insensitive and respects the provided limit.  If the
        # knowledge graph or synonyms module is unavailable this
        # operation returns UNSUPPORTED_OP.
        if op == "SEARCH_KG_CANONICAL":
            q_raw = str(payload.get("query", "")).strip().lower()
            try:
                limit = int(payload.get("limit", 10))
            except Exception:
                limit = 10
            if not q_raw:
                return error_response(op, mid, "INVALID_REQUEST", "query is required")
            try:
                from brains.personal.memory import knowledge_graph  # type: ignore
            except Exception:
                knowledge_graph = None  # type: ignore
            try:
                from brains.personal.memory import synonyms  # type: ignore
            except Exception:
                synonyms = None  # type: ignore
            if knowledge_graph is None or synonyms is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Knowledge graph or synonyms not available")
            try:
                canonical_q = synonyms.get_canonical(q_raw) if synonyms else q_raw
            except Exception:
                canonical_q = q_raw
            if not canonical_q:
                canonical_q = q_raw
            matches: List[Dict[str, str]] = []
            try:
                facts = knowledge_graph.list_facts(0)
                for fact in facts:
                    if len(matches) >= max(1, limit):
                        break
                    try:
                        subj = str(fact.get("subject", "")).lower()
                        obj = str(fact.get("object", "")).lower()
                    except Exception:
                        continue
                    try:
                        subj_c = synonyms.get_canonical(subj) if synonyms else subj
                    except Exception:
                        subj_c = subj
                    try:
                        obj_c = synonyms.get_canonical(obj) if synonyms else obj
                    except Exception:
                        obj_c = obj
                    if canonical_q == subj_c or canonical_q == obj_c:
                        matches.append({"subject": fact.get("subject"), "relation": fact.get("relation"), "object": fact.get("object")})
                return success_response(op, mid, {"matches": matches})
            except Exception as ex:
                return error_response(op, mid, "ERROR", str(ex))

        # --- Knowledge graph relation listing and grouping ---------------
        # Return a list of unique relations present in the knowledge graph.
        if op == "LIST_RELATIONS":
            try:
                from brains.personal.memory import knowledge_graph  # type: ignore
            except Exception:
                knowledge_graph = None  # type: ignore
            if knowledge_graph is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Knowledge graph not available")
            try:
                rels = knowledge_graph.list_relations()
                return success_response(op, mid, {"relations": rels})
            except Exception as ex:
                return error_response(op, mid, "ERROR", str(ex))

        # Group facts by their relation.  Returns a dict mapping each
        # relation to a list of subject→object pairs.  An optional
        # limit controls the maximum number of facts per relation to
        # return.  Passing limit=0 returns all facts for each relation.
        if op == "GROUP_KG_BY_RELATION":
            try:
                from brains.personal.memory import knowledge_graph  # type: ignore
            except Exception:
                knowledge_graph = None  # type: ignore
            if knowledge_graph is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Knowledge graph not available")
            try:
                limit = int(payload.get("limit", 10))
            except Exception:
                limit = 10
            if limit < 0:
                limit = 0
            try:
                grouped = knowledge_graph.group_by_relation(limit)
                # Convert to simple subject-object pairs
                simplified: Dict[str, List[Dict[str, str]]] = {}
                for rel, facts in grouped.items():
                    lst: List[Dict[str, str]] = []
                    count = 0
                    for fact in facts:
                        if limit and count >= limit:
                            break
                        lst.append({"subject": fact.get("subject"), "object": fact.get("object")})
                        count += 1
                    simplified[rel] = lst
                return success_response(op, mid, {"grouped": simplified})
            except Exception as ex:
                return error_response(op, mid, "ERROR", str(ex))

        # --- Knowledge graph fact update ---------------------------------
        # Update an existing fact or add a new one.  Requires
        # ``subject``, ``relation`` and ``object`` fields.  If a
        # matching (subject, relation) is found, its object will be
        # replaced with the provided ``object``.  If no match exists,
        # the fact will be appended.  Returns whether the update was
        # performed.
        if op == "UPDATE_FACT":
            try:
                from brains.personal.memory import knowledge_graph  # type: ignore
            except Exception:
                knowledge_graph = None  # type: ignore
            if knowledge_graph is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Knowledge graph not available")
            subject = str(payload.get("subject", "")).strip()
            relation = str(payload.get("relation", "")).strip()
            obj = str(payload.get("object", "")).strip()
            if not (subject and relation and obj):
                return error_response(op, mid, "INVALID_REQUEST", "subject, relation and object are required")
            try:
                updated = knowledge_graph.update_fact(subject, relation, obj)
            except Exception:
                updated = False
            return success_response(op, mid, {"updated": bool(updated)})

        # --- Knowledge graph fact removal --------------------------------
        # Remove the first fact matching (subject, relation).  Requires
        # ``subject`` and ``relation``.  Returns whether a fact was
        # removed.
        if op == "REMOVE_FACT":
            try:
                from brains.personal.memory import knowledge_graph  # type: ignore
            except Exception:
                knowledge_graph = None  # type: ignore
            if knowledge_graph is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Knowledge graph not available")
            subject = str(payload.get("subject", "")).strip()
            relation = str(payload.get("relation", "")).strip()
            if not (subject and relation):
                return error_response(op, mid, "INVALID_REQUEST", "subject and relation are required")
            try:
                removed = knowledge_graph.remove_fact(subject, relation)
            except Exception:
                removed = False
            return success_response(op, mid, {"removed": bool(removed)})

        # --- Query all facts with a specific relation --------------------
        # Return a list of subject-object pairs for a given relation.
        # Requires ``relation`` field.  Accepts optional ``limit`` to
        # bound the number of results.  The result format is a list of
        # dicts {subject, object}.  If the relation does not exist,
        # returns an empty list.
        if op == "QUERY_RELATION":
            try:
                from brains.personal.memory import knowledge_graph  # type: ignore
            except Exception:
                knowledge_graph = None  # type: ignore
            if knowledge_graph is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Knowledge graph not available")
            rel = str(payload.get("relation", "")).strip()
            try:
                limit = int(payload.get("limit", 10))
            except Exception:
                limit = 10
            if not rel:
                return error_response(op, mid, "INVALID_REQUEST", "relation is required")
            if limit < 0:
                limit = 0
            try:
                grouped = knowledge_graph.group_by_relation(0)
                records = grouped.get(rel, [])
                results: List[Dict[str, str]] = []
                count = 0
                for fact in records:
                    if limit and count >= limit:
                        break
                    results.append({"subject": fact.get("subject"), "object": fact.get("object")})
                    count += 1
                return success_response(op, mid, {"results": results})
            except Exception as ex:
                return error_response(op, mid, "ERROR", str(ex))

        # --- Knowledge graph bulk import -----------------------------------
        # Import multiple fact triples into the knowledge graph.  The payload
        # must contain a ``facts`` field which is an iterable of triples.  Each
        # triple can be a dict with ``subject``, ``relation`` and ``object``
        # keys or a list/tuple of three values.  Returns the number of
        # imported records.
        if op == "IMPORT_FACTS":
            try:
                from brains.personal.memory import knowledge_graph  # type: ignore
            except Exception:
                knowledge_graph = None  # type: ignore
            if knowledge_graph is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Knowledge graph not available")
            facts = payload.get("facts")
            if facts is None:
                return error_response(op, mid, "INVALID_REQUEST", "facts list is required")
            try:
                imported = knowledge_graph.import_facts(facts)  # type: ignore
            except Exception:
                imported = 0
            return success_response(op, mid, {"imported": imported})

        # --- Knowledge graph export ----------------------------------------
        # Return all facts from the knowledge graph.  No arguments are
        # required.  Returns a list of fact dictionaries.
        if op == "EXPORT_FACTS":
            try:
                from brains.personal.memory import knowledge_graph  # type: ignore
            except Exception:
                knowledge_graph = None  # type: ignore
            if knowledge_graph is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Knowledge graph not available")
            try:
                facts = knowledge_graph.export_facts()  # type: ignore
            except Exception:
                facts = []
            return success_response(op, mid, {"facts": facts})

        # --- Extended KG operations (V2) ------------------------------------
        # Add a new fact (subject, relation, object).  This is an alias for
        # ADD_FACT in the original API.  Requires subject, relation and
        # object in the payload.  Returns {"added": True} on success.
        if op == "ADD_RELATION":
            try:
                from brains.personal.memory import knowledge_graph  # type: ignore
            except Exception:
                knowledge_graph = None  # type: ignore
            if knowledge_graph is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Knowledge graph not available")
            s = str(payload.get("subject", "")).strip()
            r = str(payload.get("relation", "")).strip()
            o = str(payload.get("object", "")).strip()
            if not (s and r and o):
                return error_response(op, mid, "INVALID_REQUEST", "subject, relation and object are required")
            try:
                knowledge_graph.add_fact(s, r, o)  # type: ignore[attr-defined]
            except Exception:
                return error_response(op, mid, "ERROR", "failed to add relation")
            return success_response(op, mid, {"added": True})

        # Remove a fact by subject and relation.  Returns {"removed": bool}.
        if op == "REMOVE_RELATION":
            try:
                from brains.personal.memory import knowledge_graph  # type: ignore
            except Exception:
                knowledge_graph = None  # type: ignore
            if knowledge_graph is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Knowledge graph not available")
            s = str(payload.get("subject", "")).strip()
            r = str(payload.get("relation", "")).strip()
            if not (s and r):
                return error_response(op, mid, "INVALID_REQUEST", "subject and relation are required")
            try:
                removed = knowledge_graph.remove_fact(s, r)  # type: ignore[attr-defined]
            except Exception:
                removed = False
            return success_response(op, mid, {"removed": bool(removed)})

        # List stored inference rules.
        if op == "LIST_RULES":
            try:
                from brains.personal.memory import knowledge_graph  # type: ignore
            except Exception:
                knowledge_graph = None  # type: ignore
            if knowledge_graph is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Knowledge graph not available")
            try:
                rules = knowledge_graph.list_rules()  # type: ignore[attr-defined]
            except Exception:
                rules = []
            return success_response(op, mid, {"rules": rules})

        # Add an inference rule.  The payload must include a two-element
        # 'pattern' list and a 'consequence' string.  Returns {"added": bool}.
        if op == "ADD_RULE":
            try:
                from brains.personal.memory import knowledge_graph  # type: ignore
            except Exception:
                knowledge_graph = None  # type: ignore
            if knowledge_graph is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Knowledge graph not available")
            pat = payload.get("pattern")
            cons = payload.get("consequence")
            if not isinstance(pat, list) or len(pat) != 2 or not isinstance(cons, str):
                return error_response(op, mid, "INVALID_REQUEST", "pattern must be a list of two relations and consequence a relation")
            try:
                added_rule = knowledge_graph.add_rule(pat, cons)  # type: ignore[attr-defined]
            except Exception:
                added_rule = False
            return success_response(op, mid, {"added": bool(added_rule)})

        # Run inference to generate implied facts.  Accepts optional
        # 'limit' (default 10) controlling maximum results.  The
        # returned list contains fact dicts but does not persist them.
        if op == "RUN_INFERENCE":
            try:
                from brains.personal.memory import knowledge_graph  # type: ignore
            except Exception:
                knowledge_graph = None  # type: ignore
            if knowledge_graph is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Knowledge graph not available")
            try:
                limit = int(payload.get("limit", 10))
            except Exception:
                limit = 10
            if limit <= 0:
                limit = 10
            try:
                inferred = knowledge_graph.run_inference(limit)  # type: ignore[attr-defined]
            except Exception:
                inferred = []
            return success_response(op, mid, {"inferred": inferred})

        # Export all facts (v2).  Equivalent to EXPORT_FACTS but named
        # explicitly for the version 2 API.  Returns {"facts": [...]}.
        if op == "EXPORT_KG_V2":
            try:
                from brains.personal.memory import knowledge_graph  # type: ignore
            except Exception:
                knowledge_graph = None  # type: ignore
            if knowledge_graph is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Knowledge graph not available")
            try:
                items = knowledge_graph.export_facts()  # type: ignore[attr-defined]
            except Exception:
                items = []
            return success_response(op, mid, {"facts": items})

        # Import a batch of facts (v2).  Payload must include 'facts'
        # as a list of triples or dicts.  Returns {"added": count}.
        if op == "IMPORT_KG_V2":
            try:
                from brains.personal.memory import knowledge_graph  # type: ignore
            except Exception:
                knowledge_graph = None  # type: ignore
            if knowledge_graph is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Knowledge graph not available")
            facts = payload.get("facts")
            if not isinstance(facts, (list, tuple)):
                return error_response(op, mid, "INVALID_REQUEST", "facts must be a list of triples or dicts")
            try:
                added_count = knowledge_graph.import_facts(facts)  # type: ignore[attr-defined]
            except Exception:
                added_count = 0
            return success_response(op, mid, {"added": int(added_count)})

        # --- Synonym search ----------------------------------------------
        # Search the synonym mapping for entries containing the query.
        # Returns a list of {"term": original, "canonical": canonical}
        # pairs.  Case‑insensitive substring match is applied to both
        # the original term and the canonical target.  The number of
        # results is limited by `limit`.
        if op == "SEARCH_SYNONYMS":
            q = str(payload.get("query", "")).strip().lower()
            try:
                limit = int(payload.get("limit", 10))
            except Exception:
                limit = 10
            if not q:
                return error_response(op, mid, "INVALID_REQUEST", "query is required")
            try:
                from brains.personal.memory import synonyms  # type: ignore
            except Exception:
                synonyms = None  # type: ignore
            if synonyms is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Synonym mapping not available")
            matches: List[Dict[str, str]] = []
            try:
                mapping = synonyms.get_mapping()
                q_lower = q.lower()
                for term, canonical in mapping.items():
                    if len(matches) >= max(1, limit):
                        break
                    try:
                        term_l = str(term).lower()
                        canon_l = str(canonical).lower()
                    except Exception:
                        continue
                    if (q_lower in term_l) or (q_lower in canon_l):
                        matches.append({"term": term, "canonical": canonical})
                return success_response(op, mid, {"matches": matches})
            except Exception as ex:
                return error_response(op, mid, "ERROR", str(ex))

        # --- Synonym import and export ----------------------------------
        # Import multiple synonym mappings.  The payload must contain
        # a ``mapping`` field which is either a dictionary of
        # synonym→canonical pairs or an iterable of (synonym, canonical)
        # pairs.  Returns the number of imported entries.  If the
        # synonym helper is unavailable, returns UNSUPPORTED_OP.
        if op == "IMPORT_SYNONYMS":
            if synonyms is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Synonym mapping not available")
            mapping_data = payload.get("mapping")
            if mapping_data is None:
                return error_response(op, mid, "INVALID_REQUEST", "mapping is required")
            try:
                count = synonyms.import_synonyms(mapping_data)  # type: ignore[attr-defined]
            except Exception:
                count = 0
            return success_response(op, mid, {"imported": count})

        # Export the entire synonym mapping.  Returns a dict of
        # synonym→canonical pairs.  If the synonym helper is unavailable
        # return UNSUPPORTED_OP.
        if op == "EXPORT_SYNONYMS":
            if synonyms is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Synonym mapping not available")
            try:
                exported = synonyms.export_synonyms()  # type: ignore[attr-defined]
            except Exception:
                exported = {}
            return success_response(op, mid, {"synonyms": exported})

        # --- Canonical QA memory search ----------------------------------
        # Search the QA memory for entries that match the canonical form
        # of a query.  This operation first canonicalises the query
        # using the synonym mapping and then searches questions and
        # answers for either the original query or its canonical form.
        # A limit bounds the number of results.  This helper improves
        # recall when users phrase queries using synonyms or epithets.
        if op == "SEARCH_QA_CANONICAL":
            query_raw = str(payload.get("query", "")).strip()
            try:
                limit = int(payload.get("limit", 10))
            except Exception:
                limit = 10
            if not query_raw:
                return error_response(op, mid, "INVALID_REQUEST", "query is required")
            try:
                from brains.personal.memory import synonyms as _syn_mod  # type: ignore
            except Exception:
                _syn_mod = None  # type: ignore
            # Canonicalise the query if possible
            try:
                query_lower = query_raw.lower()
            except Exception:
                query_lower = query_raw
            canonical = None
            if _syn_mod is not None:
                try:
                    canonical = _syn_mod.get_canonical(query_raw)
                except Exception:
                    canonical = None
            if canonical:
                canonical_lower = canonical.lower()
            else:
                canonical_lower = None
            # Now search the QA memory for either form
            results: List[Dict[str, Any]] = []
            try:
                qa_path = MAVEN_ROOT / "reports" / "qa_memory.jsonl"
                if qa_path.exists():
                    with qa_path.open("r", encoding="utf-8") as fh:
                        for line in fh:
                            if len(results) >= max(1, limit):
                                break
                            try:
                                rec = json.loads(line)
                            except Exception:
                                continue
                            if not isinstance(rec, dict):
                                continue
                            q_text = str(rec.get("question", "")).lower()
                            a_text = str(rec.get("answer", "")).lower()
                            if query_lower in q_text or query_lower in a_text:
                                results.append({"question": rec.get("question"), "answer": rec.get("answer"), "ts": rec.get("timestamp")})
                                continue
                            if canonical_lower and (canonical_lower in q_text or canonical_lower in a_text):
                                results.append({"question": rec.get("question"), "answer": rec.get("answer"), "ts": rec.get("timestamp")})
                                continue
                return success_response(op, mid, {"matches": results})
            except Exception as ex:
                return error_response(op, mid, "ERROR", str(ex))

        # --- User mood operations ---------------------------------------
        # Retrieve the current user mood as a float in [-1, 1].  A
        # positive value indicates positive mood, negative indicates
        # negative mood.  The mood decays toward neutral over time.
        if op == "GET_MOOD":
            try:
                from brains.personal.memory import user_mood  # type: ignore[attr-defined]
            except Exception:
                user_mood = None  # type: ignore
            if user_mood is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "User mood not available")
            try:
                mood_val = user_mood.get_mood()  # type: ignore[attr-defined]
            except Exception:
                mood_val = 0.0
            return success_response(op, mid, {"mood": float(mood_val)})

        # Update the user mood by applying a valence adjustment.  The
        # payload may provide ``value`` (float) which is clamped to
        # [-1, 1].  If omitted, a default zero adjustment is applied.
        if op == "UPDATE_MOOD":
            try:
                from brains.personal.memory import user_mood  # type: ignore[attr-defined]
            except Exception:
                user_mood = None  # type: ignore
            if user_mood is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "User mood not available")
            try:
                val = float(payload.get("value", 0.0))
            except Exception:
                val = 0.0
            try:
                user_mood.update(val)  # type: ignore[attr-defined]
                return success_response(op, mid, {"updated": True})
            except Exception:
                return error_response(op, mid, "ERROR", "failed to update mood")

        # Reset the user mood to neutral (0.0) by deleting the stored
        # mood file.  Returns true when reset succeeds.
        if op == "RESET_MOOD":
            try:
                from brains.personal.memory import user_mood  # type: ignore[attr-defined]
            except Exception:
                user_mood = None  # type: ignore
            if user_mood is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "User mood not available")
            try:
                user_mood.reset()  # type: ignore[attr-defined]
                return success_response(op, mid, {"reset": True})
            except Exception:
                return error_response(op, mid, "ERROR", "failed to reset mood")

        # --- Safety rule operations ---------------------------------------
        # Return the list of safety rule patterns.  These are simple
        # substrings that the reasoning brain will match against user
        # queries to catch obviously false or harmful statements.  If
        # the safety rules module is unavailable, returns UNSUPPORTED_OP.
        if op == "LIST_SAFETY_RULES":
            try:
                from brains.personal.memory import safety_rules  # type: ignore[attr-defined]
            except Exception:
                safety_rules = None  # type: ignore
            if safety_rules is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Safety rules not available")
            try:
                rules = safety_rules.get_rules()  # type: ignore[attr-defined]
            except Exception:
                rules = []
            return success_response(op, mid, {"rules": rules})

        # Add a new safety rule pattern.  Requires a 'rule' in the payload.
        if op == "ADD_SAFETY_RULE":
            try:
                from brains.personal.memory import safety_rules  # type: ignore[attr-defined]
            except Exception:
                safety_rules = None  # type: ignore
            if safety_rules is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Safety rules not available")
            rule_str = str(payload.get("rule", "")).strip()
            if not rule_str:
                return error_response(op, mid, "INVALID_REQUEST", "rule is required")
            try:
                added = safety_rules.add_rule(rule_str)  # type: ignore[attr-defined]
            except Exception:
                added = False
            return success_response(op, mid, {"added": bool(added)})

        # Remove all safety rules, resetting to empty.  Returns {"cleared": True}
        if op == "RESET_SAFETY_RULES":
            try:
                from brains.personal.memory import safety_rules  # type: ignore[attr-defined]
            except Exception:
                safety_rules = None  # type: ignore
            if safety_rules is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Safety rules not available")
            try:
                ok = safety_rules.clear_rules()  # type: ignore[attr-defined]
            except Exception:
                ok = False
            return success_response(op, mid, {"cleared": bool(ok)})
        # --- QA memory summarisation -------------------------------------
        # Summarise the QA memory by grouping entries by their domain key
        # (the first two words of the question).  For each domain the
        # operation returns the number of stored Q/A pairs, the most
        # recent answer and a list of unique answers.  A `limit` parameter
        # controls how many domains are returned.  This summary helps
        # developers gauge memory coverage and recall patterns.
        if op == "SUMMARIZE_QA":
            try:
                limit = int(payload.get("limit", 10))
            except Exception:
                limit = 10
            if limit <= 0:
                limit = 10
            qa_path = MAVEN_ROOT / "reports" / "qa_memory.jsonl"
            summaries: List[Dict[str, Any]] = []
            try:
                if qa_path.exists():
                    domain_map: Dict[str, Dict[str, Any]] = {}
                    import json as _json
                    with qa_path.open("r", encoding="utf-8") as fh:
                        for line in fh:
                            try:
                                rec = _json.loads(line)
                            except Exception:
                                continue
                            if not isinstance(rec, dict):
                                continue
                            q = str(rec.get("question", "")).strip()
                            a = str(rec.get("answer", "")).strip()
                            ts = rec.get("timestamp", 0)
                            # Compute domain key: first two words lower‑cased
                            words = q.lower().split()
                            domain_key = " ".join(words[:2]) if words else ""
                            if not domain_key:
                                domain_key = ""
                            info = domain_map.get(domain_key)
                            if info is None:
                                info = {"domain": domain_key, "count": 0, "answers": [], "last_ts": 0, "last_answer": ""}
                                domain_map[domain_key] = info
                            info["count"] += 1
                            # Track unique answers (case‑insensitive)
                            if a:
                                if a.lower() not in [x.lower() for x in info["answers"]]:
                                    info["answers"].append(a)
                            # Update most recent answer based on timestamp ordering
                            try:
                                cur_ts = float(ts)
                            except Exception:
                                cur_ts = 0.0
                            if cur_ts >= info.get("last_ts", 0.0):
                                info["last_ts"] = cur_ts
                                info["last_answer"] = a
                    # Convert domain_map to sorted list
                    items = list(domain_map.values())
                    # Sort by count descending
                    items.sort(key=lambda x: x.get("count", 0), reverse=True)
                    for entry in items[:limit]:
                        # For readability, include up to 5 unique answers
                        uniq = entry.get("answers", [])
                        entry["unique_answers"] = uniq[:5]
                        # Remove internal fields
                        entry.pop("answers", None)
                        entry.pop("last_ts", None)
                        summaries.append(entry)
                return success_response(op, mid, {"summary": summaries})
            except Exception as ex:
                return error_response(op, mid, "ERROR", str(ex))

        # --- Goal summary ------------------------------------------------
        # Provide an overview of goals: total, active, completed and counts
        # by category (prefixes like AUTO_REPAIR, DELEGATED_TO, etc.).
        if op == "GOAL_SUMMARY":
            try:
                from brains.personal.memory import goal_memory  # type: ignore
            except Exception:
                goal_memory = None  # type: ignore
            if goal_memory is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Goal memory not available")
            try:
                all_goals = goal_memory.get_goals(active_only=False)
                total = len(all_goals)
                active = [g for g in all_goals if not g.get("completed", False)]
                completed = total - len(active)
                # Count by category: use prefix before ':' in description or title
                category_counts: Dict[str, int] = {}
                for g in all_goals:
                    # Determine category from description prefix
                    desc = str(g.get("description", "") or g.get("title", ""))
                    cat = ""
                    if desc:
                        # if description contains a prefix pattern e.g. 'AUTO_REPAIR', 'DELEGATED_TO:42'
                        # separate by ':' and take the first part
                        parts = desc.split(":", 1)
                        cat = parts[0].strip().upper()
                    if not cat:
                        cat = "GENERAL"
                    category_counts[cat] = category_counts.get(cat, 0) + 1
                summary = {
                    "total": total,
                    "active": len(active),
                    "completed": completed,
                    "categories": category_counts
                }
                return success_response(op, mid, {"summary": summary, "goals": active})
            except Exception as ex:
                return error_response(op, mid, "ERROR", str(ex))

        # --- Domain statistics and classification ------------------------
        # Provide a high‑level view of domain performance.  This
        # operation returns success/failure counts, total attempts,
        # computed adjustment and a coarse classification for each
        # domain.  Domains are categorised as "expert" (≥80 % success),
        # "intermediate" (60–79 % success) or "novice" (<60 % success).
        # An optional `limit` bounds the number of entries returned.
        # Domains are sorted by total attempts then by success ratio.
        if op == "DOMAIN_STATS":
            try:
                from brains.personal.memory import meta_confidence  # type: ignore
            except Exception:
                meta_confidence = None  # type: ignore
            if meta_confidence is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "Meta confidence not available")
            try:
                limit = int(payload.get("limit", 10))
            except Exception:
                limit = 10
            if limit <= 0:
                limit = 10
            try:
                stats = meta_confidence.get_stats(1000)
            except Exception:
                stats = []
            results: List[Dict[str, Any]] = []
            for rec in stats:
                try:
                    succ = float(rec.get("success", 0))
                except Exception:
                    succ = 0.0
                try:
                    fail = float(rec.get("failure", 0))
                except Exception:
                    fail = 0.0
                total = succ + fail
                ratio: float
                if total > 0.0:
                    ratio = succ / total
                else:
                    ratio = 0.0
                if ratio >= 0.8:
                    cls = "expert"
                elif ratio >= 0.6:
                    cls = "intermediate"
                else:
                    cls = "novice"
                results.append({
                    "domain": rec.get("domain"),
                    "success": int(succ),
                    "failure": int(fail),
                    "total": int(total),
                    "adjustment": rec.get("adjustment"),
                    "ratio": round(ratio, 4),
                    "classification": cls,
                })
            results.sort(key=lambda r: (r.get("total", 0), r.get("ratio", 0)), reverse=True)
            return success_response(op, mid, {"domains": results[:max(1, limit)]})

        # --- User knowledge operations ----------------------------------
        # These calls expose the per-domain familiarity counts that Maven
        # tracks for each user.  The USER_KNOWLEDGE_STATS operation
        # returns a list of domains along with decayed counts and a
        # familiarity level (expert/familiar/novice).  RESET_USER_KNOWLEDGE
        # clears the user knowledge store entirely, erasing all familiarity
        # data.  Both operations live in the personal brain and are
        # auxiliary helpers; they do not affect the core pipeline stages.
        if op == "USER_KNOWLEDGE_STATS":
            try:
                from brains.personal.memory import user_knowledge  # type: ignore
            except Exception:
                user_knowledge = None  # type: ignore
            if user_knowledge is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "User knowledge tracking not available")
            try:
                limit = int(payload.get("limit", 10))
            except Exception:
                limit = 10
            if limit <= 0:
                limit = 10
            try:
                items = user_knowledge.get_stats(limit)
            except Exception:
                items = []
            return success_response(op, mid, {"domains": items})

        if op == "RESET_USER_KNOWLEDGE":
            try:
                from brains.personal.memory import user_knowledge  # type: ignore
            except Exception:
                user_knowledge = None  # type: ignore
            if user_knowledge is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "User knowledge tracking not available")
            try:
                # Clear the user knowledge file by saving an empty dict.  This
                # operation resets all familiarity counts and timestamps.
                user_knowledge._save({})  # type: ignore  # pylint: disable=protected-access
                return success_response(op, mid, {"reset": True})
            except Exception:
                return error_response(op, mid, "ERROR", "failed to reset user knowledge")

        # --- Introspection / Diagnostics -----------------------------------
        # Provide a summary of Maven's internal state.  The INTROSPECT
        # operation returns counts of various persistent memory structures
        # (QA memory entries, knowledge graph facts, synonyms, profile
        # attributes and active goals) to help developers understand the
        # agent's footprint.  This operation aggregates data from
        # multiple modules and handles any errors gracefully.
        if op == "INTROSPECT":
            stats: Dict[str, Any] = {}
            # Count QA memory entries
            try:
                qa_path = MAVEN_ROOT / "reports" / "qa_memory.jsonl"
                if qa_path.exists():
                    with qa_path.open("r", encoding="utf-8") as fh:
                        stats["qa_entries"] = sum(1 for _ in fh)
                else:
                    stats["qa_entries"] = 0
            except Exception:
                stats["qa_entries"] = 0
            # Count knowledge graph facts
            try:
                from brains.personal.memory import knowledge_graph  # type: ignore
                items = knowledge_graph.list_facts(0) if knowledge_graph else []
                stats["facts_count"] = len(items)
            except Exception:
                stats["facts_count"] = 0
            # Count synonym mappings
            try:
                from brains.personal.memory import synonyms  # type: ignore
                mapping = synonyms.get_mapping() if synonyms else {}
                stats["synonyms_count"] = len(mapping)
            except Exception:
                stats["synonyms_count"] = 0
            # Count user profile attributes
            try:
                from brains.personal.memory import user_profile  # type: ignore
                profile = user_profile.get_profile() if user_profile else {}
                stats["profile_attributes"] = len(profile)
            except Exception:
                stats["profile_attributes"] = 0
            # Count active goals
            try:
                from brains.personal.memory import goal_memory  # type: ignore
                if goal_memory:
                    active = goal_memory.get_goals(active_only=True)
                    stats["active_goals"] = len(active)
                else:
                    stats["active_goals"] = 0
            except Exception:
                stats["active_goals"] = 0
            # Count meta confidence domains
            try:
                from brains.personal.memory import meta_confidence  # type: ignore
                if meta_confidence:
                    domains = meta_confidence.get_stats(1000)
                    stats["domains_tracked"] = len(domains)
                else:
                    stats["domains_tracked"] = 0
            except Exception:
                stats["domains_tracked"] = 0
            # Count topic statistics entries
            try:
                from brains.personal.memory import topic_stats  # type: ignore
                if topic_stats:
                    # get_stats returns top-N; to count all topics we can inspect its internal file
                    stats_path = MAVEN_ROOT / "reports" / "topic_stats.json"
                    if stats_path.exists():
                        with stats_path.open("r", encoding="utf-8") as fh:
                            data = json.load(fh) or {}
                            stats["topics_tracked"] = len(data)
                    else:
                        stats["topics_tracked"] = 0
                else:
                    stats["topics_tracked"] = 0
            except Exception:
                stats["topics_tracked"] = 0
            return success_response(op, mid, {"stats": stats})

        # --- User profile operations --------------------------------------
        # Maintain a simple user profile of preferences or attributes.  This
        # allows Maven to store and recall user‑specific details for more
        # personalised interactions.  The profile is stored in
        # reports/user_profile.json.  Keys are lower‑cased.
        try:
            from brains.personal.memory import user_profile  # type: ignore
        except Exception:
            user_profile = None  # type: ignore

        if op == "UPDATE_PROFILE":
            # Update a single profile attribute.  Requires `key` and `value`.
            if user_profile is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "User profile not available")
            key = str(payload.get("key", "")).strip()
            value = str(payload.get("value", "")).strip()
            if not (key and value):
                return error_response(op, mid, "INVALID_REQUEST", "key and value are required")
            try:
                user_profile.update_profile(key, value)
            except Exception:
                pass
            return success_response(op, mid, {"updated": True})

        if op == "GET_PROFILE":
            if user_profile is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "User profile not available")
            try:
                prof = user_profile.get_profile()
            except Exception:
                prof = {}
            return success_response(op, mid, {"profile": prof})

        if op == "GET_ATTRIBUTE":
            if user_profile is None:
                return error_response(op, mid, "UNSUPPORTED_OP", "User profile not available")
            key = str(payload.get("key", "")).strip()
            if not key:
                return error_response(op, mid, "INVALID_REQUEST", "key is required")
            try:
                val = user_profile.get_attribute(key)
            except Exception:
                val = None
            return success_response(op, mid, {"value": val})

        if op == "EXPORT":
            filter_tags = payload.get("filter_tags")
            return success_response(op, mid, {"items": _export(filter_tags)})
        return error_response(op, mid, "UNSUPPORTED_OP", f"Unknown operation: {op}")
    except Exception as e:
        return error_response(op, mid, "EXCEPTION", str(e))

# Ensure the personal brain exposes a `handle` entry point
try:
    handle = service_api  # type: ignore[assignment]
    service_api = handle  # type: ignore[assignment]
except Exception:
    pass
