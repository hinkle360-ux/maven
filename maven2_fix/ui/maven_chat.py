"""
Natural Language Chat Interface for Maven (Improved)
===================================================

This module provides a conversational entry point into the Maven system.  It
leverages the Language brain to parse user utterances and determine
communicative intent before dispatching the request to the appropriate
subsystem.  Statements and questions are evaluated via the full pipeline
through the Memory Librarian.  Self‑DMN maintenance operations (tick,
reflect, dissent scan) are invoked when explicitly requested.  The
confidence used for pipeline execution is derived from the language
brain's confidence penalty, allowing subjective content (emotions,
opinions, speculation) to be treated with appropriate caution.

To use this interface from the command line, run:

    python -m maven.ui.maven_chat

and enter queries at the prompt.  Type ``exit`` or ``quit`` to stop.  This
file lives in the ``ui`` package and is imported by ``run_maven.py`` when
no arguments are provided.
"""

from __future__ import annotations

import re
import time
import sys
import json
from datetime import datetime
from pathlib import Path
from typing import Tuple, Dict, Any

# At runtime this module may be executed either via ``python -m maven.ui.maven_chat``
# or directly as a script.  When executed as a script, Python's import
# machinery does not automatically include the Maven project root (which
# contains the ``api`` package) on ``sys.path``.  To ensure that
# ``from api.utils import generate_mid`` succeeds regardless of how this
# file is launched, attempt to import ``api.utils`` and, on failure,
# insert the project root into ``sys.path`` dynamically.  The project
# root is two directories up from this file (``.../maven/ui`` → ``.../maven``).
try:
    from api.utils import generate_mid  # type: ignore
except ModuleNotFoundError:
    # Compute the absolute path to the project root (two parents up)
    current_dir = Path(__file__).resolve()
    project_root = current_dir.parents[1]
    # Prepend project root to sys.path if not already present
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from api.utils import generate_mid  # type: ignore

# Import brains dynamically to avoid cyclic dependencies when run as a script.
try:
    from brains.cognitive.language.service import language_brain  # type: ignore
except Exception:
    language_brain = None  # type: ignore
try:
    from brains.cognitive.memory_librarian.service import memory_librarian  # type: ignore
except Exception:
    memory_librarian = None  # type: ignore
try:
    from brains.cognitive.self_dmn.service import self_dmn_brain  # type: ignore
except Exception:
    self_dmn_brain = None  # type: ignore
try:
    from brains.cognitive import correction_handler  # type: ignore
except Exception:
    correction_handler = None  # type: ignore

# Module level variables for chat logging and pending actions.
#
# When a chat session is started via ``repl()``, ``_CONV_FILE`` is set to
# the path of a JSONL file under ``reports/agent/chat``.  Each turn of
# the conversation is appended as a JSON object with ``ts``, ``user``,
# ``intent`` and ``response`` fields.  Logging is best effort:
# failures to open or write the file are silently ignored.
#
# The ``_PENDING_ACTION`` variable stores a tuple describing a
# deferred operation that requires user confirmation.  It is set by
# commands that would cause side effects (e.g. storing a fact or
# registering a claim).  When set, the next call to ``process``
# expects the user to respond "yes" or "no".  A positive response
# triggers the stored callable and clears the pending action; a
# negative response clears the pending action without performing any
# operation.  Any other response also clears the pending action and
# proceeds to handle the input normally.
_CONV_FILE: str | None = None
# Pending action tuple (callable, args tuple, kwargs dict, name) or None
_PENDING_ACTION: tuple | None = None


def _sanitize_for_log(text: str) -> str:
    """
    Sanitize a string before logging by masking email addresses and
    long alphanumeric tokens that may represent secrets or IDs.

    This helper replaces anything that looks like an email address with
    ``<EMAIL>`` and any contiguous run of 16 or more alphanumeric
    characters with ``<TOKEN>``.  It is intended to prevent the
    accidental recording of sensitive data in chat logs while still
    retaining the overall shape of the conversation for auditing.

    Args:
        text: The text to sanitize.

    Returns:
        A sanitized version of the text safe for logging.
    """
    try:
        # Mask email addresses
        text = re.sub(r"([A-Za-z0-9_.+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9.-]+)", "<EMAIL>", text)
        # Mask long tokens (16+ alphanumeric characters)
        text = re.sub(r"[A-Za-z0-9]{16,}", "<TOKEN>", text)
    except Exception:
        pass
    return text


