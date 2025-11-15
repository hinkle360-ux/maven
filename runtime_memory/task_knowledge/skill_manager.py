
from __future__ import annotations
import json
from typing import Dict, Any, List
from pathlib import Path

# Skill database path
SKILLS_FILE = Path(__file__).parent / "skills.jsonl"

# Skill ID counter
_SKILL_ID_COUNTER: int = 0

def _next_skill_id() -> int:
    """Generate next skill ID deterministically."""
    global _SKILL_ID_COUNTER
    _SKILL_ID_COUNTER += 1
    return _SKILL_ID_COUNTER

def _load_skills() -> List[Dict[str, Any]]:
    """Load all skills from the skills file."""
    if not SKILLS_FILE.exists():
        return []

    skills = []
    try:
        with open(SKILLS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if not line or line.startswith("#"):
                    continue
                try:
                    skill = json.loads(line)
                    skills.append(skill)
                    # Update counter to max
                    sid = skill.get("skill_id", 0)
                    if isinstance(sid, int):
                        global _SKILL_ID_COUNTER
                        _SKILL_ID_COUNTER = max(_SKILL_ID_COUNTER, sid)
                except Exception:
                    continue
    except Exception:
        return []

    return skills

def _save_skill(skill: Dict[str, Any]) -> None:
    """Append a skill to the skills file."""
    try:
        with open(SKILLS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(skill) + "\n")
    except Exception:
        pass

def detect_skill_pattern(query_history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Detect skill patterns from query history.

    A skill is recognized when:
    - Similar question type repeats ≥ 3 times
    - Answers follow the same plan structure

    Args:
        query_history: List of query records with intent, plan, answer structure

    Returns:
        List of detected skills.
    """
    if not query_history or len(query_history) < 3:
        return []

    detected_skills = []

    # Track query patterns by intent
    intent_groups: Dict[str, List[Dict]] = {}

    for query in query_history:
        if not isinstance(query, dict):
            continue

        intent = str(query.get("intent", "")).upper()
        query_text = str(query.get("query", "")).lower()

        # Categorize query types
        query_type = ""
        if "why" in query_text:
            query_type = "WHY"
        elif "how does" in query_text or "how do" in query_text:
            query_type = "HOW"
        elif "explain" in query_text:
            query_type = "EXPLAIN"
        elif "compare" in query_text or "difference" in query_text:
            query_type = "COMPARE"

        if query_type:
            key = f"{intent}_{query_type}"
            if key not in intent_groups:
                intent_groups[key] = []
            intent_groups[key].append(query)

    # Detect skills from repeated patterns
    for pattern_key, queries in intent_groups.items():
        if len(queries) >= 3:
            # Extract common structure
            intent, qtype = pattern_key.split("_", 1)

            # Analyze plan structure
            plan_steps = []
            for q in queries:
                plan = q.get("plan", [])
                if isinstance(plan, list) and plan:
                    plan_steps.append(plan)

            # Find common steps
            common_steps = []
            if plan_steps:
                # Simple heuristic: steps that appear in ≥50% of plans
                step_frequency: Dict[str, int] = {}
                for plan in plan_steps:
                    for step in plan:
                        step_str = str(step)
                        step_frequency[step_str] = step_frequency.get(step_str, 0) + 1

                threshold = len(plan_steps) // 2
                common_steps = [step for step, count in step_frequency.items() if count >= threshold]

            # Create skill record
            skill = {
                "type": "SKILL",
                "skill_id": _next_skill_id(),
                "name": f"{qtype.lower()}_{intent.lower()}",
                "input_shape": f"{qtype} question",
                "output_shape": "multi-step explanation",
                "steps": common_steps if common_steps else ["retrieve facts", "compose answer"],
                "tier": "MID",
                "importance": min(1.0, 0.5 + (len(queries) * 0.1)),
                "usage_count": len(queries),
                "pattern_key": pattern_key
            }

            detected_skills.append(skill)

    return detected_skills

def consolidate_skill(thought_chain: List[str], plan: List[str], query_type: str, intent: str) -> Dict[str, Any]:
    """
    Consolidate a skill from a single execution.

    Args:
        thought_chain: List of reasoning steps
        plan: List of plan steps
        query_type: Type of query (WHY, HOW, EXPLAIN, etc.)
        intent: Intent classification

    Returns:
        Skill record.
    """
    skill = {
        "type": "SKILL",
        "skill_id": _next_skill_id(),
        "name": f"{query_type.lower()}_{intent.lower()}",
        "input_shape": f"{query_type} question about {intent.lower()}",
        "output_shape": "structured explanation",
        "steps": plan if plan else thought_chain[:5],  # Use plan or first 5 thought steps
        "tier": "MID",
        "importance": 0.7,
        "usage_count": 1
    }

    return skill

def match_skill(query: str, intent: str) -> Dict[str, Any] | None:
    """
    Match a query to an existing skill.

    Args:
        query: User query text
        intent: Intent classification

    Returns:
        Matching skill or None.
    """
    skills = _load_skills()

    query_lower = query.lower()

    # Determine query type
    query_type = ""
    if "why" in query_lower:
        query_type = "WHY"
    elif "how does" in query_lower or "how do" in query_lower:
        query_type = "HOW"
    elif "explain" in query_lower:
        query_type = "EXPLAIN"
    elif "compare" in query_lower or "difference" in query_lower:
        query_type = "COMPARE"

    if not query_type:
        return None

    # Match by pattern
    pattern_key = f"{intent.upper()}_{query_type}"

    for skill in skills:
        if skill.get("pattern_key") == pattern_key:
            return skill

        # Fallback: match by name
        expected_name = f"{query_type.lower()}_{intent.lower()}"
        if skill.get("name") == expected_name:
            return skill

    return None

def service_api(msg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Skill manager service API.

    Supported operations:
    - DETECT_SKILLS: Detect skills from query history
    - CONSOLIDATE_SKILL: Create skill from single execution
    - MATCH_SKILL: Match query to existing skill
    - QUERY_SKILLS: Query all skills
    """
    from api.utils import generate_mid, success_response, error_response  # type: ignore

    op = (msg or {}).get("op", " ").upper()
    mid = msg.get("mid") or generate_mid()
    payload = msg.get("payload") or {}

    if op == "HEALTH":
        skills = _load_skills()
        return success_response(op, mid, {
            "status": "operational",
            "skill_count": len(skills)
        })

    if op == "DETECT_SKILLS":
        query_history = payload.get("query_history", [])
        detected = detect_skill_pattern(query_history)

        # Save detected skills
        for skill in detected:
            _save_skill(skill)

        return success_response(op, mid, {
            "detected_skills": detected,
            "count": len(detected)
        })

    if op == "CONSOLIDATE_SKILL":
        thought_chain = payload.get("thought_chain", [])
        plan = payload.get("plan", [])
        query_type = payload.get("query_type", "")
        intent = payload.get("intent", "")

        if not query_type or not intent:
            return error_response(op, mid, "MISSING_PARAMS", "query_type and intent required")

        skill = consolidate_skill(thought_chain, plan, query_type, intent)
        _save_skill(skill)

        return success_response(op, mid, {"skill": skill})

    if op == "MATCH_SKILL":
        query = payload.get("query", "")
        intent = payload.get("intent", "")

        if not query or not intent:
            return error_response(op, mid, "MISSING_PARAMS", "query and intent required")

        skill = match_skill(query, intent)

        if skill:
            return success_response(op, mid, {"skill": skill, "matched": True})
        else:
            return success_response(op, mid, {"matched": False})

    if op == "QUERY_SKILLS":
        skills = _load_skills()
        return success_response(op, mid, {
            "skills": skills,
            "count": len(skills)
        })

    return error_response(op, mid, "UNSUPPORTED_OP", op)
