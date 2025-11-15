
from __future__ import annotations
import json
from typing import Dict, Any, List
from pathlib import Path

HERE = Path(__file__).resolve().parent
BRAIN_ROOT = HERE.parent
CONCEPTS_FILE = BRAIN_ROOT / "memory" / "concepts.jsonl"

# Ensure memory directory exists
CONCEPTS_FILE.parent.mkdir(parents=True, exist_ok=True)

# Concept ID counter (deterministic, monotonic)
_CONCEPT_ID_COUNTER: int = 0

def _next_concept_id() -> int:
    """Generate next concept ID deterministically."""
    global _CONCEPT_ID_COUNTER
    _CONCEPT_ID_COUNTER += 1
    return _CONCEPT_ID_COUNTER

def _load_concepts() -> List[Dict[str, Any]]:
    """Load all concepts from the concepts file."""
    if not CONCEPTS_FILE.exists():
        return []

    concepts = []
    try:
        with open(CONCEPTS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    concept = json.loads(line.strip())
                    concepts.append(concept)
                    # Update counter to max
                    cid = concept.get("concept_id", 0)
                    if isinstance(cid, int):
                        global _CONCEPT_ID_COUNTER
                        _CONCEPT_ID_COUNTER = max(_CONCEPT_ID_COUNTER, cid)
                except Exception:
                    continue
    except Exception:
        return []

    return concepts

def _save_concept(concept: Dict[str, Any]) -> None:
    """Append a concept to the concepts file."""
    try:
        with open(CONCEPTS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(concept) + "\n")
    except Exception:
        pass

def _create_concept(pattern: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a concept from a pattern.

    Args:
        pattern: Pattern dict with pattern_type, subject/intent/topic, etc.

    Returns:
        Concept record with structured attributes.
    """
    pattern_type = pattern.get("pattern_type", "")

    # Determine concept name and attributes based on pattern type
    if pattern_type == "preference_cluster":
        name = f"preference_{pattern.get('subject', 'unknown')}"
        attributes = [f"likes_{pattern.get('subject', 'unknown')}"]
        importance = 0.8 + (pattern.get("consistency", 0.0) * 0.2)
    elif pattern_type == "recurring_intent":
        name = f"intent_pattern_{pattern.get('intent', 'unknown').lower()}"
        attributes = [f"frequent_{pattern.get('intent', 'unknown').lower()}_queries"]
        importance = 0.7 + (pattern.get("consistency", 0.0) * 0.2)
    elif pattern_type == "domain_focus":
        name = f"domain_{pattern.get('topic', 'unknown')}"
        attributes = [f"focus_on_{pattern.get('topic', 'unknown')}"]
        importance = 0.75 + (pattern.get("consistency", 0.0) * 0.15)
    elif pattern_type == "relation_structure":
        name = f"relation_{pattern.get('relation_type', 'unknown')}"
        attributes = [f"has_{pattern.get('relation_type', 'unknown')}_relationships"]
        importance = 0.7 + (pattern.get("consistency", 0.0) * 0.2)
    else:
        name = f"concept_{pattern_type}"
        attributes = []
        importance = 0.6

    concept = {
        "concept_id": _next_concept_id(),
        "name": name,
        "attributes": attributes,
        "derived_from_pattern": pattern,
        "tier": "LONG",
        "importance": min(1.0, importance)
    }

    return concept

def _update_concept(concept_id: int, updates: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update an existing concept.

    Args:
        concept_id: ID of concept to update
        updates: Dict of fields to update

    Returns:
        Updated concept or error dict.
    """
    concepts = _load_concepts()

    for i, concept in enumerate(concepts):
        if concept.get("concept_id") == concept_id:
            # Apply updates
            for key, value in updates.items():
                if key != "concept_id":  # Don't allow ID changes
                    concept[key] = value

            # Rewrite entire file (simple implementation)
            try:
                with open(CONCEPTS_FILE, "w", encoding="utf-8") as f:
                    for c in concepts:
                        f.write(json.dumps(c) + "\n")
            except Exception:
                return {"error": "Failed to update concept file"}

            return concept

    return {"error": f"Concept {concept_id} not found"}

def _query_concepts(filters: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Query concepts by filters.

    Args:
        filters: Dict with optional keys: name, tier, min_importance

    Returns:
        List of matching concepts.
    """
    concepts = _load_concepts()
    results = []

    name_filter = filters.get("name", "")
    tier_filter = filters.get("tier", "")
    min_importance = filters.get("min_importance", 0.0)

    for concept in concepts:
        # Apply filters
        if name_filter and name_filter not in concept.get("name", ""):
            continue
        if tier_filter and concept.get("tier", "") != tier_filter:
            continue
        if concept.get("importance", 0.0) < min_importance:
            continue

        results.append(concept)

    return results

def service_api(msg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Abstraction brain service API.

    Supported operations:
    - HEALTH: Health check
    - CREATE_CONCEPT: Create concept from pattern
    - UPDATE_CONCEPT: Update existing concept
    - QUERY_CONCEPT: Query concepts by filters
    """
    from api.utils import generate_mid, success_response, error_response  # type: ignore

    op = (msg or {}).get("op", " ").upper()
    mid = msg.get("mid") or generate_mid()
    payload = msg.get("payload") or {}

    if op == "HEALTH":
        concepts = _load_concepts()
        return success_response(op, mid, {
            "status": "operational",
            "concept_count": len(concepts)
        })

    if op == "CREATE_CONCEPT":
        pattern = payload.get("pattern", {})
        if not pattern:
            return error_response(op, mid, "MISSING_PATTERN", "Pattern required")

        concept = _create_concept(pattern)
        _save_concept(concept)

        return success_response(op, mid, {"concept": concept})

    if op == "UPDATE_CONCEPT":
        concept_id = payload.get("concept_id")
        updates = payload.get("updates", {})

        if concept_id is None:
            return error_response(op, mid, "MISSING_ID", "Concept ID required")

        result = _update_concept(int(concept_id), updates)

        if "error" in result:
            return error_response(op, mid, "UPDATE_FAILED", result["error"])

        return success_response(op, mid, {"concept": result})

    if op == "QUERY_CONCEPT":
        filters = payload.get("filters", {})
        concepts = _query_concepts(filters)

        return success_response(op, mid, {
            "concepts": concepts,
            "count": len(concepts)
        })

    return error_response(op, mid, "UNSUPPORTED_OP", op)

# Ensure the abstraction brain exposes a `handle` entry point
try:
    handle = service_api  # type: ignore[assignment]
    service_api = handle  # type: ignore[assignment]
except Exception:
    pass
