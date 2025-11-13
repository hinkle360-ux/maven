"""
Correction Handler
==================

This module implements a mechanism for processing user feedback, both
positive and negative.  When the user indicates that the agent's previous
statement was correct or incorrect, the correction handler updates confidence
scores and reinforces or supersedes beliefs accordingly.

Integration points include:
- meta_confidence: Domain-level success tracking
- memory_librarian: Key-value confidence updates via BRAIN_MERGE
- working memory: Session-level Q&A storage with confidence scores

The module maintains a simple context of the last exchange to enable
feedback processing when users respond with "correct", "yes", "no", etc.
"""

from __future__ import annotations

from typing import Dict, Any, Optional

# Module-level storage for the last exchange to enable feedback processing
_LAST_EXCHANGE: Optional[Dict[str, Any]] = None


def set_last_exchange(question: str, answer: str, confidence: float = 0.4, domain: str = "") -> None:
    """Store the last question/answer exchange for feedback processing.

    Args:
        question: The user's question
        answer: Maven's answer
        confidence: The confidence score of the answer
        domain: The domain/topic extracted from the question (first 1-2 words)
    """
    global _LAST_EXCHANGE
    _LAST_EXCHANGE = {
        "question": question,
        "answer": answer,
        "confidence": confidence,
        "domain": domain,
    }


def get_last_exchange() -> Optional[Dict[str, Any]]:
    """Retrieve the last exchange for feedback processing."""
    global _LAST_EXCHANGE
    return _LAST_EXCHANGE


def is_positive_feedback(text: str) -> bool:
    """Detect whether the text is positive feedback.

    Recognizes affirmative responses like "correct", "yes", "right", etc.

    Args:
        text: The user's input text

    Returns:
        True if the text indicates positive feedback
    """
    try:
        q = str(text or "").strip().lower()
    except Exception:
        return False

    # Exact matches
    positive_exact = {
        "correct", "right", "yes", "good", "true", "exactly",
        "yep", "yeah", "yup", "sure", "indeed", "absolutely",
        "y", "ok", "okay", "agreed"
    }
    if q in positive_exact:
        return True

    # Phrase matches
    positive_phrases = [
        "that's correct", "that's right", "you're right", "you're correct",
        "yes correct", "correct on", "all correct", "yes that's",
        "that is correct", "that is right"
    ]
    return any(phrase in q for phrase in positive_phrases)


def is_negative_feedback(text: str) -> bool:
    """Detect whether the text is negative feedback.

    Recognizes corrections like "no", "incorrect", "wrong", etc.

    Args:
        text: The user's input text

    Returns:
        True if the text indicates negative feedback
    """
    try:
        q = str(text or "").strip().lower()
    except Exception:
        return False

    # Exact matches
    negative_exact = {"no", "incorrect", "wrong", "false", "nope", "n"}
    if q in negative_exact:
        return True

    # Phrase matches and starts with
    if q.startswith("no") or "incorrect" in q or "wrong" in q:
        return True

    return False


def is_correction(ctx: Dict[str, Any]) -> bool:
    """Detect whether the current query is a user correction.

    This checks for explicit patterns in the original query such
    as "no," or "incorrect".
    """
    try:
        q = str((ctx.get("original_query") or "")).strip().lower()
    except Exception:
        q = ""
    return is_negative_feedback(q)


