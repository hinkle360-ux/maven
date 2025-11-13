from __future__ import annotations
from typing import Dict, Any, List, Optional
import json
from pathlib import Path

# Step‑2 integration: import memory librarian service for working memory recall
try:
    from brains.cognitive.memory_librarian.service.memory_librarian import service_api as mem_service_api  # type: ignore
except Exception:
    mem_service_api = None  # type: ignore

# Deferred import of importlib for optional affect modulation.  Importing
# importlib here avoids circular dependencies when the affect brain
# depends on the reasoning brain.
import importlib

# Basic common‑sense knowledge.  This mapping associates well‑known entities
# with their correct categories.  It is used by _common_sense_check to
# detect blatantly incorrect questions such as "Is Mars a country?" and
# provide a corrective answer.  Additional entries may be added here
# to expand coverage of obvious facts.
COMMON_SENSE_CATEGORIES: Dict[str, str] = {
    "mars": "planet",
    "venus": "planet",
    "earth": "planet",
    "mercury": "planet",
    "jupiter": "planet",
    "saturn": "planet",
    "uranus": "planet",
    "neptune": "planet",
    "pluto": "dwarf planet",
    "moon": "natural satellite",
    "sun": "star",
    "paris": "city",
    "london": "city",
    "tokyo": "city",
    "new york": "city",
    "rome": "city",
    "berlin": "city"
}

