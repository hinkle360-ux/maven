
from __future__ import annotations
import json, time, re
from pathlib import Path
from typing import Dict, Any

# Root directories
HERE = Path(__file__).resolve().parent
BRAIN_ROOT = HERE.parent

def _counts():
    """Return record counts for each memory tier."""
    from api.memory import ensure_dirs, count_lines  # type: ignore
    t = ensure_dirs(BRAIN_ROOT)
    return {"stm": count_lines(t["stm"]), "mtm": count_lines(t["mtm"]), "ltm": count_lines(t["ltm"]), "cold": count_lines(t["cold"])}

def _prefs_file() -> Path:
    """
    Determine the path to the preferences JSON file.  Preferences are stored
    in the STM tier to ensure they are lightweight and easy to rotate.
    """
    pref_dir = BRAIN_ROOT / "memory" / "stm"
    pref_dir.mkdir(parents=True, exist_ok=True)
    return pref_dir / "prefs.json"

def _load_prefs() -> Dict[str, Any]:
    """
    Load persisted affect preferences.  If the preferences file does not
    exist or cannot be parsed, return sensible defaults.
    """
    p = _prefs_file()
    if not p.exists():
        return {"tone_counts": {"neutral": 0, "calm": 0, "upbeat": 0, "urgent": 0}, "priority_adjust": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"tone_counts": {"neutral": 0, "calm": 0, "upbeat": 0, "urgent": 0}, "priority_adjust": {}}

def _save_prefs(prefs: Dict[str, Any]) -> None:
    """
    Persist affect preferences to disk.  Errors are swallowed silently to
    avoid interrupting pipeline execution.
    """
    try:
        pf = _prefs_file()
        pf.write_text(json.dumps(prefs, indent=2), encoding="utf-8")
    except Exception:
        pass

def _compute_affect(text: str) -> Dict[str, Any]:
    """
    Compute affect scores (arousal, valence) and derive a priority delta and suggested tone.
    The heuristics are intentionally simple: exclamation points and sentiment words drive
    arousal and valence.  Personal subject boosts nudge valence and priority delta.
    """
    t = (text or "")
    lower = t.lower()
    # Basic sentiment dictionaries
    negative_words = [
        "worried", "worry", "concern", "concerned", "afraid", "fear", "fearful",
        "hate", "angry", "mad", "sad", "terrible", "bad", "upset", "anxious",
        "stress", "stressed"
    ]
    positive_words = [
        "happy", "joy", "love", "good", "great", "awesome", "excited",
        "delightful", "excellent", "glad", "thankful", "positive", "optimistic"
    ]
    exclamations = t.count("!")
    # Count occurrences (not unique) to reflect intensity
    neg_count = 0
    pos_count = 0
    for w in negative_words:
        neg_count += lower.count(w)
    for w in positive_words:
        pos_count += lower.count(w)
    # Compute arousal: exclamations and total sentiment words raise arousal
    arousal = min(1.0, 0.2 * exclamations + 0.1 * (neg_count + pos_count))
    # Compute valence: positive minus negative
    valence = 0.0
    if pos_count > 0:
        valence += min(1.0, pos_count * 0.4)
    if neg_count > 0:
        valence -= min(1.0, neg_count * 0.4)
    # Apply personal subject boost
    boost = 0.0
    try:
        import importlib
        per_brain = importlib.import_module("brains.personal.service.personal_brain")
        res = per_brain.service_api({"op": "SCORE_BOOST", "payload": {"subject": text}})
        boost = float((res.get("payload") or {}).get("boost", 0.0))
    except Exception:
        boost = 0.0
    valence = max(-1.0, min(1.0, valence + boost))
    # Base priority delta: product of valence and arousal scaled down
    priority_delta = valence * arousal * 0.2
    # Load stored preferences to adjust priority
    prefs = _load_prefs()
    priority_adjust_total = 0.0
    try:
        for adj in prefs.get("priority_adjust", {}).values():
            priority_adjust_total += float(adj)
    except Exception:
        priority_adjust_total = 0.0
    priority_delta = max(-0.2, min(0.2, priority_delta + priority_adjust_total))
    # Derive a suggested tone from heuristics
    def contains_any(substrs):
        return any(s in lower for s in substrs)
    if exclamations >= 2 or contains_any(["urgent", "asap", "immediately"]):
        tone = "urgent"
    elif arousal >= 0.6:
        tone = "urgent"
    elif arousal >= 0.3 and valence < 0:
        tone = "calm"
    elif arousal >= 0.3 and valence >= 0:
        tone = "upbeat"
    elif valence > 0:
        tone = "upbeat"
    elif valence < 0:
        tone = "calm"
    else:
        tone = "neutral"
    # Bias tone toward historically successful tones if one dominates
    counts = prefs.get("tone_counts", {})
    total_ct = sum(counts.values()) if counts else 0
    if total_ct >= 5:  # Only consider when we have some history
        top_tone = max(counts, key=lambda k: counts[k])
        top_count = counts.get(top_tone, 0)
        if total_ct > 0 and (top_count / total_ct) >= 0.6:
            tone = top_tone
    return {
        "arousal": round(arousal, 3),
        "valence": round(valence, 3),
        "priority_delta": round(priority_delta, 3),
        "suggested_tone": tone
    }

def service_api(msg):
    """
    Central entry point for the affect priority brain.  Supports basic health
    reporting, affect scoring, and reinforcement learning based on run outcomes.
    """
    from api.utils import generate_mid, success_response, error_response  # type: ignore
    op = (msg or {}).get("op", " ").upper()
    mid = msg.get("mid") or generate_mid()
    payload = msg.get("payload") or {}
    # HEALTH operation
    if op == "HEALTH":
        return success_response(op, mid, {"status": "operational", "memory_health": _counts()})
    # SCORE operation: evaluate a text and return affect metrics
    if op == "SCORE":
        try:
            text = str(payload.get("text", ""))
        except Exception:
            text = ""
        metrics = _compute_affect(text)
        return success_response(op, mid, metrics)
    # LEARN_FROM_RUN operation: update preferences based on pipeline outcome
    if op == "LEARN_FROM_RUN":
        try:
            tone = str(payload.get("tone") or "").lower()
            decision = str(payload.get("decision") or "").upper()
            # Load and update preferences
            prefs = _load_prefs()
            # Update tone usage counts
            if tone:
                prefs.setdefault("tone_counts", {"neutral": 0, "calm": 0, "upbeat": 0, "urgent": 0})
                prefs["tone_counts"][tone] = prefs["tone_counts"].get(tone, 0) + 1
            # Update priority adjustments for each tone based on decision
            if tone:
                prefs.setdefault("priority_adjust", {})
                current_adj = float(prefs["priority_adjust"].get(tone, 0.0))
                # Reward allows with a small positive bias, penalize denies/quarantines with negative bias
                delta = 0.01 if decision == "ALLOW" else -0.01
                new_adj = max(-0.2, min(0.2, current_adj + delta))
                prefs["priority_adjust"][tone] = round(new_adj, 3)
            _save_prefs(prefs)
            return success_response(op, mid, {"logged": True})
        except Exception as e:
            return error_response(op, mid, "ERROR", f"Failed to learn: {e}")
    # Unsupported operations
    return error_response(op, mid, "UNSUPPORTED_OP", op)

# Ensure the affect_priority brain exposes a `handle` entry point
try:
    handle = service_api  # type: ignore[assignment]
    service_api = handle  # type: ignore[assignment]
except Exception:
    pass
