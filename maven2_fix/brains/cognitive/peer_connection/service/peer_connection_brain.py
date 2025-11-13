"""
Peer Connection Brain Service
----------------------------

This brain simulates establishing connections to peers for real‑time
communication.  It is minimal by design: the only supported operation
is ``CONNECT``, which accepts a ``peer_id`` in the payload and returns a
confirmation message.  If called with an unsupported operation or an
invalid payload, it returns an error.

This brain can be invoked from the language layer when a command like
"connect to peer 123" is parsed.  It does not perform any real network
operations; instead, it logs the intent and responds with a static
acknowledgement.  Future versions could integrate with an actual
transport layer.
"""

from __future__ import annotations
from typing import Dict, Any

def service_api(msg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Entry point for the peer connection brain.

    Args:
        msg: A dictionary containing ``op`` and an optional ``payload``.  The
            ``op`` field determines the action to perform.  Recognized
            operations:

            - ``CONNECT``: Establish a connection to a peer.  The ``payload``
              should include ``peer_id`` as a string or integer.  On
              success, the response payload contains a human‑friendly
              confirmation message.  If the peer_id is missing or invalid,
              returns an error.

    Returns:
        A dictionary with either a ``payload`` describing the result or an
        ``error`` indicating why the operation failed.  The top‑level
        ``ok`` field indicates whether the operation succeeded.
    """
    op = str((msg or {}).get("op", "")).upper()
    payload = (msg or {}).get("payload") or {}
    # Handle peer delegation of tasks.  When asked to delegate a task to a
    # peer, create a new goal in the personal memory and return a
    # confirmation message.  The payload should include both ``peer_id``
    # and ``task`` (or ``goal``) fields.
    if op == "DELEGATE":
        peer_id = payload.get("peer_id")
        task = payload.get("task") or payload.get("goal")
        # Normalize peer_id to string and ensure it's non‑empty
        try:
            peer_str = str(peer_id).strip()
        except Exception:
            peer_str = ""
        try:
            task_str = str(task).strip()
        except Exception:
            task_str = ""
        if not peer_str or not task_str:
            return {
                "ok": False,
                "error": {
                    "code": "INVALID_DELEGATE",
                    "message": "Both peer_id and task are required for delegation."
                }
            }
        # Add the delegated task as a goal in personal memory.  Use the
        # description field to record which peer it is assigned to.
        try:
            from brains.personal.memory import goal_memory  # type: ignore
            rec = goal_memory.add_goal(task_str, description=f"DELEGATED_TO:{peer_str}")
            goal_id = rec.get("goal_id")
        except Exception:
            goal_id = None
        return {
            "ok": True,
            "payload": {
                "message": f"Delegated task '{task_str}' to peer {peer_str}.",
                "goal_id": goal_id,
                "peer_id": peer_str,
                "task": task_str,
            }
        }

    # Handle peer queries. When asked to query a peer, return a stubbed
    # response and optionally record the question in a log.  The payload
    # should include ``peer_id`` and ``question`` fields.
    if op == "ASK":
        peer_id = payload.get("peer_id")
        question = payload.get("question") or payload.get("q")
        # Normalize fields to strings and strip whitespace
        try:
            peer_str = str(peer_id).strip()
        except Exception:
            peer_str = ""
        try:
            qstr = str(question).strip()
        except Exception:
            qstr = ""
        if not peer_str or not qstr:
            return {
                "ok": False,
                "error": {
                    "code": "INVALID_QUERY",
                    "message": "Both peer_id and question are required for a peer query."
                }
            }
        # Formulate a stubbed response.  A future implementation could
        # delegate the question to an actual agent.  Here we simply
        # acknowledge the query and echo back a generic placeholder answer.
        response_text = (
            f"Peer {peer_str} acknowledges your question about '{qstr}', "
            "but cannot answer right now."
        )
        # Persist the query to a log file for audit.  We write to
        # reports/peer_queries.jsonl relative to the Maven root.  Failure to
        # write should not interrupt the response.
        try:
            from pathlib import Path  # type: ignore
            import json  # type: ignore
            # Determine the Maven root by ascending from this module's path.
            root = Path(__file__).resolve().parents[4]
            log_path = root / "reports" / "peer_queries.jsonl"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "peer_id": peer_str,
                "question": qstr,
                "response": response_text,
                "timestamp": __import__("time").time()
            }
            with log_path.open("a", encoding="utf-8") as fh:
                json.dump(entry, fh)
                fh.write("\n")
        except Exception:
            pass
        return {
            "ok": True,
            "payload": {
                "message": response_text,
                "peer_id": peer_str,
                "question": qstr
            }
        }

    # Only one operation is currently supported
    if op == "CONNECT":
        peer_id = payload.get("peer_id")
        # Normalize peer_id to string and ensure it's non‑empty
        peer_id_str: str
        try:
            peer_id_str = str(peer_id).strip()
        except Exception:
            peer_id_str = ""
        if not peer_id_str:
            return {
                "ok": False,
                "error": {
                    "code": "INVALID_PEER_ID",
                    "message": "A valid peer_id is required to establish a connection."
                }
            }
        # Simulate connecting to the peer.  In this offline environment no
        # actual network connection is made; we simply return a message.
        return {
            "ok": True,
            "payload": {
                "message": f"Connected to peer {peer_id_str} for real‑time communication."
            }
        }
    # Unsupported operation
    return {
        "ok": False,
        "error": {
            "code": "UNSUPPORTED_OP",
            "message": op
        }
    }

# Ensure the peer_connection brain exposes a `handle` entry point
try:
    handle = service_api  # type: ignore[assignment]
    service_api = handle  # type: ignore[assignment]
except Exception:
    pass