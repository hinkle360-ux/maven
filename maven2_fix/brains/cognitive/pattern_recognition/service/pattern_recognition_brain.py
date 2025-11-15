
from __future__ import annotations
import re
from typing import Dict, Any, List
from pathlib import Path

HERE = Path(__file__).resolve().parent
BRAIN_ROOT = HERE.parent

def _counts():
    """Return a mapping of record counts per memory tier, rotating first."""
    from api.memory import rotate_if_needed, ensure_dirs, count_lines  # type: ignore
    # Rotate memory to prevent overflow before computing counts
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

def _analyze(text: str) -> Dict[str, Any]:
    """
    Analyze a chunk of text and extract simple lexical and structural features.

    This primitive pattern recognition function was intentionally designed to keep
    the complexity of the "brain" minimal while still surfacing a handful of
    informative attributes about the input.  It now includes additional
    structural markers such as uppercase tokens, email addresses, and URLs in
    addition to the original digit, punctuation and repeating word checks.  A
    future version could incorporate more sophisticated statistical or
    linguistic analyses, but for now we deliberately favour simple heuristics
    that are easy to reason about and implement.

    Args:
        text: Raw user input string to inspect.

    Returns:
        A dictionary containing a `features` map with extracted booleans and
        counts, a `confidence` score for the extraction and a timestamp.
    """
    s = (text or "").strip()
    # Tokenize on alphanumerics and apostrophes; this preserves contractions
    words = [w for w in re.findall(r"[A-Za-z0-9']+", s)]
    repeats = sorted({w for w in words if words.count(w) > 1})
    # Core flags
    has_digit = any(c.isdigit() for c in s)
    has_punct = any(c in ".?!,;:" for c in s)
    # New structural markers
    # Uppercase words (heuristic: two or more uppercase letters)
    has_uppercase_word = any(w.isupper() and len(w) > 1 for w in words)
    # Simple email detection
    email_pattern = re.compile(r"\b[\w.-]+@[\w.-]+\.[A-Za-z]{2,}\b")
    has_email = bool(email_pattern.search(s))
    # Simple URL detection (http/https)
    url_pattern = re.compile(r"https?://\S+")
    has_url = bool(url_pattern.search(s))
    # Attempt to detect emojis by scanning for characters outside basic Latin
    # Unicode blocks.  Emojis live in ranges >0x1F600; we use a rough check
    # that any codepoint above 0x1F300 is likely an emoji or symbol.  This
    # avoids importing heavy external libraries.
    has_emoji = any(ord(ch) > 0x1F300 for ch in s)
    # Aggregate counts
    length = len(s)
    unique_words = len(set(words))
    avg_word_len = round(sum(len(w) for w in words) / len(words), 2) if words else 0.0
    shape = {
        "has_digit": has_digit,
        "has_punctuation": has_punct,
        "has_uppercase_word": has_uppercase_word,
        "has_email": has_email,
        "has_url": has_url,
        "has_emoji": has_emoji,
        "length": length,
        "word_count": len(words),
        "unique_words": unique_words,
        "avg_word_len": avg_word_len,
        "repeating_words": repeats[:5],
    }
    # Compute a learned bias based on recent successes to augment the output.
    from api.memory import compute_success_average, ensure_dirs, append_jsonl, rotate_if_needed  # type: ignore
    try:
        learned_bias = compute_success_average(BRAIN_ROOT)
    except Exception:
        learned_bias = 0.0
    out = {"features": shape, "confidence": 0.5, "learned_bias": learned_bias}
    # Log to memory with a placeholder success field for later marking.
    tiers = ensure_dirs(BRAIN_ROOT)
    try:
        append_jsonl(tiers["stm"], {"op": "ANALYZE", "input": s, "output": out, "success": None})
        append_jsonl(tiers["mtm"], {"op": "ANALYZE", "word_count": len(words)})
    except Exception:
        pass
    # Rotate records if memory exceeds configured thresholds
    try:
        rotate_if_needed(BRAIN_ROOT)
    except Exception:
        pass
    return out

