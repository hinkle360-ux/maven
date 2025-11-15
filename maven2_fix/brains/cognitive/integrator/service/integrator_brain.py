"""
Integrator Brain
================

This module provides a minimal implementation of the proposed
cognitive synchronisation layer outlined in the Stage 2.5 → 3.0
roadmap.  The purpose of the integrator brain is to arbitrate
attention between specialist brains and, in future phases, to
coordinate meta‑cognitive functions such as self‑modelling and
cross‑brain messaging.  For now, it implements a simple attention
manager that resolves competing bids for cognitive focus.

The integrator brain exposes a ``service_api`` entry point with a
single operation:

``RESOLVE``
    Accepts a list of bids from other brains (each encoded as a
    dictionary with ``brain_name``, ``priority``, ``reason`` and
    ``evidence`` keys) and returns the name of the brain that should
    receive focus.  The resolution algorithm implements the rule‑based
    arbiter described in the roadmap: contradictions detected by the
    reasoning brain take precedence, followed by unanswered questions
    handled by the language brain, then the bid with the highest
    priority value.

The module also defines two simple data containers, ``BrainBid`` and
``AttentionState``.  These are plain Python classes rather than
dataclasses because they need to remain lightweight and avoid pulling
in additional dependencies.  ``BrainBid`` encapsulates a single bid
from a brain for attention, while ``AttentionState`` records the
current focus and a history of resolved transitions.  The history is
not persisted across runs and is maintained in memory only for
debugging purposes.

This implementation is deliberately conservative: it does not attempt
to modify the global pipeline directly.  Downstream callers such as
``memory_librarian.service`` may import this module and call
``service_api`` with the ``RESOLVE`` op to determine which brain
should take precedence during the current pipeline invocation.  The
decision and its supporting evidence can then be recorded in the
context for auditing or future self‑review.
"""

from __future__ import annotations

from typing import Dict, Any, List, Optional


class BrainBid:
    """Simple container representing a bid for attention from a brain.

    Attributes:
        brain_name: The canonical name of the brain submitting the bid.
        priority: A numeric value between 0.0 and 1.0 indicating
            urgency/confidence.  Higher values win when no overriding
            conditions are met.
        reason: A short string describing why the brain is bidding.
        evidence: Arbitrary additional data supporting the bid.
    """

    def __init__(self, brain_name: str, priority: float, reason: str, evidence: Optional[Dict[str, Any]] = None) -> None:
        self.brain_name = str(brain_name)
        # Clamp priority to the [0.0, 1.0] range
        try:
            p = float(priority)
        except Exception:
            p = 0.0
        if p < 0.0:
            p = 0.0
        if p > 1.0:
            p = 1.0
        self.priority = p
        self.reason = str(reason)
        self.evidence = evidence or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "brain_name": self.brain_name,
            "priority": self.priority,
            "reason": self.reason,
            "evidence": self.evidence,
        }


class AttentionTransition:
    """Record of an attention state change.

    Each transition captures the previous and next brain focus, the
    reason for the change and any associated evidence.  These records
    are stored in ``AttentionState.history`` for auditing and may be
    used during self‑review phases to analyse how the integrator is
    allocating cognitive resources.
    """

    def __init__(self, previous: str, current: str, reason: str, evidence: Optional[Dict[str, Any]] = None) -> None:
        self.previous_focus = previous
        self.current_focus = current
        self.reason = reason
        self.evidence = evidence or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "previous_focus": self.previous_focus,
            "current_focus": self.current_focus,
            "reason": self.reason,
            "evidence": self.evidence,
        }


class AttentionState:
    """Encapsulate the current attention focus and its history.

    ``current_focus`` holds the name of the brain that presently has
    attention.  ``focus_strength`` is a float in [0.0, 1.0] that could
    represent how strongly this focus should be maintained – future
    enhancements may adjust this value based on domain confidence or
    urgency.  ``focus_reason`` stores the justification for the
    current focus.  ``competing_bids`` retains the latest set of
    processed bids.  ``history`` accumulates ``AttentionTransition``
    instances describing previous state changes.
    """

    def __init__(self) -> None:
        self.current_focus: str = ""
        self.focus_strength: float = 0.0
        self.focus_reason: str = ""
        self.competing_bids: List[BrainBid] = []
        self.history: List[AttentionTransition] = []

    def update(self, new_focus: str, reason: str, evidence: Optional[Dict[str, Any]] = None) -> None:
        # Record transition if there is an existing focus
        if self.current_focus:
            self.history.append(AttentionTransition(self.current_focus, new_focus, reason, evidence))
        self.current_focus = new_focus
        self.focus_reason = reason
        self.focus_strength = 1.0  # Default to full focus strength for now
        # Preserve the evidence on competing bids for traceability
        if evidence:
            # Store in evidence of the latest transition for introspection
            pass


_STATE = AttentionState()


def _resolve_attention(bids: List[BrainBid]) -> str:
    """Resolve the winning brain from a list of bids.

    Implements the rule‑based arbiter described in the roadmap.

    1. If any bid's reason is ``contradiction_detected``, return the
       ``brain_name`` of the first such bid.  Contradiction resolution
       takes absolute priority.
    2. If any bid's reason is ``unanswered_question``, return the
       ``brain_name`` of the first such bid.  Questions are answered
       before other considerations.
    3. Otherwise, return the ``brain_name`` of the bid with the
       maximum ``priority`` value.

    If the input list is empty, the default focus is ``"language"``.
    """
    if not bids:
        return "language"
    # Rule 1: contradictions override everything
    for b in bids:
        if b.reason == "contradiction_detected":
            return b.brain_name
    # Rule 2: unanswered questions override remaining
    for b in bids:
        if b.reason == "unanswered_question":
            return b.brain_name
    # Rule 3: highest priority wins
    winner = max(bids, key=lambda x: x.priority)
    return winner.brain_name