def _log_turn(user_text: str, intent: str, response: str) -> None:
    """Append a single chat turn to the conversation log.

    If a conversation file has been established by the REPL, this
    function writes a single JSON line containing the timestamp,
    user input, interpreted intent and system response.  Prior to
    writing, the user and response strings are sanitized to mask
    potential secrets such as email addresses or long tokens.  Logging
    errors are ignored to avoid disrupting the chat flow.

    Args:
        user_text: The raw input entered by the user.
        intent: The high‑level intent determined for this turn.
        response: The response returned to the user.
    """
    global _CONV_FILE
    if not _CONV_FILE:
        return
    entry = {
        "ts": datetime.utcnow().isoformat(),
        "user": _sanitize_for_log(user_text),
        "intent": intent,
        "response": _sanitize_for_log(response),
    }
    try:
        with open(_CONV_FILE, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except Exception:
        # Do not surface logging errors
        pass


def _parse_language(text: str) -> Dict[str, Any]:
    """Call the language brain to parse the text and return the parsed payload.

    If the language brain is unavailable, a fallback classification is
    returned: the input is treated as a FACT statement with no penalty.

    Args:
        text: The user utterance.

    Returns:
        A dictionary of parsed metadata including ``storable_type`` and
        ``confidence_penalty``.
    """
    if language_brain is None:
        # Fallback: treat everything as a fact with zero penalty
        return {
            "storable_type": "FACT",
            "storable": True,
            "confidence_penalty": 0.0,
        }
    mid = generate_mid()
    try:
        resp = language_brain.service_api({"op": "PARSE", "mid": mid, "payload": {"text": text}})
        parsed = (resp or {}).get("payload") or {}
        return parsed
    except Exception:
        # On error, fallback classification
        return {
            "storable_type": "FACT",
            "storable": True,
            "confidence_penalty": 0.0,
        }


def _interpret_intent(text: str, parsed: Dict[str, Any]) -> str:
    """Determine a high‑level intent based on the raw text and parse result.

    This function inspects the user utterance for explicit maintenance
    commands (tick, reflect, dissent) and otherwise uses the storable_type
    to decide whether to run the full pipeline.  Commands take priority
    over the storable_type classification.

    Args:
        text: The raw user utterance.
        parsed: The parsed metadata from the language brain.

    Returns:
        One of ``dmn_tick``, ``dmn_reflect``, ``dmn_dissent`` or ``pipeline``.
    """
    lower = text.strip().lower()
    # Explicit Self‑DMN commands override other intents
    if any(word in lower for word in ["tick", "advance hum", "oscillator"]):
        return "dmn_tick"
    if "reflect" in lower:
        return "dmn_reflect"
    if any(word in lower for word in ["dissent", "scan", "rescan"]):
        return "dmn_dissent"
    # Status or health requests
    if any(word in lower for word in ["status", "health", "counts"]):
        return "status"
    # Summaries or reports and export requests
    if any(word in lower for word in ["summary", "summarize", "report", "dashboard", "export"]):
        return "summary"
    # Retrieval requests (search memory)
    if ("search" in lower or "find" in lower or "lookup" in lower) and "memory" in lower:
        return "retrieve"
    # Router explanation requests
    if "router" in lower and ("explain" in lower or "why" in lower or "route" in lower or "bank" in lower):
        return "router_explain"
    # Register claim
    if "register" in lower and "claim" in lower:
        return "register_claim"
    # Explicit store command (but will ultimately run through pipeline)
    if lower.startswith("store ") or lower.startswith("remember ") or lower.startswith("save "):
        return "pipeline"
    # Default: treat as pipeline request (question or statement)
    return "pipeline"


def process(text: str) -> str:
    """Handle a user utterance by dispatching to the appropriate brain.

    The utterance is first parsed by the language brain to determine
    intent and confidence penalties.  Self‑DMN commands are executed
    directly.  All other utterances are passed through the full
    pipeline via the Memory Librarian.  The resulting answer is
    returned along with a confidence score when available.

    Args:
        text: The raw user utterance.

    Returns:
        A human‑friendly response string.
    """
    # If there is a pending action awaiting user consent, handle it first.
    global _PENDING_ACTION
    if _PENDING_ACTION is not None:
        # Unpack pending action
        cb, args, kwargs, action_name = _PENDING_ACTION
        reply = text.strip().lower()
        # Acceptable affirmative responses
        yes_set = {"yes", "y", "ok", "okay", "sure", "proceed", "apply"}
        # Acceptable negative responses
        no_set = {"no", "n", "cancel", "stop", "abort"}
        if reply in yes_set:
            # Perform the deferred action
            try:
                result = cb(*args, **kwargs)
            except Exception as e:
                # Clear pending action before raising error
                _PENDING_ACTION = None
                return f"An error occurred while performing the {action_name.replace('_', ' ')}: {e}"
            # Clear the pending action
            _PENDING_ACTION = None
            return result
        elif reply in no_set:
            # Cancel the pending operation
            _PENDING_ACTION = None
            return "Operation cancelled."
        else:
            # Unrecognized response: clear and continue with normal processing
            _PENDING_ACTION = None
            # Fall through to standard handling below

    # Check if the input is user feedback (positive or negative) about the last answer
    if correction_handler is not None:
        try:
            if correction_handler.is_positive_feedback(text):
                # User confirmed the last answer was correct
                lib_api = memory_librarian.service_api if memory_librarian is not None else None
                return correction_handler.handle_positive_feedback(lib_api)
            elif correction_handler.is_negative_feedback(text):
                # User indicated the last answer was incorrect
                lib_api = memory_librarian.service_api if memory_librarian is not None else None
                return correction_handler.handle_negative_feedback(lib_api)
        except Exception:
            # If feedback handling fails, continue with normal processing
            pass

    # Obtain parse metadata
    parsed = _parse_language(text)
    st_type = str(parsed.get("storable_type", ""))
    penalty = 0.0
    try:
        penalty = float(parsed.get("confidence_penalty") or 0.0)
    except Exception:
        penalty = 0.0
    # Handle color preference queries early (workaround for pipeline issue)
    lower_text = text.strip().lower()
    if ("color" in lower_text and "like" in lower_text and ("what" in lower_text or "which" in lower_text)) or "favorite color" in lower_text or "favourite color" in lower_text:
        # Try to retrieve stored color preference
        if memory_librarian is not None:
            try:
                r = memory_librarian.service_api({
                    "op": "BRAIN_GET",
                    "payload": {
                        "scope": "BRAIN",
                        "origin_brain": "memory_librarian",
                        "key": "favorite_color"
                    }
                })
                if r and r.get("ok") and r.get("payload", {}).get("found"):
                    data = r.get("payload", {}).get("data", {})
                    if data and data.get("value"):
                        val = data["value"]
                        return f"You like the color {val}."
            except Exception:
                pass  # Fall through to normal processing

    # Determine high‑level intent
    intent = _interpret_intent(text, parsed)
    mid = generate_mid()
    try:
        # Handle Self‑DMN maintenance operations and meta commands
        if intent == "dmn_tick":
            if self_dmn_brain is None:
                return "Self‑DMN brain unavailable."
            self_dmn_brain.service_api({"op": "TICK", "mid": mid})
            return "Self‑DMN tick complete."
        if intent == "dmn_reflect":
            if self_dmn_brain is None:
                return "Self‑DMN brain unavailable."
            # Extract a numeric window if present
            match = re.search(r"(\d+)", text)
            window = int(match.group(1)) if match else 10
            resp = self_dmn_brain.service_api({"op": "REFLECT", "mid": mid, "payload": {"window": window}})
            metrics = (resp.get("payload") or {}).get("metrics") or {}
            counts = metrics.get("counts", {})
            return f"Reflection complete: {counts.get('runs', 0)} runs analysed." if counts else "Reflection complete."
        if intent == "dmn_dissent":
            if self_dmn_brain is None:
                return "Self‑DMN brain unavailable."
            match = re.search(r"(\d+)", text)
            window = int(match.group(1)) if match else 10
            resp = self_dmn_brain.service_api({"op": "DISSENT_SCAN", "mid": mid, "payload": {"window": window}})
            flagged = (resp.get("payload") or {}).get("flagged") or []
            return f"Dissent scan complete: {len(flagged)} claims flagged." if flagged else "No dissent found."
        # Status/health request
        if intent == "status":
            # Collate health from memory librarian and self‑DMN if available
            parts: list[str] = []
            if memory_librarian is not None:
                try:
                    hlth = memory_librarian.service_api({"op": "HEALTH", "mid": mid})
                    payload = hlth.get("payload") or {}
                    mh = payload.get("memory_health", {})
                    parts.append(f"Memory counts: STM={mh.get('stm', 0)}, MTM={mh.get('mtm', 0)}, LTM={mh.get('ltm', 0)}, COLD={mh.get('cold', 0)}")
                except Exception:
                    pass
            if self_dmn_brain is not None:
                try:
                    h = self_dmn_brain.service_api({"op": "HEALTH", "mid": mid})
                    pay = h.get("payload") or {}
                    parts.append(f"Self‑DMN status: {pay.get('status', 'unknown')}")
                except Exception:
                    pass
            if parts:
                return "; ".join(parts)
            return "Status unavailable."

        # Summary/report request
        if intent == "summary":
            try:
                import importlib
                sys_mod = importlib.import_module("brains.cognitive.system_history.service.system_history_brain")
                # Extract window if a number appears in the text
                match = re.search(r"(\d+)", text)
                window = int(match.group(1)) if match else 10
                res = sys_mod.service_api({"op": "SUMMARIZE", "mid": mid, "payload": {"window": window}})
                summ = (res.get("payload") or {}).get("summary") or {}
                agg = summ.get("aggregated", {})
                runs = agg.get("runs_analyzed", 0)
                decisions = agg.get("decisions", {})
                bank_use = agg.get("bank_usage", {})
                msg_parts = [f"Analysed {runs} runs"]
                if decisions:
                    dec_parts = [f"{k.lower()}: {v}" for k, v in decisions.items() if v]
                    if dec_parts:
                        msg_parts.append("decisions " + ", ".join(dec_parts))
                if bank_use:
                    bu_parts = [f"{b}: {c}" for b, c in bank_use.items()]
                    msg_parts.append("bank usage " + ", ".join(bu_parts))
                return "; ".join(msg_parts)
            except Exception:
                return "Could not generate summary."

        # Router explanation request
        if intent == "router_explain":
            # Explain which bank the routers would choose for the given text
            try:
                from importlib import import_module
                simple_bank = None
                learned_target = None
                learned_scores = None
                # Compute simple router suggestion if memory_librarian available
                if memory_librarian is not None:
                    try:
                        simple_bank = memory_librarian._simple_route_to_bank(text)
                    except Exception:
                        simple_bank = None
                # Compute learned router suggestion
                try:
                    lr_mod = import_module("brains.cognitive.reasoning.service.learned_router")
                    lr_resp = lr_mod.service_api({"op": "ROUTE", "payload": {"text": text}})
                    lp = lr_resp.get("payload") or {}
                    learned_target = lp.get("target_bank")
                    learned_scores = lp.get("scores")
                except Exception:
                    learned_target = None
                    learned_scores = None
                parts = []
                if simple_bank:
                    parts.append(f"Simple router suggests: {simple_bank}")
                if learned_target:
                    # Format scores for top few banks if available
                    score_desc = ""
                    if isinstance(learned_scores, dict):
                        # Get top 3 scores in descending order
                        try:
                            items = sorted(learned_scores.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
                            score_desc = ", ".join([f"{b}: {v:.2f}" for b, v in items])
                        except Exception:
                            score_desc = ""
                    if score_desc:
                        parts.append(f"Learned router suggests: {learned_target} (scores {score_desc})")
                    else:
                        parts.append(f"Learned router suggests: {learned_target}")
                if not parts:
                    return "Unable to determine routing explanation."
                return "; ".join(parts)
            except Exception:
                return "Could not explain routing."

        # Memory retrieval request
        if intent == "retrieve":
            if memory_librarian is None:
                return "Memory Librarian module unavailable."
            # Attempt to extract a query from the utterance.  Look for
            # patterns like 'for <text>' or 'about <text>'.  If none are
            # found, remove command words and treat the rest as the query.
            lower = text.lower()
            query: str | None = None
            m = re.search(r"(?:for|about)\s+(.+)", lower)
            if m:
                query = m.group(1).strip()
            else:
                # Remove the words 'search', 'find', 'lookup', 'memory'
                q = re.sub(r"\b(search|find|lookup|memory|for|about)\b", "", lower)
                query = q.strip()
            if not query:
                return "Please specify what to search for."
            # Perform retrieval across banks.  Use the librarian's internal helper
            # rather than a service op, since the service API does not
            # directly expose a RETRIEVE operation.  This helper returns
            # results aggregated from all banks with deduplication.
            try:
                results_data: Dict[str, Any] | None = None
                # Prefer the parallel implementation if available
                try:
                    # Some versions expose a parallel helper
                    results_data = memory_librarian._retrieve_from_banks_parallel(query, k=5)
                except Exception:
                    # Fallback to the serial implementation
                    results_data = memory_librarian._retrieve_from_banks(query, k=5)
                if not results_data:
                    return f"No memory entries found for '{query}'."
                res_list = results_data.get("results") or []
                if not res_list:
                    return f"No memory entries found for '{query}'."
                # Present up to three results with their bank names
                lines: list[str] = []
                for i, item in enumerate(res_list[:3], start=1):
                    content = item.get("content") or item.get("text") or str(item)
                    bank = item.get("source_bank") or item.get("bank") or "?"
                    summary = str(content)
                    # Truncate long summaries
                    if len(summary) > 60:
                        summary = summary[:57] + "..."
                    lines.append(f"{i}. {summary} (bank: {bank})")
                extra = "" if len(res_list) <= 3 else f" and {len(res_list) - 3} more"
                return f"Found {len(res_list)} result{'s' if len(res_list) != 1 else ''} for '{query}':\n" + "\n".join(lines) + extra
            except Exception:
                return "Failed to search memory."

        # Register claim request: defer execution until user confirms
        if intent == "register_claim":
            # Extract a proposition after the keyword 'claim' or 'register'
            prop = None
            m = re.search(r"claim\s+(.+)", text, flags=re.IGNORECASE)
            if m:
                prop = m.group(1).strip()
            if not prop:
                m = re.search(r"register\s+(.+)", text, flags=re.IGNORECASE)
                if m:
                    prop = m.group(1).strip()
            if not prop:
                return "Please specify a claim to register after the word 'claim'."

            # Define a closure that registers the claim when executed
            def _do_register_claim() -> str:
                # Import the skeptic module lazily
                import importlib  # type: ignore
                skeptic_mod = importlib.import_module("brains.cognitive.self_dmn.service.self_dmn_skeptic")
                cid = f"CL-{int(time.time()*1000)}"
                payload = {
                    "claim_id": cid,
                    "proposition": prop,
                    "consensus_score": 0.5,
                    "skeptic_score": 0.5,
                    "expiry": time.time() + 24*3600,
                }
                res = skeptic_mod.service_api({"op":"REGISTER","mid": mid, "payload": payload})
                claim = (res.get("payload") or {}).get("claim") or payload
                return f"Registered claim {claim.get('claim_id')} with status {claim.get('status', 'unknown')}"
            # Save pending action and return prompt
            _PENDING_ACTION = (_do_register_claim, tuple(), {}, "register_claim")  # type: ignore
            return "This will register a claim in Self‑DMN. Proceed? (yes/no)"

        # Otherwise run the full pipeline (question or statement).  If the user
        # explicitly used a store/remember/save prefix, defer execution until
        # user confirmation to avoid accidental writes.  On confirmation,
        # ``_do_store`` will execute the pipeline with the cleaned text.
        if memory_librarian is None:
            return "Memory Librarian module unavailable."
        # Determine if the user explicitly wants to store information
        lowered = text.strip().lower()
        cleaned_text = text
        store_used = False
        for prefix in ["store ", "remember ", "save "]:
            if lowered.startswith(prefix):
                cleaned_text = text[len(prefix):].strip()
                store_used = True
                break
        # Compute the confidence outside of any closure to capture penalty
        conf = 1.0 - penalty
        if conf < 0.1:
            conf = 0.1
        if conf > 1.0:
            conf = 1.0
        # If an explicit store command was used, set up a pending action
        if store_used:
            # use the module-level _PENDING_ACTION variable defined above
            def _do_store() -> str:
                resp_inner = memory_librarian.service_api({"op": "RUN_PIPELINE", "mid": mid, "payload": {"text": cleaned_text, "confidence": conf}})
                context_inner = ((resp_inner or {}).get("payload") or {}).get("context") or {}
                ans = context_inner.get("final_answer")
                cval = context_inner.get("final_confidence")
                if ans:
                    return str(ans)
                return "I'm not sure how to respond to that."
            _PENDING_ACTION = (_do_store, tuple(), {}, "store_fact")  # type: ignore
            return "This action will store new information. Proceed? (yes/no)"
        # Otherwise, run the pipeline immediately for questions and statements
        resp = memory_librarian.service_api({"op": "RUN_PIPELINE", "mid": mid, "payload": {"text": cleaned_text, "confidence": conf}})
        context = ((resp or {}).get("payload") or {}).get("context") or {}
        answer = context.get("final_answer")
        confidence = context.get("final_confidence")
        # If a final answer exists, publish it to the shared blackboard before returning
        if answer:
            # Best‑effort publish: do not raise errors if blackboard is unavailable
            try:
                from brains.agent.service import blackboard  # type: ignore
                payload: Dict[str, Any] = {
                    "type": "utterance",
                    "role": "assistant",
                    "text": answer,
                }
                # Include confidence if numeric
                try:
                    if isinstance(confidence, float):
                        payload["confidence"] = confidence
                except Exception:
                    pass
                blackboard.put("dialogue", payload)
            except Exception:
                # Silently ignore publish errors to avoid disrupting chat
                pass
            # Store this exchange for potential feedback processing
            if correction_handler is not None:
                try:
                    # Extract domain from the question (first 1-2 words)
                    words = cleaned_text.strip().split()
                    domain = " ".join(words[:2]) if len(words) >= 2 else words[0] if words else ""
                    conf_val = confidence if isinstance(confidence, float) else 0.4
                    correction_handler.set_last_exchange(
                        question=cleaned_text,
                        answer=str(answer),
                        confidence=conf_val,
                        domain=domain
                    )
                except Exception:
                    pass
            return str(answer)
        # ------------------------------------------------------------------
        # LLM fallback: When no final answer exists or the confidence is low or
        # the generic "I don't yet have enough information" message is
        # returned, attempt to generate a response using the local LLM.
        # This ensures the chat remains helpful even when the pipeline
        # provides no answer.  Only call the LLM when it is available.
        try:
            # Determine if the pipeline produced a fallback message
            fallback_trigger = False
            raw_ans = str(answer or "").strip().lower()
            if not answer:
                fallback_trigger = True
            elif raw_ans.startswith("i don't yet have enough information"):
                fallback_trigger = True
            # Fall back when the generic limitation message appears anywhere in the answer.  This catches
            # cases where the answer is quoted or has minor variations, e.g. "I don't yet have enough
            # information about photosynthesis simply to provide a summary."
            elif "i don't yet have enough information" in raw_ans:
                fallback_trigger = True
            # Also trigger when confidence is extremely low (<0.5)
            if isinstance(confidence, float) and confidence < 0.5:
                fallback_trigger = True
            if fallback_trigger:
                from brains.tools.llm_service import llm_service as _chat_llm  # type: ignore
                if _chat_llm is not None:
                    # Build a simple context with the session user name if available
                    user_name = None
                    try:
                        # Use the session identity from the pipeline context if present
                        user_name = context.get("session_identity") or None
                    except Exception:
                        user_name = None
                    call_ctx = {}
                    if user_name:
                        call_ctx["user"] = {"name": user_name}
                    # Generate a response directly from the LLM using the raw user text
                    llm_res = _chat_llm.call(prompt=text, context=call_ctx)
                    if llm_res and llm_res.get("ok") and llm_res.get("text"):
                        llm_text = str(llm_res.get("text"))
                        # Use provided confidence if available; default to 0.75
                        try:
                            cval = float(llm_res.get("confidence", 0.75) or 0.75)
                        except Exception:
                            cval = 0.75
                        # Store this exchange for potential feedback processing
                        if correction_handler is not None:
                            try:
                                words = cleaned_text.strip().split()
                                domain = " ".join(words[:2]) if len(words) >= 2 else words[0] if words else ""
                                correction_handler.set_last_exchange(
                                    question=cleaned_text,
                                    answer=llm_text,
                                    confidence=cval,
                                    domain=domain
                                )
                            except Exception:
                                pass
                        return llm_text
        except Exception:
            # Ignore any errors in LLM fallback to avoid crashing
            pass
        return "I'm not sure how to respond to that."
    except Exception as e:
        return f"An error occurred: {e}"


def repl() -> None:
    """Simple read‑eval‑print loop for interactive use."""
    print("Welcome to the Maven chat interface. Type 'exit' or 'quit' to leave.")
    # Initialise a conversation log file on first entry.  We defer the
    # creation until here so that import of this module does not have
    # side effects.  The log directory is reports/agent/chat to reuse
    # the existing agent logging area.  No new top‑level folders are
    # created.  The filename includes the start timestamp.
    global _CONV_FILE
    if _CONV_FILE is None:
        try:
            here = Path(__file__).resolve()
            maven_root = here.parents[2]
            log_dir = maven_root / "reports" / "agent" / "chat"
            log_dir.mkdir(parents=True, exist_ok=True)
            import time
            _CONV_FILE = str(log_dir / f"conv_{int(time.time())}.jsonl")
        except Exception:
            _CONV_FILE = None
    while True:
        try:
            raw = input("You: ")
        except EOFError:
            break
        # If nothing was entered, prompt again
        if raw is None:
            continue
        # Trim whitespace from both ends
        line = str(raw).strip()
        # Exit or quit commands (case-insensitive) before sanitisation
        if line.lower() in {"exit", "quit"}:
            print("Goodbye!")
            break
        # Sanitize the input: remove an accidental leading "You:" prefix
        # Users sometimes paste the "You:" prompt back into the input; strip it off
        lower_line = line.lower()
        if lower_line.startswith("you:"):
            line = line[4:].strip()
        # Remove surrounding quotes if both ends have a double quote
        if line.startswith('"') and line.endswith('"') and len(line) >= 2:
            line = line[1:-1].strip()
        # If only one quote appears at either end, strip all quotes
        elif line.startswith('"') or line.endswith('"'):
            line = line.replace('"', '').strip()
        # After sanitisation, if the line is empty, skip
        if not line:
            continue
        # Determine intent ahead of processing so we can log it
        parsed = _parse_language(line)
        intent = _interpret_intent(line, parsed)
        response = process(line)
        # Log the turn (best effort)
        _log_turn(line, intent, response)
        print(f"Maven: {response}")


if __name__ == "__main__":
    # When run as a script, adjust sys.path to ensure Maven modules can be imported
    here = Path(__file__).resolve()
    maven_root = here.parents[2]
    if str(maven_root) not in sys.path:
        sys.path.insert(0, str(maven_root))
    repl()