def extract_patterns(records: List[Dict]) -> List[Dict]:
    """
    Extract deterministic patterns from a list of memory records.

    This is not clustering, not statistics, not ML.
    This is deterministic rule-based pattern induction.

    Extracts:
    - repeated user preferences
    - consistent relational structures
    - topic co-occurrence
    - repeated types of queries (intent frequencies)
    - domain-specific repeated explanations

    Args:
        records: List of memory records with content, tags, intent, etc.

    Returns:
        List of structured pattern records (not free text).
    """
    if not records or not isinstance(records, list):
        return []

    patterns = []

    # Track preferences (same pattern repeated)
    preference_map: Dict[str, List[Dict]] = {}
    intent_counter: Dict[str, int] = {}
    topic_map: Dict[str, int] = {}
    relation_types: Dict[str, int] = {}

    for rec in records:
        if not isinstance(rec, dict):
            continue

        content = str(rec.get("content", "")).lower().strip()
        tags = rec.get("tags", [])
        if isinstance(tags, str):
            tags = [tags]
        tags_set = {str(t).lower() for t in tags}
        intent = str(rec.get("intent", "")).upper()
        verdict = str(rec.get("verdict", "")).upper()

        # Pattern 1: Preference clustering
        if verdict == "PREFERENCE" or "preference" in tags_set:
            # Extract preference subject
            if "like" in content:
                parts = content.split("like")
                if len(parts) > 1:
                    subject = parts[1].strip().split()[0] if parts[1].strip().split() else ""
                    if subject:
                        if subject not in preference_map:
                            preference_map[subject] = []
                        preference_map[subject].append(rec)

        # Pattern 2: Intent frequency tracking
        if intent:
            intent_counter[intent] = intent_counter.get(intent, 0) + 1

        # Pattern 3: Topic co-occurrence
        for tag in tags_set:
            if tag and len(tag) > 2:
                topic_map[tag] = topic_map.get(tag, 0) + 1

        # Pattern 4: Relationship patterns
        if "relationship" in tags_set or verdict == "RELATIONSHIP":
            # Extract relation type (friend, family, etc.)
            for word in ["friend", "family", "colleague", "mentor"]:
                if word in content:
                    relation_types[word] = relation_types.get(word, 0) + 1

    # Generate pattern records for preferences (≥2 occurrences)
    for subject, recs in preference_map.items():
        if len(recs) >= 2:
            patterns.append({
                "pattern_type": "preference_cluster",
                "subject": subject,
                "occurrences": len(recs),
                "consistency": min(1.0, len(recs) / 10.0),  # Deterministic scoring
                "examples": [r.get("content", "") for r in recs[:3]]
            })

    # Generate pattern records for recurring intents (≥3 occurrences)
    for intent, count in intent_counter.items():
        if count >= 3:
            patterns.append({
                "pattern_type": "recurring_intent",
                "intent": intent,
                "frequency": count,
                "consistency": min(1.0, count / 20.0)
            })

    # Generate pattern records for domain focus (≥5 occurrences)
    for topic, count in topic_map.items():
        if count >= 5:
            patterns.append({
                "pattern_type": "domain_focus",
                "topic": topic,
                "frequency": count,
                "consistency": min(1.0, count / 30.0)
            })

    # Generate pattern records for relationship types
    for rel_type, count in relation_types.items():
        if count >= 2:
            patterns.append({
                "pattern_type": "relation_structure",
                "relation_type": rel_type,
                "frequency": count,
                "consistency": min(1.0, count / 5.0)
            })

    return patterns

def service_api(msg: Dict[str, Any]) -> Dict[str, Any]:
    from api.utils import generate_mid, success_response, error_response  # type: ignore
    op = (msg or {}).get("op"," ").upper()
    mid = msg.get("mid") or generate_mid()
    payload = msg.get("payload") or {}

    if op == "HEALTH":
        return success_response(op, mid, {"status": "operational", "memory_health": _counts()})
    if op == "ANALYZE":
        return success_response(op, mid, _analyze(str(payload.get("text",""))))
    if op == "EXTRACT_PATTERNS":
        records = payload.get("records", [])
        patterns = extract_patterns(records)
        return success_response(op, mid, {"patterns": patterns, "count": len(patterns)})
    return error_response(op, mid, "UNSUPPORTED_OP", op)

# Ensure the pattern_recognition brain exposes a `handle` entry point
try:
    handle = service_api  # type: ignore[assignment]
    service_api = handle  # type: ignore[assignment]
except Exception:
    pass