def service_api(msg: Dict[str, Any]) -> Dict[str, Any]:
    """Entry point for the integrator brain.

    The ``msg`` must contain an ``op`` field specifying the operation
    and may include a ``payload`` field with additional data.  Only
    the ``RESOLVE`` operation is currently supported.  The payload
    should include a ``bids`` key containing a list of bid dictionaries.

    Returns a dictionary with ``ok`` status and, when resolving,
    the ``focus`` key indicating the chosen brain.  The current
    attention state (including competing bids and history) is also
    returned for traceability.
    """
    try:
        op = (msg.get("op") or "").upper()
    except Exception:
        op = ""
    payload: Dict[str, Any] = msg.get("payload") or {}
    mid = msg.get("mid") or "UNKNOWN"
    if op == "RESOLVE":
        # Build bid objects from raw payload entries
        raw_bids = payload.get("bids") or []
        bids: List[BrainBid] = []
        for rb in raw_bids:
            try:
                bids.append(BrainBid(
                    brain_name=rb.get("brain_name"),
                    priority=rb.get("priority", 0.0),
                    reason=rb.get("reason", ""),
                    evidence=rb.get("evidence", {}),
                ))
            except Exception:
                continue
        # Step‑3 & 4 enhancements: incorporate motivation weights into attention
        motivation_weights: Dict[str, float] = {}
        try:
            from brains.cognitive.motivation.service.motivation_brain import service_api as motivation_api  # type: ignore
            query = str(payload.get("query", ""))
            context = payload.get("context", {})

            resp = motivation_api({
                "op": "EVALUATE_QUERY",
                "payload": {"query": query, "context": context}
            })
            if resp.get("ok"):
                motivation_weights = (resp.get("payload") or {}).get("weights", {})
        except Exception:
            pass

        # Apply motivation-weighted priority adjustments
        if motivation_weights:
            for b in bids:
                brain_name = str(b.brain_name).lower()
                try:
                    weight_boost = 0.0

                    if brain_name == "language":
                        weight_boost = motivation_weights.get("helpfulness", 0.8) * 0.1
                    elif brain_name == "reasoning":
                        weight_boost = (
                            motivation_weights.get("truthfulness", 0.9) * 0.1 +
                            motivation_weights.get("curiosity", 0.5) * 0.05
                        )
                    elif brain_name == "planner":
                        weight_boost = motivation_weights.get("self_improvement", 0.5) * 0.1

                    if weight_boost > 0:
                        b.priority = min(1.0, float(b.priority) + weight_boost)
                        b.evidence = b.evidence or {}
                        b.evidence["motivation_boost"] = weight_boost
                        b.evidence["motivation_weights"] = motivation_weights
                except Exception:
                    pass

        # Apply attention nudge if enabled
        nudge_enabled = False
        try:
            from api.utils import CFG  # type: ignore
            nudge_enabled = bool((CFG.get("wm", {}) or {}).get("nudge", False))
        except Exception:
            pass
        if nudge_enabled:
            for b in bids:
                if b.brain_name in ("reasoning", "planner"):
                    try:
                        b.priority = min(1.0, float(b.priority) + 0.05)
                        b.evidence = b.evidence or {}
                        b.evidence["nudge"] = "wm_overlap"
                    except Exception:
                        pass

        # Query the motivation brain for overall drive to scale all priorities
        drive = 0.0
        try:
            from brains.cognitive.motivation.service.motivation_brain import service_api as motivation_api  # type: ignore
            resp = motivation_api({"op": "SCORE_DRIVE", "payload": {"context": context or {}}})
            drive = float((resp.get("payload") or {}).get("drive", 0.0))
        except Exception:
            drive = 0.0
        if drive:
            for b in bids:
                try:
                    b.priority = min(1.0, float(b.priority) * (1.0 + 0.2 * drive))
                    b.evidence = b.evidence or {}
                    b.evidence["drive_scaling"] = drive
                except Exception:
                    pass
        # Resolve the winning brain after adjustments
        _STATE.competing_bids = bids
        focus = _resolve_attention(bids)
        _STATE.update(focus, reason="resolved_attention", evidence={"bids": [b.to_dict() for b in bids]})
        return {
            "ok": True,
            "mid": mid,
            "payload": {
                "focus": focus,
                "state": {
                    "current_focus": _STATE.current_focus,
                    "focus_strength": _STATE.focus_strength,
                    "focus_reason": _STATE.focus_reason,
                    "competing_bids": [b.to_dict() for b in _STATE.competing_bids],
                    "history": [t.to_dict() for t in _STATE.history],
                },
            },
        }
    elif op == "STATE":
        # Return the current attention state without modifications
        return {
            "ok": True,
            "mid": mid,
            "payload": {
                "state": {
                    "current_focus": _STATE.current_focus,
                    "focus_strength": _STATE.focus_strength,
                    "focus_reason": _STATE.focus_reason,
                    "competing_bids": [b.to_dict() for b in _STATE.competing_bids],
                    "history": [t.to_dict() for t in _STATE.history],
                }
            },
        }
    else:
        return {"ok": False, "mid": mid, "error": {"code": "UNSUPPORTED_OP", "message": f"Unsupported op: {op}"}}

# Ensure the integrator brain exposes a `handle` entry point
try:
    handle = service_api  # type: ignore[assignment]
    service_api = handle  # type: ignore[assignment]
except Exception:
    pass