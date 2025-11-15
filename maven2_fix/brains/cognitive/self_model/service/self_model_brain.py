"""
Self‑Model Service
==================

The self‑model provides a reflective layer that allows Maven to
estimate whether it can answer a given query based on its current
beliefs.  It exposes a minimal API with a ``CAN_ANSWER`` operation
and a helper method ``can_answer`` for direct use by other modules.
This model does not attempt deep semantic understanding; instead it
uses heuristics over stored facts to judge its knowledge state.

Future enhancements may incorporate confidence calibration,
meta‑learning and a richer belief representation.
"""

from __future__ import annotations

from typing import Dict, Any, List, Tuple, Optional
import json
from pathlib import Path

# Import the belief tracker to retrieve related beliefs.  If the
# module is unavailable (e.g. in older Maven versions), fallback to
# the internal stub implementation defined below.
try:
    from brains.cognitive.belief_tracker.service.belief_tracker import find_related_beliefs as _bt_find_related  # type: ignore
except Exception:
    _bt_find_related = None  # type: ignore


class SelfModel:
    """A simple self‑model for estimating answerability.

    The current implementation inspects a list of related beliefs to
    determine if any are sufficiently confident to support an answer.
    Callers are responsible for populating the belief list; this class
    does not perform retrieval itself.
    """

    def __init__(self) -> None:
        pass

    def find_related_beliefs(self, query: str) -> List[Dict[str, Any]]:
        """Retrieve beliefs related to the query string.

        This method attempts to use the external belief tracker if
        available.  It falls back to an empty list when the belief
        tracker is not installed or an error occurs.  Each belief
        returned should contain at least a ``confidence`` key.

        Args:
            query: The user query string.
        Returns:
            A list of belief dictionaries, potentially empty.
        """
        # Prefer the belief tracker if present
        try:
            if _bt_find_related:
                return _bt_find_related(query) or []
        except Exception:
            # Ignore belief tracker errors and fall back to stub
            pass
        # Fallback stub: no beliefs available
        return []

    def can_answer(self, query: str) -> Tuple[bool, List[Dict[str, Any]]]:
        """Determine if the agent believes it can answer the query.

        This method retrieves related beliefs and checks whether the
        highest confidence exceeds a threshold (default 0.7).  If so it
        returns ``True`` along with the related beliefs; otherwise it
        returns ``False`` and an empty list.  Callers may adjust the
        threshold or extend this logic for more nuanced reasoning.

        Args:
            query: The user query.
        Returns:
            A tuple ``(can_answer, beliefs)`` where ``can_answer`` is
            ``True`` if the agent believes it can respond and
            ``beliefs`` contains the supporting evidence.
        """
        try:
            related = self.find_related_beliefs(query) or []
        except Exception:
            related = []
        if not related:
            return False, []
        # Extract the highest confidence from related beliefs
        try:
            highest = max((float(b.get("confidence", 0.0) or 0.0) for b in related))
        except Exception:
            highest = 0.0
        if highest > 0.7:
            return True, related
        return False, []

    # ------------------------------------------------------------------
    # New: load and provide self facts for direct identity queries.  The
    # self model maintains a minimal bank of immutable facts about the
    # agent (e.g. name, type, age policy).  These facts are stored in
    # ``brains/cognitive/self_model/memory/self_facts.json``.  The
    # ``query_self`` helper uses simple pattern matching to answer
    # questions like "who are you" or "how old are you".  It returns
    # both the response text and a flag indicating that the answer
    # originates from the self model.  Unsupported queries return
    # ``None`` so that callers may fallback to other modules.

    def _load_self_facts(self) -> Dict[str, Any]:
        """Load baseline self facts from the self_facts.json file.

        Returns an empty dict on error or if no model file exists.
        """
        try:
            here = Path(__file__).resolve().parent
            facts_path = here.parent / "memory" / "self_facts.json"
            if facts_path.exists():
                data = json.loads(facts_path.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else {}
        except Exception:
            pass
        return {}

    def query_self(self, query: str) -> Dict[str, Any]:
        """Attempt to answer a self‑referential question.

        Inspect the provided query for common identity questions.  If a
        match is found, return a success dict with answer and confidence.
        When no appropriate self answer exists, return an error dict.

        Args:
            query: Raw user query.
        Returns:
            A dict with ok, payload (text, confidence, self_origin) or error.
        """
        try:
            ql = (query or "").strip().lower()
        except Exception:
            return {
                "ok": False,
                "error": {
                    "code": "SELF_MODEL_FAILURE",
                    "message": "Self-model could not process the request."
                },
                "payload": {}
            }
        facts = self._load_self_facts() or {}
        name = str(facts.get("name")) or "Maven"
        kind = str(facts.get("type")) or "synthetic cognition system"
        # Extended self facts: creation date, creator, co‑creator, archivist and purpose
        creation_date = str(facts.get("creation_date")) if facts.get("creation_date") else None
        creator = str(facts.get("creator")) if facts.get("creator") else None
        co_creator = str(facts.get("co_creator")) if facts.get("co_creator") else None
        archivist = str(facts.get("archivist")) if facts.get("archivist") else None
        purpose = str(facts.get("purpose")) if facts.get("purpose") else None
        # Recognise questions about identity (who/what) and age
        # Who/what queries
        try:
            import re
            # Match phrases like "who are you", "who you are", "what is your name",
            # "what's your name", "are you maven", etc.
            if re.search(r"\b(who\s+are\s+you|who\s+you\s+are|what\s+is\s+your\s+name|what's\s+your\s+name|tell\s+me\s+about\s+yourself|are\s+you\s+maven)\b", ql):
                # Compose a richer self description by including extended self facts when available.
                # Start with the basic identity.  Then, if creation details exist, append them in one
                # coherent sentence.  Finally, mention the purpose if provided.
                parts = [f"I'm {name}, a {kind}."]
                # Include creation information when present
                if creation_date or creator or co_creator or archivist:
                    creation_bits = []
                    if creation_date:
                        creation_bits.append(f"in {creation_date}")
                    if creator:
                        creation_bits.append(f"by my architect {creator}")
                    if co_creator:
                        creation_bits.append(f"with the help of {co_creator}")
                    if archivist:
                        creation_bits.append(f"and documented by {archivist}")
                    # Join bits into a human‑readable fragment
                    creation_phrase = ", ".join(creation_bits)
                    parts.append(f"I was created {creation_phrase}.")
                # Include purpose
                if purpose:
                    parts.append(f"My purpose is {purpose}.")
                answer = " ".join(parts)
                return {
                    "ok": True,
                    "payload": {
                        "text": answer,
                        "confidence": 0.92,
                        "self_origin": True
                    }
                }
            # Age queries: "how old are you", "how old you", "your age"
            if re.search(r"\bhow\s+old\s+are\s+you\b", ql) or re.search(r"\bhow\s+old\s+you\b", ql) or re.search(r"\byour\s+age\b", ql):
                has_age = bool(facts.get("has_age", False))
                if not has_age:
                    # The agent does not have a biological age.  Offer to share
                    # uptime if available.  The actual uptime reporting is
                    # delegated to other modules, so only mention the
                    # possibility here.
                    return {
                        "ok": True,
                        "payload": {
                            "text": "I don't have a biological age; I'm software. I can share my uptime if you want.",
                            "confidence": 0.95,
                            "self_origin": True
                        }
                    }
                # If an age is explicitly provided in the facts, use it.
                explicit_age = facts.get("age")
                if explicit_age:
                    return {
                        "ok": True,
                        "payload": {
                            "text": f"I'm {explicit_age}.",
                            "confidence": 0.90,
                            "self_origin": True
                        }
                    }
                # Fallback: no age information
                return {
                    "ok": True,
                    "payload": {
                        "text": "I don't have a biological age; I'm software.",
                        "confidence": 0.90,
                        "self_origin": True
                    }
                }
            # Location queries: "where are you", "where are we"
            if re.search(r"\bwhere\s+are\s+you\b", ql) or re.search(r"\bwhere\s+are\s+we\b", ql):
                return {
                    "ok": True,
                    "payload": {
                        "text": "I'm a digital system running on a server, so I don't occupy a physical location like a person does.",
                        "confidence": 0.88,
                        "self_origin": True
                    }
                }

            # Capabilities queries.  Users may ask what the assistant can do or is capable of.
            # Match phrases like "what can you do", "what do you do", "what are your capabilities",
            # "what are you capable of", and related variations.  If detected, respond with
            # a concise summary of the assistant's core functions.
            try:
                if re.search(r"\bwhat\s+(?:can|do)\s+you\s+(?:do)?\b", ql) or \
                   re.search(r"\bwhat\s+are\s+(?:your|you)\s+(?:capabilities|abilities|skills)\b", ql) or \
                   re.search(r"\bwhat\s+are\s+you\s+capable\b", ql):
                    cap_reply = (
                        "I can answer questions, perform reasoning, store and recall information, generate creative content, "
                        "write code snippets, summarise texts, and assist with planning and problem solving."
                    )
                    return {
                        "ok": True,
                        "payload": {
                            "text": cap_reply,
                            "confidence": 0.9,
                            "self_origin": True
                        }
                    }
            except Exception:
                pass

            # Preference/likes queries.  Detect when a question asks about
            # Maven's personal tastes using a robust token‑based approach.
            # Examples include "what do you like", "do you prefer", "what are your
            # preferences", "do you enjoy", "are you into", or misspellings like
            # "likee" and "preferances".  We require the presence of a second
            # person pronoun (you/your/yourself) together with a token that
            # begins with a recognised preference root.  This avoids triggering
            # on arbitrary uses of preference words that do not involve
            # the assistant.  If detected, return a generic explanation that the
            # assistant has no personal preferences.
            try:
                import re
                tokens = re.findall(r"\b\w+\b", ql)
                pronouns = {"you", "your", "yourself"}
                pref_roots = [
                    "like", "lik", "prefer", "preferenc", "preferanc",
                    "favor", "favour", "favorite", "favourite",
                    "enjoy", "into", "interested", "love"
                ]
                found_pronoun = any(tok in pronouns for tok in tokens)
                found_pref = any(any(tok.startswith(root) for root in pref_roots) for tok in tokens)
                if found_pronoun and found_pref:
                    pref_reply = (
                        "I don't have personal likes or preferences—I'm a software "
                        "assistant designed to help answer questions, provide information "
                        "and assist with tasks. If you have something specific you'd like "
                        "to know or do, feel free to ask!"
                    )
                    return {
                        "ok": True,
                        "payload": {
                            "text": pref_reply,
                            "confidence": 0.88,
                            "self_origin": True
                        }
                    }
            except Exception:
                pass
        except Exception:
            # On any regex error, fall back to no answer
            pass
        return {
            "ok": False,
            "error": {
                "code": "NO_SELF_ANSWER",
                "message": "Unsupported self query"
            },
            "payload": {}
        }


def describe_self(mode: str = "short") -> Dict[str, Any]:
    """Generate a structured self-description.

    Args:
        mode: Either "short" or "detailed"

    Returns:
        Dictionary with identity, capabilities, and limitations
    """
    model = SelfModel()
    facts = model._load_self_facts()

    if mode == "detailed":
        return {
            "identity": {
                "name": facts.get("name", "Maven"),
                "creator": facts.get("creator", "Josh Hinkle (Hink)"),
                "origin": facts.get("origin", "November 2025"),
                "role": facts.get("role", "offline personal intelligence"),
                "goals": facts.get("goals", [])
            },
            "capabilities": facts.get("capabilities", []),
            "limitations": facts.get("limitations", [])
        }
    else:
        return {
            "identity": {
                "name": facts.get("name", "Maven"),
                "role": facts.get("role", "offline personal intelligence")
            },
            "capabilities": facts.get("capabilities", []),
            "limitations": facts.get("limitations", [])
        }

def get_capabilities() -> List[str]:
    """Retrieve list of Maven's capabilities.

    Returns:
        List of capability strings
    """
    model = SelfModel()
    facts = model._load_self_facts()
    return facts.get("capabilities", [])

def get_limitations() -> List[str]:
    """Retrieve list of Maven's limitations.

    Returns:
        List of limitation strings
    """
    model = SelfModel()
    facts = model._load_self_facts()
    return facts.get("limitations", [])

def update_self_facts(updates: Dict[str, Any]) -> Dict[str, Any]:
    """Update self facts in a controlled way.

    Args:
        updates: Dictionary of updates to apply

    Returns:
        Updated facts or error
    """
    try:
        here = Path(__file__).resolve().parent
        facts_path = here.parent / "memory" / "self_facts.json"

        if facts_path.exists():
            current_facts = json.loads(facts_path.read_text(encoding="utf-8"))
        else:
            current_facts = {}

        for key, value in updates.items():
            if key in ["capabilities", "limitations"]:
                if isinstance(value, list):
                    if "add" in updates.get("_mode", {}):
                        current_facts.setdefault(key, []).extend(value)
                    else:
                        current_facts[key] = value
            elif key not in ["name", "creator", "origin", "role"]:
                current_facts[key] = value

        facts_path.write_text(json.dumps(current_facts, indent=2), encoding="utf-8")
        return {"ok": True, "updated_facts": current_facts}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def service_api(msg: Dict[str, Any]) -> Dict[str, Any]:
    """Entry point for the self‑model brain.

    Supports operations for identity, capabilities, and limitations.
    """
    op = str((msg or {}).get("op", "")).upper()
    mid = (msg or {}).get("mid")
    payload = (msg or {}).get("payload") or {}
    model = SelfModel()

    if op == "DESCRIBE_SELF":
        mode = str(payload.get("mode", "short"))
        description = describe_self(mode)
        return {
            "ok": True,
            "op": op,
            "mid": mid,
            "payload": description,
        }

    if op == "GET_CAPABILITIES":
        capabilities = get_capabilities()
        return {
            "ok": True,
            "op": op,
            "mid": mid,
            "payload": {"capabilities": capabilities},
        }

    if op == "GET_LIMITATIONS":
        limitations = get_limitations()
        return {
            "ok": True,
            "op": op,
            "mid": mid,
            "payload": {"limitations": limitations},
        }

    if op == "UPDATE_SELF_FACTS":
        updates = payload.get("updates", {})
        result = update_self_facts(updates)
        if result.get("ok"):
            return {
                "ok": True,
                "op": op,
                "mid": mid,
                "payload": result,
            }
        else:
            return {
                "ok": False,
                "op": op,
                "mid": mid,
                "error": {"code": "UPDATE_FAILED", "message": result.get("error", "Unknown error")},
            }

    if op == "CAN_ANSWER":
        q = str(payload.get("query", ""))
        can_ans, beliefs = model.can_answer(q)
        return {
            "ok": True,
            "op": op,
            "mid": mid,
            "payload": {
                "can_answer": can_ans,
                "beliefs": beliefs,
            },
        }

    if op == "QUERY_SELF":
        q = str(payload.get("query", ""))
        result = model.query_self(q)
        if result.get("ok"):
            return {
                "ok": True,
                "op": op,
                "mid": mid,
                "payload": result.get("payload", {}),
            }
        return {
            "ok": False,
            "op": op,
            "mid": mid,
            "error": result.get("error", {"code": "NO_SELF_ANSWER", "message": "Unsupported self query"}),
        }

    return {
        "ok": False,
        "op": op,
        "mid": mid,
        "error": {"code": "UNSUPPORTED_OP", "message": op},
    }