def handle_positive_feedback(memory_librarian_api=None) -> str:
    """Process positive feedback by updating confidence scores.

    When the user confirms an answer is correct, this function:
    1. Updates meta_confidence for the domain (marks success)
    2. Calls BRAIN_MERGE to bump the Q&A confidence by +0.1
    3. Returns a confirmation message

    Args:
        memory_librarian_api: The memory librarian service_api function (optional)

    Returns:
        A response message for the user
    """
    global _LAST_EXCHANGE
    if _LAST_EXCHANGE is None:
        return "Noted."

    try:
        question = _LAST_EXCHANGE.get("question", "")
        answer = _LAST_EXCHANGE.get("answer", "")
        current_conf = _LAST_EXCHANGE.get("confidence", 0.4)
        domain = _LAST_EXCHANGE.get("domain", "")

        # Extract domain from question if not already set (first 1-2 words)
        if not domain and question:
            words = question.strip().split()
            domain = " ".join(words[:2]) if len(words) >= 2 else words[0] if words else ""

        # Update meta-confidence for the domain
        try:
            from brains.personal.memory import meta_confidence
            if domain:
                meta_confidence.update(domain, success=True)
        except Exception:
            pass

        # Update confidence in fast_cache (which pipeline checks on every query)
        new_conf = current_conf
        try:
            # Try to access the memory_librarian module to use its cache functions
            from brains.cognitive.memory_librarian.service import memory_librarian as ml_module
            # First try to boost existing cache entry
            boosted_conf = ml_module._boost_cache_confidence(question, boost_amount=0.15)
            if boosted_conf is not None:
                new_conf = boosted_conf
            else:
                # No cached entry exists, store a new one with boosted confidence
                new_conf = min(1.0, current_conf + 0.15)
                ml_module._store_fast_cache_entry(question, answer, new_conf)
        except Exception:
            # Fallback: just add 0.15 to current confidence locally
            new_conf = min(1.0, current_conf + 0.15)

        # Also update BRAIN_MERGE for persistent storage
        if memory_librarian_api is not None:
            try:
                q_key = question.strip().lower()
                memory_librarian_api({
                    "op": "BRAIN_MERGE",
                    "payload": {
                        "scope": "BRAIN",
                        "origin_brain": "qa_memory",
                        "key": q_key,
                        "value": answer,
                        "conf_delta": 0.15
                    }
                })
            except Exception:
                pass

        # Return confirmation with updated confidence
        return "Noted."

    except Exception:
        return "Noted."


def handle_negative_feedback(memory_librarian_api=None) -> str:
    """Process negative feedback by recording the failure.

    When the user indicates an answer is incorrect, this function:
    1. Updates meta_confidence for the domain (marks failure)
    2. Records the incorrect pattern for learning
    3. Returns an acknowledgment

    Args:
        memory_librarian_api: The memory librarian service_api function (optional)

    Returns:
        A response message for the user
    """
    global _LAST_EXCHANGE
    if _LAST_EXCHANGE is None:
        return "I see. I'll try to do better."

    try:
        question = _LAST_EXCHANGE.get("question", "")
        domain = _LAST_EXCHANGE.get("domain", "")

        # Extract domain from question if not already set
        if not domain and question:
            words = question.strip().split()
            domain = " ".join(words[:2]) if len(words) >= 2 else words[0] if words else ""

        # Update meta-confidence for the domain (mark as failure)
        try:
            from brains.personal.memory import meta_confidence
            if domain:
                meta_confidence.update(domain, success=False)
        except Exception:
            pass

        return "I see. I'll try to do better."

    except Exception:
        return "I see. I'll try to do better."


def find_contradicted_belief(ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Identify the belief contradicted by the correction.

    This placeholder simply returns None.  In a full implementation it
    would search memory for the belief previously used to answer the
    query.
    """
    return None


def supersede_belief(belief_id: Any, new_info: Dict[str, Any]) -> None:
    """Replace an outdated belief with updated information.

    Args:
        belief_id: The identifier of the old belief.
        new_info: The updated belief content.
    """
    # TODO: integrate with the memory librarian to supersede beliefs
    pass


def record_correction_pattern(old_belief: Any, new_info: Dict[str, Any]) -> None:
    """Record the pattern of the correction for learning.

    Args:
        old_belief: The old belief content or id.
        new_info: The updated belief content.
    """
    # TODO: log correction patterns for analysis
    pass


def handle_correction(ctx: Dict[str, Any]) -> None:
    """Process a user correction request.

    If the input is detected as a correction, this function attempts to
    supersede the contradicted belief with the new information and
    record the correction pattern.  In a full implementation, this
    would update the knowledge base accordingly.  Errors are silently
    ignored to avoid blocking the pipeline.
    """
    try:
        if not is_correction(ctx):
            return
        old_belief = find_contradicted_belief(ctx)
        new_info = ctx.get("new_info") or {}
        if old_belief:
            supersede_belief(old_belief, new_info)
        record_correction_pattern(old_belief, new_info)
    except Exception:
        pass