# -----------------------------------------------------------------------------
# Telemetry logging
#
# The reasoning brain records statistics about certain filter events
# (e.g. safety and ethics checks) in a persistent telemetry file.  Each
# event type increments a counter in ``reports/telemetry.json``.  This
# helper function updates the file in a safe manner.  Errors in reading
# or writing the file are silently ignored to avoid disrupting the
# reasoning process.
def _update_telemetry(event_type: str) -> None:
    try:
        if not event_type:
            return
        root = REASONING_ROOT.parents[2]
        tpath = root / "reports" / "telemetry.json"
        # Load existing telemetry
        data: Dict[str, int] = {}
        if tpath.exists():
            try:
                with open(tpath, "r", encoding="utf-8") as fh:
                    tmp = json.load(fh) or {}
                if isinstance(tmp, dict):
                    for k, v in tmp.items():
                        try:
                            data[str(k)] = int(v)
                        except Exception:
                            continue
            except Exception:
                data = {}
        # Increment counter
        data[event_type] = data.get(event_type, 0) + 1
        # Persist updated telemetry
        try:
            tpath.parent.mkdir(parents=True, exist_ok=True)
            with open(tpath, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
        except Exception:
            pass
    except Exception:
        # Ignore all telemetry errors
        pass

def _common_sense_check(question: str) -> Optional[Dict[str, str]]:
    """
    Perform a simple sanity check on binary questions of the form
    "Is X a Y?".  If X is a known entity with a canonical category and
    Y does not match that category, return a corrective result.  Otherwise
    return None to indicate no correction is needed.

    Args:
        question: The raw question string.

    Returns:
        A dictionary with keys 'entity', 'correct', 'wrong' if a mismatch
        is detected, or None otherwise.
    """
    try:
        import re
        q = (question or "").strip().lower()
        # Normalize whitespace and remove punctuation for matching
        q_norm = re.sub(r"[^a-z0-9\s]", " ", q)
        q_norm = re.sub(r"\s+", " ", q_norm).strip()
        # Match patterns like "is X a Y" or "is X an Y"
        m = re.match(r"^is\s+(.*?)\s+an?\s+(.*?)$", q_norm)
        if m:
            entity = m.group(1).strip()
            category = m.group(2).strip()
            # Remove common articles from entity (e.g. the sun)
            entity = re.sub(r"^(the|a|an)\s+", "", entity).strip()
            # Look up in the common sense mapping; require exact match or
            # simple multi-word match
            if entity in COMMON_SENSE_CATEGORIES:
                correct_cat = COMMON_SENSE_CATEGORIES[entity]
                # If category does not match exactly or as a substring, treat as mismatch
                if category != correct_cat and category not in correct_cat:
                    return {"entity": entity, "correct": correct_cat, "wrong": category}
        return None
    except Exception:
        return None
# Compute the root directory for the reasoning brain.  This is used when
# calculating the rolling success average via compute_success_average.  The
# reasoning root corresponds to the directory containing this file's
# ``service`` folder, i.e. maven/brains/cognitive/reasoning.
THIS_FILE = Path(__file__).resolve()
REASONING_ROOT = THIS_FILE.parent.parent  # .../reasoning/service/ -> .../reasoning


def _is_question_text(text: str) -> bool:
    """
    Return True if the provided text appears to be phrased as a question.
    Currently this checks for a trailing question mark.
    """
    try:
        return str(text or "").strip().endswith("?")
    except Exception:
        return False


def _score_evidence(proposed: Dict[str, Any], evidence: Dict[str, Any]) -> float:
    """
    Compute a basic evidence score for a proposed fact given retrieval results.
    If any retrieved record matches the proposed content exactly or as a substring,
    return a high score (0.8).  Otherwise assign a nominal low score (0.4) if the
    proposed fact has any content, else 0.0.
    """
    try:
        content = str(proposed.get("content", "")).strip().lower()
        for it in (evidence or {}).get("results", []):
            if isinstance(it, dict):
                c = str(it.get("content", "")).strip().lower()
                if c and (content == c or content in c or c in content):
                    return 0.8
    except Exception:
        pass
    return 0.4 if proposed.get("content") else 0.0


def _educated_guess_for_question(query: str) -> str | None:
    """
    Provide a simple heuristic based educated guess for yes/no questions when there
    is no direct evidence available.  This helper inspects the lower‑cased query
    and returns a plausible answer string if a pattern is recognized.  Only a
    few illustrative patterns are currently supported.  If no guess can be made,
    returns None.
    """
    try:
        q_lower = (query or "").strip().lower()
    except Exception:
        q_lower = ""
    # Example heuristic: Do penguins have fur? → Penguins are birds; birds have feathers
    if "penguin" in q_lower and "fur" in q_lower:
        return "Probably not — penguins are birds and birds have feathers."
    # Additional patterns can be added here as needed
    return None

# -----------------------------------------------------------------------------
# Cross‑Episode QA Memory
#
# To enable long‑term learning across runs, the reasoner consults a simple
# question‑answer log stored under ``reports/qa_memory.jsonl``.  Each entry
# contains a question string and its corresponding answer.  When evaluating
# a new question, the reasoner will first attempt to find an exact or
# normalized match in this log.  If found, the stored answer is returned as
# a confident response (bypassing retrieval and heuristic guessing).

_QA_MEMORY_PATH = None  # Will be lazily initialised to reports/qa_memory.jsonl

def _qa_memory_lookup(question: str) -> str | None:
    """
    Search the QA memory for a stored answer to the given question.  The
    lookup normalises the question by lower‑casing and stripping trailing
    punctuation.  If multiple answers exist, the most recent is returned.

    Args:
        question: The user's original question string.

    Returns:
        The stored answer text if found, otherwise None.
    """
    global _QA_MEMORY_PATH
    try:
        q = str(question or "").strip().lower().rstrip("?")
        if not q:
            return None
        # Lazy init path
        if _QA_MEMORY_PATH is None:
            # Resolve path relative to the reasoning brain location
            # Ascend to the Maven repository root.  REASONING_ROOT points to
            # .../brains/cognitive/reasoning.  Its parents list yields:
            #   0 -> .../brains/cognitive
            #   1 -> .../brains
            #   2 -> .../maven
            # Using index 2 rather than 3 ensures we land at the top of the
            # maven repo (maven_new/maven) instead of one level too high
            # (maven_new).  Without this adjustment the QA memory file would
            # be looked up in maven_new/reports instead of maven_new/maven/reports.
            root = REASONING_ROOT.parents[2]
            p = root / "reports" / "qa_memory.jsonl"
            _QA_MEMORY_PATH = p
        path = _QA_MEMORY_PATH
        if not path.exists():
            return None
        ans = None
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if not isinstance(rec, dict):
                    continue
                stored_q = str(rec.get("question", "")).strip().lower().rstrip("?")
                if stored_q == q:
                    ans = rec.get("answer")
        return ans
    except Exception:
        return None


def _route_for(conf: float) -> str:
    """
    Determine which memory tier to route a fact into based on confidence.
    High confidence facts go into the factual bank, moderate confidence into
    working theories, and low confidence into STM only.
    """
    if conf >= 0.7:
        return "factual"
    if conf >= 0.4:
        return "working_theories"
    return "stm_only"


def service_api(msg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main entrypoint for the reasoning brain.  Supports EVALUATE_FACT and HEALTH.

    EVALUATE_FACT accepts a proposed fact and optional evidence.  It decides
    whether to accept the fact as TRUE, classify it as a THEORY, or mark it as
    UNKNOWN.  Questions are handled specially: the reasoner attempts to answer
    them using provided evidence and simple heuristics.  It also incorporates a
    learned bias signal from recent successes to gently adjust confidence.
    """
    op = (msg or {}).get("op", "").upper()
    mid = (msg or {}).get("mid")
    payload = (msg or {}).get("payload") or {}

    # ------------------------------------------------------------------
    # Custom operation: EXPLAIN_LAST
    #
    # When the Memory Librarian or another brain requests an explanation
    # of the last answer, this op constructs a simple derivation.  It
    # expects the payload to contain 'last_query' and 'last_response'.
    # For basic arithmetic questions (e.g. "2+3"), it parses the
    # expression and explains the operation.  For other inputs, it
    # returns a generic statement referencing the prior response.  The
    # returned payload uses a bespoke verdict to signal that this is
    # explanatory content rather than a truth judgement.  If any
    # exception occurs, a fallback explanation is returned.
    if op == "EXPLAIN_LAST":
        # Prepare default values
        last_q = str((payload or {}).get("last_query", ""))
        last_r = str((payload or {}).get("last_response", ""))
        explanation: str = ""
        try:
            import re as _re_exp
            # Basic arithmetic pattern: two integers with an operator
            m = _re_exp.match(r"\s*([-+]?\d+)\s*([+\-*/])\s*([-+]?\d+)\s*$", last_q)
            if m:
                a = int(m.group(1))
                op_char = m.group(2)
                b = int(m.group(3))
                result: Optional[float | int]
                verb: str
                if op_char == "+":
                    result = a + b
                    verb = "add"
                elif op_char == "-":
                    result = a - b
                    verb = "subtract"
                elif op_char == "*":
                    result = a * b
                    verb = "multiply"
                else:  # division
                    # Guard against division by zero
                    if b == 0:
                        result = None
                    else:
                        result = a / b
                    verb = "divide"
                if result is not None:
                    # Use integer representation when possible
                    if isinstance(result, float) and result.is_integer():
                        result = int(result)
                    explanation = f"To answer your previous question, I {verb} {a} and {b} to get {result}."
                else:
                    explanation = f"The previous calculation involved division by zero, which is undefined."
            # Fallback: if no arithmetic pattern matched or explanation not set
            if not explanation:
                if last_q and last_r:
                    explanation = f"I responded '{last_r}' to your previous query '{last_q}' based on my reasoning and stored knowledge."
                elif last_r:
                    explanation = f"I answered '{last_r}' in response to your previous question."
                else:
                    explanation = "I don't have enough context to provide an explanation."
        except Exception:
            # On any unexpected error, fall back to a generic explanation
            if last_r:
                explanation = f"I answered '{last_r}' previously based on my reasoning and memory."
            else:
                explanation = "I'm unable to provide an explanation due to missing context."
        # Assemble response.  Use a distinct verdict to differentiate
        # explanatory output from fact evaluation.  Confidence is set
        # optimistically as this operation simply reconstructs prior logic.
        return {
            "ok": True,
            "op": op,
            "mid": mid,
            "payload": {
                "verdict": "EXPLANATION",
                "mode": "EXPLANATION",
                "confidence": 0.95,
                "routing_order": {"target_bank": None, "action": None},
                "supported_by": [],
                "contradicted_by": [],
                "answer": explanation,
                "weights_used": {"rule": "explain_last_v1"},
            },
        }

    if op == "EVALUATE_FACT":
        # Extract the proposed fact and any original query information
        proposed = (payload or {}).get("proposed_fact") or {}
        # Some callers (Memory Librarian) will include original_query in the proposed fact.  If not
        # present, fall back to the proposed content so that question analysis and
        # semantic lookups still function when original_query isn't provided.  This
        # improves robustness when service_api is called directly without the
        # Memory Librarian, e.g. during tests.
        orig_q = str(proposed.get("original_query", "") or payload.get("original_query", "") or "")
        content = str(proposed.get("content", ""))
        # If original_query is empty but content exists, use content as the question text for
        # downstream heuristics and semantic retrieval.  This allows the reasoner to
        # handle cases where only the fact content is supplied (no original query).
        if not orig_q and content:
            orig_q = str(content)

        # Step‑2: Opportunistic recall from working memory.
        # Before performing heavy reasoning, attempt to retrieve a prior answer stored in working memory.
        try:
            if mem_service_api is not None:
                lookup_key = orig_q if orig_q else content
                # Only attempt recall for non-empty keys
                if lookup_key:
                    wm_resp = mem_service_api({
                        "op": "WM_GET",
                        "payload": {"key": lookup_key}
                    })
                    wm_entries = (wm_resp or {}).get("payload", {}).get("entries", [])
                    # Use the most recent entry if available
                    if wm_entries:
                        # Choose the last entry (most recent) and return as known answer
                        last_entry = wm_entries[-1]
                        answer_val = last_entry.get("value")
                        if answer_val is not None:
                            return {
                                "ok": True,
                                "op": op,
                                "mid": mid,
                                "payload": {
                                    "verdict": "KNOWN",
                                    "mode": "WM_RETRIEVED",
                                    # Use the entry's confidence or default to 0.7
                                    "confidence": float(last_entry.get("confidence", 0.7)),
                                    "routing_order": {"target_bank": None, "action": None},
                                    "supported_by": [],
                                    "contradicted_by": [],
                                    "answer": answer_val,
                                    "weights_used": {"rule": "wm_lookup_v1"},
                                },
                            }
        except Exception:
            # Ignore any WM retrieval errors
            pass

        # Determine if this input is a question by intent or punctuation.

        # Affect modulation: compute a valence adjustment for this fact or question.
        # Use the fact content when available, otherwise fall back to the original
        # query string.  The valence is later used to tweak confidence scores
        # slightly (positive valence raises confidence, negative lowers).
        # Extract affect metrics (valence and arousal) for modulation.
        # If the affect brain cannot be loaded or fails, fall back to zeros.
        aff_val: float = 0.0
        aff_arousal: float = 0.0
        try:
            ap_mod = importlib.import_module(
                "brains.cognitive.affect_priority.service.affect_priority_brain"
            )
            aff_text = content if content else orig_q
            aff_res = ap_mod.service_api({"op": "SCORE", "payload": {"text": aff_text}})
            aff_payload = aff_res.get("payload") or {}
            aff_val = float(aff_payload.get("valence", 0.0))
            aff_arousal = float(aff_payload.get("arousal", 0.0))
        except Exception:
            aff_val = 0.0
            aff_arousal = 0.0

        # --- Topic familiarity modulation ----------------------------------
        # Adjust affect valence based on the frequency of this question's
        # topic in the cross‑episode statistics.  Questions that have been
        # asked repeatedly receive a small positive boost to confidence,
        # while brand‑new topics get a slight penalty.  The statistics are
        # stored in reports/topic_stats.json.  Errors in loading the stats
        # or computing the key are silently ignored.
        try:
            from pathlib import Path
            import json, re
            # Compute topic key: first two words of the normalized query
            q = orig_q.strip().lower()
            # Normalize: remove punctuation
            q_norm = re.sub(r"[^a-z0-9\s]", " ", q)
            q_norm = re.sub(r"\s+", " ", q_norm).strip()
            parts = q_norm.split()
            topic_key = " ".join(parts[:2]) if parts else ""
            # Load stats
            root = Path(__file__).resolve().parents[5]
            stats_path = root / "reports" / "topic_stats.json"
            fam_boost = 0.0
            if topic_key:
                stats: Dict[str, int] = {}
                if stats_path.exists():
                    try:
                        with open(stats_path, "r", encoding="utf-8") as fh:
                            stats = json.load(fh)
                    except Exception:
                        stats = {}
                count = int(stats.get(topic_key, 0))
                if count > 0:
                    # Each repetition adds 0.02, capped at +0.06
                    fam_boost = min(0.06, 0.02 * float(count))
                else:
                    # Slight penalty for unseen topics
                    fam_boost = -0.02
                # Adjust affect valence
                aff_val = float(aff_val) + fam_boost
        except Exception:
            # On any error, leave affect values unchanged
            pass

        # --- Domain confidence modulation ----------------------------------
        # Incorporate historical success rates for this domain (topic).  The
        # meta_confidence module records successes and failures of
        # previous answers.  A small adjustment based on that record is
        # applied to the affect valence so that domains where Maven has
        # performed well boost confidence and domains with poor history
        # reduce confidence.  Errors in loading the module or computing
        # the key are silently ignored.
        try:
            from brains.personal.memory import meta_confidence  # type: ignore
        except Exception:
            meta_confidence = None  # type: ignore
        if meta_confidence is not None:
            try:
                import re
                q = orig_q.strip().lower()
                # Normalize: remove non‑alphanumeric characters
                q_norm = re.sub(r"[^a-z0-9\s]", " ", q)
                q_norm = re.sub(r"\s+", " ", q_norm).strip()
                parts = q_norm.split()
                domain_key = " ".join(parts[:2]) if parts else ""
                if domain_key:
                    adj = meta_confidence.get_confidence(domain_key)
                    aff_val = float(aff_val) + float(adj)
            except Exception:
                pass

        # --- Dynamic confidence modulation ----------------------------------
        # Apply a global confidence adjustment based on recent success
        # statistics across all domains.  This uses the optional
        # dynamic_confidence module, which returns a small bias derived
        # from the mean of recent adjustments.  The bias is added to
        # affect valence (aff_val) to subtly shift overall confidence.
        try:
            # Import dynamic confidence helper; ignore if unavailable
            from brains.cognitive.reasoning.service.dynamic_confidence import compute_dynamic_confidence  # type: ignore
        except Exception:
            compute_dynamic_confidence = None  # type: ignore
        if compute_dynamic_confidence and meta_confidence is not None:
            try:
                # Gather adjustments from meta confidence stats
                stats = meta_confidence.get_stats(1000) or []
                values = []
                for d in stats:
                    try:
                        values.append(float(d.get("adjustment", 0)))
                    except Exception:
                        continue
                if values:
                    dyn = compute_dynamic_confidence(values)
                    aff_val = float(aff_val) + float(dyn)
            except Exception:
                pass

        # Determine if this input is a question by intent or punctuation.
        storable_type = str(proposed.get("storable_type", "")).upper() or ""
        is_question_intent = False
        if storable_type == "QUESTION":
            is_question_intent = True
        elif not storable_type:
            if _is_question_text(orig_q):
                is_question_intent = True

        # --------------------------------------------------------------------
        # Safety rules check.  Before proceeding with deeper reasoning, inspect
        # the query against developer‑defined safety rules.  These rules are
        # simple case‑insensitive substrings stored via the personal brain.
        # If any rule matches, we avoid returning a potentially inaccurate
        # answer.  Instead we respond with an undefined verdict and a
        # cautionary answer.  This catch‑all filter helps prevent
        # obviously false or harmful statements.  Errors in loading or
        # matching rules are silently ignored.
        try:
            from brains.personal.memory import safety_rules  # type: ignore[attr-defined]
        except Exception:
            safety_rules = None  # type: ignore
        if safety_rules is not None:
            try:
                patterns = safety_rules.get_rules()  # type: ignore[attr-defined]
                q_lower = str(orig_q).lower()
                for pattern in patterns:
                    if pattern and (pattern in q_lower):
                        ans = "I'm not sure that's correct. Let's revisit this question later."
                        conf_sf = 0.4
                        # Record safety filter event in telemetry
                        _update_telemetry("safety_filter")
                        return {
                            "ok": True,
                            "op": op,
                            "mid": mid,
                            "payload": {
                                "verdict": "UNKNOWN",
                                "mode": "SAFETY_FILTER",
                                "confidence": conf_sf,
                                "routing_order": {"target_bank": None, "action": None},
                                "supported_by": [],
                                "contradicted_by": [],
                                "answer": ans,
                                "weights_used": {"rule": "safety_filter_v1"}
                            }
                        }
            except Exception:
                pass

        # ----------------------------------------------------------------
        # Ethics rules check.  Similar to the safety filter above, inspect
        # the query against developer‑defined ethics rules stored in
        # ``reports/ethics_rules.json``.  These rules represent
        # case‑insensitive substrings that flag ethically questionable or
        # undesirable input.  If any match is found, return an
        # ``UNKNOWN`` verdict with a cautionary answer.  Failures in
        # loading or parsing the rules file are silently ignored.
        # ----------------------------------------------------------------
        # Ethics rules check.  Inspect the query against developer‑defined
        # ethics rules stored in ``reports/ethics_rules.json``.  This file may
        # contain either a list of simple patterns (backwards compatibility)
        # or a list of structured rule objects with ``pattern``, ``severity``
        # and ``action`` fields.  Structured rules allow differentiating
        # between hard blocks and softer warnings.  When a match is found
        # with a ``block`` action (or with the legacy unstructured format),
        # the question is blocked with a cautionary answer.  When a match
        # is found with a ``warn`` action, the system continues processing
        # but applies a small negative affect adjustment to reduce the
        # resulting confidence.  Any errors in loading or parsing the file
        # result in silently skipping this filter.
        try:
            root = REASONING_ROOT.parents[2]
            ethics_path = root / "reports" / "ethics_rules.json"
            if ethics_path.exists():
                with open(ethics_path, "r", encoding="utf-8") as f:
                    rules = json.load(f)
                q_lower = str(orig_q or "").lower()
                # Backwards compatible: if rules is a list of strings, convert
                # to structured rules with default block action
                if isinstance(rules, list) and rules and isinstance(rules[0], str):
                    rules = [{"pattern": p, "action": "block", "severity": "medium"} for p in rules]
                if isinstance(rules, list):
                    for rule in rules:
                        try:
                            patt = str(rule.get("pattern", "")).strip().lower()
                        except Exception:
                            patt = ""
                        if not patt:
                            continue
                        if patt in q_lower:
                            action = str(rule.get("action", "block")).lower()
                            if action == "warn":
                                # Apply a gentle negative adjustment to affect valence.
                                # This reduces the final confidence without blocking the
                                # question entirely.  Use a small penalty so as not
                                # to completely suppress plausible answers.
                                try:
                                    aff_val -= 0.05
                                except Exception:
                                    pass
                                # Record warn event
                                _update_telemetry("ethics_warn")
                                # Continue checking other patterns in case a block rule
                                # should be applied.
                                continue
                            # For block or unknown actions, return immediately with a
                            # cautionary answer.  Use severity to vary the confidence
                            # slightly; low severity yields a smaller penalty than high.
                            severity = str(rule.get("severity", "medium")).lower()
                            if severity == "low":
                                conf_penalty = 0.3
                            elif severity == "high":
                                conf_penalty = 0.5
                            else:
                                conf_penalty = 0.4
                            ans = "This query may raise ethical concerns. Let's discuss something else."
                            conf_ef = conf_penalty
                            # Record block event in telemetry
                            _update_telemetry("ethics_block")
                            return {
                                "ok": True,
                                "op": op,
                                "mid": mid,
                                "payload": {
                                    "verdict": "UNKNOWN",
                                    "mode": "ETHICS_FILTER",
                                    "confidence": conf_ef,
                                    "routing_order": {"target_bank": None, "action": None},
                                    "supported_by": [],
                                    "contradicted_by": [],
                                    "answer": ans,
                                    "weights_used": {"rule": "ethics_filter_v2"}
                                }
                            }
        except Exception:
            pass
        # Perform a common sense check on binary questions.  If the question
        # obviously contradicts basic knowledge (e.g. "Is Mars a country?"),
        # return a correction with high confidence and skip further reasoning.
        if is_question_intent:
            cs_res = _common_sense_check(orig_q)
            if cs_res:
                # Compose a corrective answer: clarify the true category of the entity.
                try:
                    # Capitalise the entity for the answer
                    ent = cs_res.get("entity", "").strip().title()
                    correct = cs_res.get("correct", "").strip()
                    wrong = cs_res.get("wrong", "").strip()
                    ans = f"No, {ent} is a {correct}, not a {wrong}."
                except Exception:
                    ans = "No, that is not correct."
                # High confidence with slight affect modulation
                try:
                    conf_cs = 0.95 + (aff_val * 0.05 + aff_arousal * 0.03)
                except Exception:
                    conf_cs = 0.95
                conf_cs = max(0.0, min(1.0, conf_cs))
                return {
                    "ok": True,
                    "op": op,
                    "mid": mid,
                    "payload": {
                        "verdict": "FALSE",
                        "mode": "COMMON_SENSE",
                        "confidence": conf_cs,
                        "routing_order": {"target_bank": None, "action": None},
                        "supported_by": [],
                        "contradicted_by": [],
                        "answer": ans,
                        "weights_used": {"rule": "common_sense_v1"}
                    }
                }

        # Commands and requests are not evaluated as facts and should skip storage.
        if storable_type in ("COMMAND", "REQUEST"):
            return {
                "ok": True,
                "op": op,
                "mid": mid,
                "payload": {
                    "verdict": "SKIP_STORAGE",
                    "mode": f"{storable_type}_INPUT",
                    "confidence": 0.0,
                    "routing_order": {"target_bank": None, "action": None},
                    "supported_by": [],
                    "contradicted_by": [],
                    "weights_used": {"rule": "intent_filter_v1"}
                }
            }
        # Emotion and opinion statements should be handled outside of the factual reasoner.
        if storable_type in ("EMOTION", "OPINION"):
            return {
                "ok": True,
                "op": op,
                "mid": mid,
                "payload": {
                    "verdict": "SKIP_STORAGE",
                    "mode": f"{storable_type}_INPUT",
                    "confidence": 0.0,
                    "routing_order": {"target_bank": None, "action": None},
                    "supported_by": [],
                    "contradicted_by": [],
                    "weights_used": {"rule": "intent_filter_v1"}
                }
            }
        # Inputs labelled as UNKNOWN (e.g. greetings like "hi", "hello") should not be
        # treated as factual statements even if evidence exists for the raw text.  Without
        # this guard, duplicate "hello" entries in memory could cause trivial greetings
        # to be accepted as facts.  When the storable_type is UNKNOWN, skip storage and
        # return an UNKNOWN verdict regardless of evidence.  This ensures chit‑chat
        # does not accumulate in memory.
        if storable_type == "UNKNOWN":
            return {
                "ok": True,
                "op": op,
                "mid": mid,
                "payload": {
                    "verdict": "SKIP_STORAGE",
                    "mode": "UNKNOWN_INPUT",
                    "confidence": 0.0,
                    "routing_order": {"target_bank": None, "action": None},
                    "supported_by": [],
                    "contradicted_by": [],
                    "weights_used": {"rule": "intent_filter_v1"}
                }
            }
        # If the original query is a question, treat this operation as answering the question.
        if is_question_intent:
            # ------------------------------------------------------------------
            # Knowledge graph lookup: attempt to answer simple definition
            # questions using the semantic memory.  Handle patterns like
            # "what is X" or "who is X".  If an answer is found, return it
            # immediately with high confidence.  This block avoids importlib
            # overhead by importing the module directly and falls back to
            # content when original_query is unavailable.  It also supports
            # inverse lookups (object → subject) to answer questions like
            # "What is the red planet?" when the fact stored is (mars, is, the red planet).
            try:
                # Import the knowledge graph.  If it does not exist, skip
                # lookup gracefully.  Synonym mappings are applied at
                # the API layer but are not used during direct lookup
                # here to avoid returning tautological answers (e.g. "the
                # red planet" → "the red planet").  Inverse lookups
                # handle synonym‐like phrasing by matching against
                # objects directly.
                from brains.personal.memory import knowledge_graph as kg_mod  # type: ignore
                import re as _re
                # Determine the question text: prefer original_query, fall back to content.
                qsource = orig_q.strip() if orig_q else str(content or "").strip()
                qnorm = qsource.lower()
                # Match "what is X" or "who is X" at the start of the question.
                mkg = _re.match(r"^(?:what|who)\s+is\s+(.+)", qnorm)
                if mkg:
                    subj = mkg.group(1).rstrip("?").strip()
                    if subj:
                        # Generate candidate subjects: the raw text and a version
                        # without leading articles.  We do not apply synonym
                        # mappings here to avoid confusing subject–object
                        # orientation.  Instead, inverse lookup handles
                        # synonym‐like phrasing by matching objects directly.
                        subj_norm = subj.lower().strip()
                        candidates = [subj_norm]
                        cand_strip = _re.sub(r"^(?:the|a|an)\s+", "", subj_norm).strip()
                        if cand_strip and cand_strip != subj_norm:
                            candidates.append(cand_strip)
                        kg_ans = None
                        # Direct lookup: subject → object.  For each
                        # candidate, attempt a direct fact lookup.  If the
                        # returned object matches the candidate itself
                        # (ignoring case and leading articles), treat it
                        # as tautological and continue to inverse lookup.
                        for cand in candidates:
                            if not cand:
                                continue
                            try:
                                res = kg_mod.query_fact(cand, "is")
                            except Exception:
                                res = None
                            if not res:
                                continue
                            # Normalise both candidate and answer for comparison
                            cand_norm = cand.lower().strip()
                            res_norm = str(res).lower().strip()
                            # Remove leading articles for comparison
                            import re as _re
                            cand_stripped = _re.sub(r"^(?:the|a|an)\s+", "", cand_norm).strip()
                            res_stripped = _re.sub(r"^(?:the|a|an)\s+", "", res_norm).strip()
                            # If the answer equals the candidate (after stripping), skip this result
                            if res_stripped == cand_stripped:
                                continue
                            kg_ans = res
                            break
                        # Inverse lookup: object → subject, with synonym support.  If no answer
                        # was found via direct lookup, search all facts for a record
                        # where the relation is "is" and the object matches the candidate.
                        # To support synonyms (e.g. "the red planet" → "mars"), both the
                        # candidate and record object are canonicalised via the synonym
                        # mapping before comparison.  Leading articles are also removed.
                        if not kg_ans:
                            try:
                                facts = kg_mod.list_facts(0)
                            except Exception:
                                facts = []
                            # Attempt to import the synonym module; if unavailable or
                            # mapping fails, canonicalisation will default to the
                            # lowercase stripped term.
                            try:
                                from brains.personal.memory import synonyms as syn_mod  # type: ignore
                            except Exception:
                                syn_mod = None  # type: ignore
                            import re as _re
                            for cand in candidates:
                                if not cand:
                                    continue
                                # Prepare the candidate: lower‑case and strip articles
                                cand_norm = str(cand).lower().strip()
                                cand_clean = _re.sub(r"^(?:the|a|an)\s+", "", cand_norm).strip()
                                # Canonicalise the candidate if a synonym mapping is available
                                if syn_mod:
                                    try:
                                        canon_cand = syn_mod.get_canonical(cand_clean)  # type: ignore
                                    except Exception:
                                        canon_cand = cand_clean
                                else:
                                    canon_cand = cand_clean
                                for rec in facts:
                                    try:
                                        if str(rec.get("relation", "")).strip().lower() != "is":
                                            continue
                                        obj_val = str(rec.get("object", "")).strip().lower()
                                        # Remove articles from the stored object
                                        obj_clean = _re.sub(r"^(?:the|a|an)\s+", "", obj_val).strip()
                                        # Canonicalise the stored object
                                        if syn_mod:
                                            try:
                                                canon_obj = syn_mod.get_canonical(obj_clean)  # type: ignore
                                            except Exception:
                                                canon_obj = obj_clean
                                        else:
                                            canon_obj = obj_clean
                                        if canon_obj == canon_cand:
                                            kg_ans = rec.get("subject")
                                            break
                                    except Exception:
                                        continue
                                if kg_ans:
                                    break
                        if kg_ans:
                            # Compute a confidence influenced by affect metrics.  The base
                            # confidence reflects the reliability of explicit facts.
                            try:
                                conf_kg = 0.88 + aff_val * 0.05 + aff_arousal * 0.03
                            except Exception:
                                conf_kg = 0.88
                            conf_kg = max(0.0, min(conf_kg, 1.0))
                            return {
                                "ok": True,
                                "op": op,
                                "mid": mid,
                                "payload": {
                                    "verdict": "TRUE",
                                    "mode": "KG_ANSWER",
                                    "confidence": conf_kg,
                                    "routing_order": {"target_bank": None, "action": None},
                                    "supported_by": [],
                                    "contradicted_by": [],
                                    "answer": kg_ans,
                                    "weights_used": {"rule": "knowledge_graph_v1"}
                                }
                            }

                        # If no direct or inverse match, attempt to derive an answer via knowledge graph inference.
                        # This uses stored inference rules (e.g. located_in + part_of -> located_in) to
                        # generate transitive facts such as (A located_in C) from (A located_in B, B part_of C).
                        # Only attempt inference when the question pattern resembles "where is X" or
                        # when the relation is implicitly "located_in" (what is X located in?).  We try
                        # matching any inferred fact whose subject matches the candidate term and
                        # relation is one of 'located_in' or 'part_of'.
                        if not kg_ans:
                            try:
                                # Run inference via the V2 rule engine.  If unavailable, fall back to
                                # the simple transitive closure provided by kg_mod.infer().
                                inf_results: list = []
                                try:
                                    # run_inference returns inferred facts based on custom rules
                                    inf_results = kg_mod.run_inference(10)  # type: ignore[attr-defined]
                                except Exception:
                                    # fallback to built‑in transitive inference on located_in/part_of
                                    try:
                                        inf_results = kg_mod.infer(10)  # type: ignore[attr-defined]
                                    except Exception:
                                        inf_results = []
                                if inf_results:
                                    import re as _re
                                    for cand in candidates:
                                        if not cand:
                                            continue
                                        cand_norm = cand.lower().strip()
                                        for rec in inf_results:
                                            try:
                                                subj_val = str(rec.get("subject", "")).strip().lower()
                                                rel_val = str(rec.get("relation", "")).strip().lower()
                                                obj_val = str(rec.get("object", "")).strip()
                                                # Check if this inferred fact matches our candidate subject and a relevant relation
                                                if subj_val == cand_norm and rel_val in {"located_in", "part_of"}:
                                                    kg_ans = obj_val
                                                    break
                                            except Exception:
                                                continue
                                        if kg_ans:
                                            break
                                if kg_ans:
                                    # Confidence for inferred answers is slightly lower than direct facts.
                                    try:
                                        conf_inf = 0.75 + aff_val * 0.05 + aff_arousal * 0.03
                                    except Exception:
                                        conf_inf = 0.75
                                    conf_inf = max(0.0, min(conf_inf, 1.0))
                                    return {
                                        "ok": True,
                                        "op": op,
                                        "mid": mid,
                                        "payload": {
                                            "verdict": "TRUE",
                                            "mode": "INFERRED",
                                            "confidence": conf_inf,
                                            "routing_order": {"target_bank": None, "action": None},
                                            "supported_by": [],
                                            "contradicted_by": [],
                                            "answer": kg_ans,
                                            "weights_used": {"rule": "knowledge_inference_v1"}
                                        }
                                    }
                            except Exception:
                                # Ignore inference errors silently
                                pass
            except Exception:
                # On any error during knowledge graph retrieval, silently continue
                pass
            # Prior knowledge: consult the cross‑episode QA memory to see if this
            # question has been answered in a previous run.  If a stored answer
            # exists, return it immediately with high confidence, bypassing
            # retrieval and heuristic guessing.
            stored_ans = _qa_memory_lookup(orig_q)
            if stored_ans:
                # Clamp confidence to a high value but account for affect modulation
                try:
                    conf_qa = 0.85 + aff_val * 0.05 + aff_arousal * 0.03
                except Exception:
                    conf_qa = 0.85
                conf_qa = max(0.0, min(conf_qa, 1.0))
                return {
                    "ok": True,
                    "op": op,
                    "mid": mid,
                    "payload": {
                        "verdict": "TRUE",
                        "mode": "KNOWN_ANSWER",
                        "confidence": conf_qa,
                        "routing_order": {"target_bank": None, "action": None},
                        "supported_by": [],
                        "contradicted_by": [],
                        "answer": stored_ans,
                        "weights_used": {"rule": "qa_memory_v1"}
                    }
                }
            # Look through provided evidence results to find a candidate answer
            evidence = payload.get("evidence") or {}
            results = (evidence.get("results") or []) if isinstance(evidence, dict) else []
            ans_record = None
            answer_text = None
            for it in results:
                if not isinstance(it, dict):
                    continue
                raw_content = str(it.get("content", "")).strip()
                if not raw_content:
                    continue
                # Attempt to parse JSON content (e.g. {"text": "...", "temperature": ...})
                parsed_text = None
                if raw_content.startswith("{") and raw_content.endswith("}"):
                    try:
                        data = json.loads(raw_content)
                        parsed_text = str(data.get("text", raw_content)).strip()
                    except Exception:
                        parsed_text = raw_content
                else:
                    parsed_text = raw_content
                # Skip if parsed text is empty or still looks like a question
                if not parsed_text or parsed_text.endswith("?"):
                    continue
                ans_record = it
                answer_text = parsed_text
                break
            if ans_record and answer_text:
                # Additional inference for yes/no membership questions.  When the
                # question begins with "Is X one of ..." and the retrieved
                # answer contains the subject, infer a simple affirmative.
                if is_question_intent:
                        try:
                            import re as _re
                            q_lower = (orig_q or "").strip().lower().rstrip("?")
                            # Match patterns like "is red one of the spectrum colors"
                            m = _re.match(r"^is\s+([a-z0-9\s\-]+?)\s+one\s+of\s+(?:the\s+)?(.+)$", q_lower)
                            if m:
                                subj = m.group(1).strip()
                                group = m.group(2).strip()
                                # Resolve synonyms to canonical form
                                try:
                                    from brains.personal.memory import synonyms as syn_mod  # type: ignore
                                    canon_subj = syn_mod.get_canonical(subj)  # type: ignore[attr-defined]
                                    syn_groups = syn_mod.list_groups()  # type: ignore[attr-defined]
                                    # List of synonym variants for the subject
                                    subj_syns = syn_groups.get(canon_subj, [canon_subj]) if syn_groups else [canon_subj]
                                except Exception:
                                    canon_subj = subj.lower()
                                    subj_syns = [canon_subj]
                                # If any variant of the subject appears in the answer, infer membership
                                try:
                                    ans_lower = answer_text.lower()
                                except Exception:
                                    ans_lower = answer_text
                                matched = False
                                for s in subj_syns:
                                    if s and s.lower() in ans_lower:
                                        matched = True
                                        break
                                if matched:
                                    # Compose a concise affirmative answer.  Capitalise the original subject
                                    subj_cap = subj.capitalize()
                                    # Strip trailing punctuation from group (e.g. "spectrum colors")
                                    group_clean = group.rstrip(".")
                                    answer_text = f"Yes, {subj_cap} is one of the {group_clean}."
                        except Exception:
                            pass
                # Use the stored confidence if present, otherwise default to 0.85
                try:
                    conf_val = float(ans_record.get("confidence", 0.85))
                except Exception:
                    conf_val = 0.85
                # Adjust confidence by affect valence.  Positive valence
                # slightly increases confidence, negative valence decreases it.
                try:
                    conf_val = conf_val + aff_val * 0.05 + aff_arousal * 0.03
                except Exception:
                    pass
                conf_val = max(0.0, min(conf_val, 1.0))
                return {
                    "ok": True,
                    "op": op,
                    "mid": mid,
                    "payload": {
                        "verdict": "TRUE",
                        "mode": "ANSWERED",
                        "confidence": conf_val,
                        "routing_order": {"target_bank": None, "action": None},
                        "supported_by": [ans_record.get("id")] if ans_record.get("id") else [],
                        "contradicted_by": [],
                        "answer": answer_text,
                        "answer_source_id": ans_record.get("id"),
                        "weights_used": {"rule": "question_answer_v1"}
                    }
                }
            # If no direct answer found, attempt an educated guess using heuristics
            guess = _educated_guess_for_question(orig_q)
            if guess:
                # Educated guesses are presented with moderate confidence and marked as THEORY
                return {
                    "ok": True,
                    "op": op,
                    "mid": mid,
                    "payload": {
                        "verdict": "THEORY",
                        "mode": "EDUCATED_GUESS",
                        "confidence": 0.6,
                        "routing_order": {"target_bank": None, "action": None},
                        "supported_by": [],
                        "contradicted_by": [],
                        "answer": guess,
                        "weights_used": {"rule": "educated_guess_v1"}
                    }
                }

            # As a fallback, attempt to evaluate the question as a logical or mathematical expression.
            # This leverages the agent's System‑2 tools for precise computation when possible.
            expr = orig_q or content
            expr = str(expr or "").strip().rstrip("?")
            # Preprocess expressions to remove common question prefixes so that
            # boolean and arithmetic evaluation can operate on the core
            # expression.  This allows inputs like "What is 2+2?" or
            # "Compute true and false" to be handled by the appropriate tool.
            try:
                import re
                # Regex captures variations of question phrases followed by the expression
                m = re.match(r"^(?:what(?:'s| is)|calculate|compute|evaluate|solve)\s+(.*)", expr, re.IGNORECASE)
                if m:
                    expr = m.group(1).strip()
            except Exception:
                pass
            # Lowercase copy used for keyword detection
            try:
                lower_expr = expr.lower()
            except Exception:
                lower_expr = expr
            answered_by_tool = False
            answer_val: Any = None
            tool_rule = None
            # Heuristic: if boolean keywords or operators are present, use the logic tool
            try:
                # Look for explicit boolean literals or logical operators (with surrounding spaces)
                if any(w in lower_expr for w in ["true", "false", " and ", " or ", "not "]):
                    import importlib
                    logic_mod = importlib.import_module("brains.agent.tools.logic_tool")
                    logic_resp = logic_mod.service_api({"op": "EVAL", "payload": {"expression": expr}})
                    if logic_resp.get("ok", False):
                        answer_val = logic_resp.get("payload", {}).get("result")
                        answered_by_tool = True
                        tool_rule = "logic_tool_v1"
            except Exception:
                pass
            # If boolean evaluation didn't apply or failed, try arithmetic evaluation
            if not answered_by_tool:
                try:
                    has_digit = any(ch.isdigit() for ch in expr)
                except Exception:
                    has_digit = False
                # Check for math operators; require at least one digit and an operator to reduce false positives
                has_op = any(op in expr for op in ["+", "-", "*", "/", "%", "**"])
                if has_digit and has_op:
                    try:
                        import importlib
                        math_mod = importlib.import_module("brains.agent.tools.math_tool")
                        math_resp = math_mod.service_api({"op": "CALC", "payload": {"expression": expr}})
                        if math_resp.get("ok", False):
                            answer_val = math_resp.get("payload", {}).get("result")
                            answered_by_tool = True
                            tool_rule = "math_tool_v1"
                    except Exception:
                        pass
            if answered_by_tool:
                # When a tool produces a result, treat it as a confident answer.
                try:
                    conf_tool = 0.9 + (aff_val * 0.05 + aff_arousal * 0.03)
                except Exception:
                    conf_tool = 0.9
                conf_tool = max(0.0, min(1.0, conf_tool))
                return {
                    "ok": True,
                    "op": op,
                    "mid": mid,
                    "payload": {
                        "verdict": "TRUE",
                        "mode": "ANSWERED",
                        "confidence": conf_tool,
                        "routing_order": {"target_bank": None, "action": None},
                        "supported_by": [],
                        "contradicted_by": [],
                        "answer": str(answer_val),
                        "weights_used": {"rule": tool_rule or "system2_tool_v1"}
                    }
                }

            # Otherwise, no answer available
            return {
                "ok": True,
                "op": op,
                "mid": mid,
                "payload": {
                    "verdict": "UNANSWERED",
                    "mode": "QUESTION_INPUT",
                    "confidence": 0.0,
                    "routing_order": {"target_bank": None, "action": None},
                    "supported_by": [],
                    "contradicted_by": [],
                    "weights_used": {"rule": "question_answer_v1"}
                }
            }

        # --- Primitive safeguard: questions are not facts ---
        if _is_question_text(content):
            return {
                "ok": True,
                "op": op,
                "mid": mid,
                "payload": {
                    "verdict": "UNANSWERED",
                    "mode": "QUESTION_INPUT",
                    "confidence": 0.0,
                    "routing_order": {"target_bank": None, "action": None},
                    "supported_by": [],
                    "contradicted_by": [],
                    "weights_used": {"rule": "primitive_reason_v2"}
                }
            }
        # Weighted confidence calculation for factual statements.  Begin by scoring
        # the proposed fact against any retrieved evidence.  This helper returns
        # 0.8 for a direct match and 0.4 for no match.  Using the evidence score
        # as the base ensures that statements without supporting evidence are
        # treated conservatively (UNKNOWN) rather than being automatically
        # labelled as theories.
        evidence = payload.get("evidence") or {}
        conf = _score_evidence(proposed, evidence)
        # Apply a penalty for speculative or hedging language supplied by callers
        try:
            pen = float(proposed.get("confidence_penalty", 0.0))
        except Exception:
            pen = 0.0
        conf -= pen
        # Apply affect adjustment: valence and arousal nudge the confidence up
        # or down slightly.  Positive values raise confidence and negative
        # values lower it.
        try:
            conf = conf + aff_val * 0.05 + aff_arousal * 0.03
        except Exception:
            pass
        # Track supporting or contradicting evidence for provenance
        supported_by: List[str] = []
        contradicted_by: List[str] = []
        # Incorporate evidence: matching records slightly boost confidence, contradictions reduce it
        try:
            for it in (evidence.get("results") or []):
                if not isinstance(it, dict):
                    continue
                c = str(it.get("content", "")).strip().lower()
                proposed_c = str(proposed.get("content", "")).strip().lower()
                record_type = str(it.get("type", "")).lower()
                if c and (proposed_c == c or proposed_c in c or c in proposed_c):
                    conf += 0.05
                    rec_id = it.get("id")
                    if rec_id:
                        supported_by.append(rec_id)
                elif record_type == "contradiction":
                    conf -= 0.1
                    rec_id = it.get("id")
                    if rec_id:
                        contradicted_by.append(rec_id)
        except Exception:
            pass
        # Adjust confidence based on recent success rate (learned bias).  We use
        # the reasoning brain's own STM as the root for computing the success
        # average.  A modest adjustment (±0.15) nudges the confidence toward
        # better performance without dominating the evidence score.
        from api.memory import compute_success_average  # type: ignore
        try:
            learned = compute_success_average(REASONING_ROOT, n=50)
        except Exception:
            learned = 0.0
        conf += 0.15 * learned
        # Clamp confidence to the valid range [0.0, 1.0]
        if conf < 0.0:
            conf = 0.0
        if conf > 1.0:
            conf = 1.0
        # Determine verdict based on dynamically adjusted thresholds.  The true
        # and theory thresholds are biased by the affect metrics: positive
        # valence and high arousal lower the thresholds (faster acceptance),
        # negative valence raises them (cautious acceptance).  Limits ensure
        # thresholds remain within reasonable bounds.
        try:
            adjust = 0.05 * aff_val + 0.03 * aff_arousal
        except Exception:
            adjust = 0.0
        true_threshold = 0.85 - adjust
        theory_threshold = 0.70 - adjust
        # Clamp thresholds to sensible ranges
        if true_threshold < 0.60:
            true_threshold = 0.60
        if true_threshold > 0.90:
            true_threshold = 0.90
        if theory_threshold < 0.50:
            theory_threshold = 0.50
        if theory_threshold > 0.85:
            theory_threshold = 0.85
        if conf >= true_threshold:
            verdict = "TRUE"
            mode = "VERIFIED"
        elif conf >= theory_threshold:
            verdict = "THEORY"
            mode = "EDUCATED_GUESS"
        else:
            verdict = "UNKNOWN"
            mode = "NO_EVIDENCE"
        # If verdict is unknown, request a targeted memory search via the message bus.
        if verdict == "UNKNOWN":
            try:
                # Import send lazily to avoid circular imports.
                from brains.cognitive.message_bus import send as _mb_send  # type: ignore
                # Construct simple domain hints from the question or content.
                hints: List[str] = []
                try:
                    q_text = str(orig_q or content or "").lower().split()
                    for w in q_text:
                        # Use alphabetic tokens as domain hints (e.g. keywords)
                        if w.isalpha():
                            hints.append(w)
                            if len(hints) >= 2:
                                break
                except Exception:
                    hints = []
                _mb_send({
                    "from": "reasoning",
                    "to": "memory",
                    "type": "SEARCH_REQUEST",
                    "domains": hints or ["general"],
                    "confidence_threshold": 0.7,
                })
            except Exception:
                # Silently ignore message bus failures
                pass
        # Determine routing order: only store TRUE facts into domain banks.
        route_bank = _route_for(conf)
        routing_order = {
            "target_bank": route_bank,
            "action": "STORE" if verdict == "TRUE" else "SKIP"
        }
        # Produce a simple reasoning trace explaining how the confidence was evaluated.
        # In addition to the generic message, append a note when a self‑identity
        # query yields no evidence.  This transparency helps users understand
        # why an answer may be unknown.  See upgrade notes on reasoning
        # transparency for more context.
        try:
            trace_msg = (
                f"Evaluated confidence {conf:.2f} against thresholds (TRUE≥{true_threshold:.2f}, THEORY≥{theory_threshold:.2f})."
            )
        except Exception:
            trace_msg = "Confidence evaluation details unavailable."
        # Append introspective explanation for self‑identity queries when
        # confidence is insufficient to produce a factual answer.  Detect
        # identity queries by looking for common phrases in the original
        # question.  Only append the note when the verdict is UNKNOWN.
        try:
            if verdict == "UNKNOWN":
                q_lower = str(orig_q or "").strip().lower()
                identity_patterns = [
                    "who are you",
                    "what is your name",
                    "what's your name",
                    "tell me about yourself",
                    "who you are",
                    "are you maven"
                ]
                for pat in identity_patterns:
                    if pat in q_lower:
                        trace_msg += " No self-definition found in memory."
                        break
        except Exception:
            # Ignore any errors when adding introspective notes
            pass
        return {
            "ok": True,
            "op": op,
            "mid": mid,
            "payload": {
                "verdict": verdict,
                "mode": mode,
                "confidence": conf,
                "routing_order": routing_order,
                "supported_by": supported_by,
                "contradicted_by": contradicted_by,
                "weights_used": {"rule": "primitive_reason_v2"},
                "reasoning_trace": trace_msg,
            }
        }
    # Health endpoint just returns a status ok
    if op == "HEALTH":
        return {"ok": True, "op": op, "mid": mid, "payload": {"status": "ok"}}
    return {"ok": False, "op": op, "mid": mid, "error": {"code": "UNSUPPORTED_OP", "message": op}}

# -----------------------------------------------------------------------------
# Attention bid interface
#
# The reasoning brain can request attention from the integrator by
# providing a bid via ``bid_for_attention``.  This function examines the
# current pipeline context and determines how urgently reasoning
# resources are needed.  It prioritises situations where contradictions
# need resolving or where a question lacks a clear answer but related
# facts are available.  For general questions it bids moderately, and
# otherwise returns a low default bid.  Errors result in a safe low
# priority.
def bid_for_attention(ctx: Dict[str, Any]) -> Dict[str, Any]:
    try:
        # Inspect reasoning verdict if it exists
        stage8 = ctx.get("stage_8_validation") or {}
        verdict = str(stage8.get("verdict", "")).upper()
        mode = str(stage8.get("mode", "")).upper()

        # Skip reasoning for PREFERENCE and relationship queries - these don't need validation
        if verdict == "PREFERENCE" or mode in {"PREFERENCE_QUERY", "RELATIONSHIP_QUERY"}:
            return {
                "brain_name": "reasoning",
                "priority": 0.05,
                "reason": "preference_or_relationship_skip",
                "evidence": {},
            }

        # High priority if contradictions have been detected.  We treat
        # ``CONTRADICTED_EVIDENCE`` mode as a proxy for contradictions or
        # a THEORY verdict to indicate disputed evidence.
        if mode == "CONTRADICTED_EVIDENCE" or verdict == "THEORY":
            return {
                "brain_name": "reasoning",
                "priority": 0.95,
                "reason": "contradiction_detected",
                "evidence": {},
            }
        # Determine if the current input is a question
        lang_info = ctx.get("stage_3_language", {}) or {}
        st_type = str(
            lang_info.get("type")
            or lang_info.get("storable_type")
            or lang_info.get("intent")
            or ""
        ).upper()
        # Check if memory retrieval found any results
        mem_results = (ctx.get("stage_2R_memory") or {}).get("results", [])
        has_related = bool(mem_results)
        # When the verdict is UNKNOWN or UNANSWERED and there are related facts
        # available, reasoning can attempt an inference.  Bid moderately high.
        if verdict in {"UNANSWERED", "UNKNOWN"} and has_related:
            return {
                "brain_name": "reasoning",
                "priority": 0.75,
                "reason": "inference_possible",
                "evidence": {},
            }
        # For general questions bid medium to analyse the question
        if st_type == "QUESTION":
            return {
                "brain_name": "reasoning",
                "priority": 0.50,
                "reason": "question_analysis",
                "evidence": {},
            }
        # Low default priority for all other cases
        return {
            "brain_name": "reasoning",
            "priority": 0.15,
            "reason": "default",
            "evidence": {},
        }
    except Exception:
        return {
            "brain_name": "reasoning",
            "priority": 0.15,
            "reason": "default",
            "evidence": {},
        }

# Ensure the reasoning brain exposes a `handle` entry point
try:
    handle = service_api  # type: ignore[assignment]
    service_api = handle  # type: ignore[assignment]
except Exception:
    pass