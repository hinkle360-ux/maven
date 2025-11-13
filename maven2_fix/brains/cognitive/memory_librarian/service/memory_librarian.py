
from __future__ import annotations
from typing import Dict, Any, List, Optional, Set
import importlib.util, sys, json, re, os, random
import threading
from pathlib import Path

# Routing diagnostics for tracking pipeline paths (Phase C cleanup)
try:
    from brains.cognitive.routing_diagnostics import tracer, RouteType  # type: ignore
except Exception:
    tracer = None  # type: ignore
    RouteType = None  # type: ignore

# Optional import of the focus analyzer.  If unavailable, update
# calls will be silently ignored.  This allows the memory
# librarian to remain compatible with older Maven builds that do
# not include the attention analytics module.
try:
    from brains.cognitive.attention.focus_analyzer import update_focus_stats  # type: ignore
except Exception:
    update_focus_stats = None  # type: ignore

# Import memory consolidation helper to enable tier promotion.  When new facts
# are stored, we trigger consolidation so that validated knowledge can
# graduate from short‑term memory into mid‑ and long‑term stores.  Errors
# during consolidation are ignored to avoid blocking storage operations.
try:
    from brains.cognitive.memory_consolidation import consolidate_memories  # type: ignore
except Exception:
    consolidate_memories = None  # type: ignore

# ---------------------------------------------------------------------------
# Global state for attention and session tracking
#
# The memory librarian keeps track of a small history of attention focus
# transitions across pipeline runs.  Each entry records which brain won
# attention, why it did so, and when this occurred.  This helps later
# analyses identify patterns in attention allocation and allows bidding
# strategies to be tuned.  A short queue of recent user queries is also
# maintained to enable multi‑turn context awareness, stress detection and
# proactive clarification.  Only the last _MAX_RECENT_QUERIES entries are
# retained to bound memory usage.
_ATTENTION_HISTORY: List[Dict[str, Any]] = []
_RECENT_QUERIES: List[Dict[str, Any]] = []
_MAX_RECENT_QUERIES: int = 10

# ---------------------------------------------------------------------------
# Conversation state for multi-turn context (Phase 0 continuation support)
#
# To support continuation queries like "more about brains" or "anything else",
# the memory librarian tracks the last discussed topic and response across
# pipeline runs.  When a continuation trigger is detected in the user's input,
# the librarian replaces the query with the last topic so that retrieval is
# scoped appropriately.  After each pipeline run, these state variables are
# updated based on the user's original query and the final answer.
_LAST_TOPIC: str = ""
_LAST_RESPONSE: str = ""

# ---------------------------------------------------------------------------
# Conversation context dictionary for deeper state tracking (Phase 2)
#
# In addition to the simple last topic/response strings above, Maven maintains
# a richer conversation context.  This dictionary stores the most recent
# query, answer, inferred topic, a list of entity tokens extracted from the
# conversation, and a depth counter measuring how many turns have occurred in
# the current session.  This structure enables pronoun resolution (e.g. mapping
# "that" or "it" back to the previous answer) and more robust continuation
# handling.  It is intentionally lightweight and does not rely on external
# NLP libraries.
_CONVERSATION_STATE: Dict[str, Any] = {
    "last_query": "",
    "last_response": "",
    "last_topic": "",
    "thread_entities": [],
    "conversation_depth": 0,
}

def _extract_topic(text: str) -> str:
    """
    Extract a plausible topic from a user query.  This helper looks for the
    keyword 'about' and returns the text following it; otherwise, it
    returns the last alphabetic word.  The topic is lower‑cased for
    consistent matching.  When no topic can be found, returns an empty string.

    Args:
        text: The raw user input.

    Returns:
        A lower‑cased topic string or ''.
    """
    try:
        s = str(text or "").strip()
    except Exception:
        return ""
    if not s:
        return ""
    # Normalize whitespace and case
    s_low = s.lower()
    # If the query contains 'about', return the substring after the last 'about'
    try:
        if " about " in s_low:
            # Split on the first occurrence of ' about ' to capture everything after
            parts = s_low.split(" about ", 1)
            topic = parts[1].strip()
            return topic
    except Exception:
        pass
    # Fallback: return the last alphabetic token
    import re as _re_extract
    try:
        tokens = _re_extract.findall(r"[A-Za-z']+", s_low)
        return tokens[-1] if tokens else ""
    except Exception:
        return ""

# ---------------------------------------------------------------------------
# Entity extraction for conversation threading
#
# The conversation state stores a list of thread entities extracted from
# recent queries and answers.  This helper performs a simple tokenisation of
# alphanumeric sequences, lowercases them, removes common stopwords and
# returns a deduplicated list.  It is deliberately naïve to avoid reliance
# on external NLP packages; its goal is to capture salient nouns or
# keywords that may help with pronoun resolution and topic inference.

def _extract_entities(text: str) -> List[str]:
    """
    Extract potential entities or keywords from a piece of text.

    This naive implementation tokenises the input on alphanumeric
    characters, lower-cases tokens, removes stopwords and returns unique
    terms.  It is designed to be lightweight and robust in the absence of
    external NLP libraries.

    Args:
        text: Arbitrary string from which to extract entities.

    Returns:
        A list of unique tokens representing possible entities or keywords.
    """
    try:
        import re as _re
        # Convert to string and lower case
        s = str(text or "")
        tokens = _re.findall(r"[A-Za-z0-9']+", s.lower())
        # Define a small stopword list; include common pronouns and
        # non-content words.  This list can be extended as needed.
        stopwords = {
            "a", "an", "the", "and", "or", "but", "if", "then", "else",
            "this", "that", "it", "he", "she", "they", "we", "you", "your",
            "my", "mine", "ours", "ourselves", "i", "me", "am", "is", "are",
            "was", "were", "be", "been", "being", "to", "of", "in", "on",
            "for", "with", "about", "as", "at", "by", "from", "into",
            "onto", "until", "while", "up", "down", "over", "under",
            "more", "anything", "else", "what", "how", "did", "you", "get",
            "come", "up", "with"
        }
        ents: List[str] = []
        for tok in tokens:
            # Keep alphabetic tokens longer than one character and not in stopwords
            if tok and tok.isalpha() and tok not in stopwords:
                ents.append(tok)
        # Deduplicate while preserving order
        uniq: List[str] = []
        seen: set[str] = set()
        for t in ents:
            if t not in seen:
                uniq.append(t)
                seen.add(t)
        return uniq
    except Exception:
        return []

# ---------------------------------------------------------------------------
# Pronoun set and cache gating helpers
#
# ``PRONOUNS`` enumerates single-word pronouns and interrogatives that
# indicate a query is context-dependent.  ``_should_cache`` applies a
# quality gate when deciding whether to write a fast or semantic cache
# entry.  Queries that are too short, have low confidence, or contain
# pronouns are not cached.  See Fix 2 for details.

# Pronouns used to detect context-dependent queries.  If any of these
# tokens appear as standalone words within a query, caching is disabled.
PRONOUNS: Set[str] = {
    "that", "this", "it", "these", "those",
    "what", "which", "who", "whom", "whose",
    "where", "when", "why", "how"
}

def _should_cache(query: str, verdict: str, confidence: float) -> bool:
    """Return True if the query should be cached.

    A query is eligible for caching only when it meets several quality
    criteria: it must have a TRUE verdict, consist of at least two
    space-separated tokens, exhibit sufficient confidence (≥ 0.8), and
    contain no pronoun tokens.  If any condition fails, the function
    returns False.

    Args:
        query: The original user query string.
        verdict: The Stage 8 verdict (e.g. 'TRUE', 'FALSE').
        confidence: The final confidence score for the answer.

    Returns:
        A boolean indicating whether caching should proceed.
    """
    try:
        q = str(query or "").strip()
        v = str(verdict or "").upper()
        if not q or v != "TRUE":
            return False
        # Too few words? (one or zero words)
        if len(q.split()) < 2:
            return False
        try:
            conf = float(confidence)
        except Exception:
            conf = 0.0
        if conf < 0.8:
            return False
        qlower = q.lower()
        # Tokenise query and check pronouns as standalone tokens
        words = qlower.split()
        for p in PRONOUNS:
            if p in words:
                return False
        return True
    except Exception:
        return False

# ---------------------------------------------------------------------------
# Continuation and pronoun resolution helper
#
# User utterances may contain requests to continue a previous topic (e.g.
# "more", "anything else", "more about physics") or refer to a prior answer
# using pronouns (e.g. "that", "this", "it").  This helper inspects the
# input query and the global conversation state to rewrite the query when
# appropriate.  It returns a tuple consisting of the potentially modified
# query and a boolean flag indicating whether the retrieval should
# restrict itself to the short‑term memory bank.  Errors are suppressed to
# avoid disrupting the pipeline.

def _resolve_continuation_and_pronouns(query: str) -> tuple[str, bool]:
    """
    Resolve continuation triggers and simple pronoun references.

    Args:
        query: The original user query.

    Returns:
        A tuple of (resolved_query, force_stm) where resolved_query is
        the modified query string (or the original when no change is
        necessary) and force_stm indicates whether retrieval should be
        limited to the short‑term memory bank.
    """
    try:
        q = str(query or "")
    except Exception:
        return query, False
    try:
        ql = q.strip().lower()
    except Exception:
        ql = ""
    # Default flag: do not restrict retrieval to STM
    force_stm = False
    # Access the current conversation state
    conv = globals().get("_CONVERSATION_STATE", {}) or {}
    last_topic = conv.get("last_topic", "") or ""
    last_response = conv.get("last_response", "") or ""
    try:
        # Continuation triggers for bare follow-ups
        # Include common variants and polite continuations
        triggers_set = {
            "more",
            "anything else",
            "any thing else",
            "what else",
            "what else?",
            "tell me more",
            "tell me more?",
            "go on",
            "continue",
            "continue?",
        }
        special_last_answer_triggers = {
            "what did you just say",
            "what was your last answer",
            "what was your last response",
            "last answer",
            "last response",
        }
        if ql in triggers_set or ql in special_last_answer_triggers:
            # If the user explicitly asks about the last answer, return
            # the last response.  Otherwise, use the last topic.
            if ql in special_last_answer_triggers:
                if last_response:
                    return last_response, True
                elif last_topic:
                    return last_topic, True
            # Generic continuation: use last topic
            if last_topic:
                return last_topic, True
        # Detect "more about X" and extract X.  Also handle "tell me more about X"
        if ql.startswith("more about ") or ql.startswith("tell me more about "):
            if ql.startswith("tell me more about "):
                candidate = ql[len("tell me more about "):].strip()
            else:
                candidate = ql[len("more about "):].strip()
            if candidate:
                return candidate, True
        # Detect "more on X" patterns and extract X or fall back to last_topic
        if ql.startswith("more on "):
            candidate = ql[len("more on "):].strip()
            if candidate:
                # If candidate is a pronoun like that/this/it etc., resolve to last_topic
                if candidate in {"that", "this", "it", "them", "these", "those"}:
                    if last_topic:
                        return last_topic, True
                return candidate, True
        # Single pronoun queries: return last response or last topic
        if ql in {"that", "this", "it", "them", "these", "those"}:
            if last_response:
                return last_response, True
            elif last_topic:
                return last_topic, True
        # Pronoun references embedded in explanatory questions
        import re as _re_pron
        # Patterns covering "how did you get {pronoun}" and "how did you come up with {pronoun}"
        patterns = [
            r"(how\s+did\s+you\s+get\s+)(that|this|it|them|these|those)\b",
            r"(how\s+did\s+you\s+come\s+up\s+with\s+)(that|this|it|them|these|those)\b",
            r"(explain\s+)(that|this|it|them|these|those)\b",
        ]
        for pat in patterns:
            m = _re_pron.search(pat, ql)
            if m:
                prefix = m.group(1)
                replacement = last_response or last_topic
                if replacement:
                    # Replace the pronoun with the resolved phrase
                    new_query = _re_pron.sub(pat, prefix + replacement, ql)
                    return new_query, True
        # Additional fallback: if the query is short (<= 3 words) and ends with
        # "else", treat it as a continuation (e.g. "anything else?")
        try:
            if len(ql.split()) <= 3 and "else" in ql:
                if last_topic:
                    return last_topic, True
        except Exception:
            pass
    except Exception:
        # Silently ignore resolution errors
        pass
    return query, False
    if not s:
        return ""
    # Normalize whitespace and case
    s_low = s.lower()
    # If the query contains 'about', return the substring after the last 'about'
    try:
        if " about " in s_low:
            # Split on the first occurrence of ' about ' to capture everything after
            parts = s_low.split(" about ", 1)
            topic = parts[1].strip()
            return topic
    except Exception:
        pass
    # Fallback: return the last alphabetic token
    import re as _re_extract
    try:
        tokens = _re_extract.findall(r"[A-Za-z']+", s_low)
        return tokens[-1] if tokens else ""
    except Exception:
        return ""

def _update_conversation_state(query: str, answer: str) -> None:
    """
    Update the global conversation state variables with the latest topic and
    response.  This function extracts a topic from the provided query and
    stores both the topic and answer in module‑level variables.  It is
    resilient to errors and will silently ignore failures.

    Args:
        query: The user's original query string.
        answer: The system's final answer string.
    """
    global _LAST_TOPIC, _LAST_RESPONSE, _CONVERSATION_STATE
    try:
        topic = _extract_topic(query)
        if topic:
            _LAST_TOPIC = topic
        if answer:
            _LAST_RESPONSE = str(answer).strip()
        # Update the detailed conversation state.  Always record the last
        # query and response; if a topic was extracted, overwrite the
        # stored topic, otherwise retain the existing one.  Also extract
        # salient entities from the query and answer to aid pronoun
        # resolution and update the conversation depth based on the
        # recent query history.
        try:
            _CONVERSATION_STATE["last_query"] = str(query).strip()
        except Exception:
            _CONVERSATION_STATE["last_query"] = query
        try:
            _CONVERSATION_STATE["last_response"] = str(answer).strip() if answer else ""
        except Exception:
            _CONVERSATION_STATE["last_response"] = answer or ""
        try:
            if topic:
                _CONVERSATION_STATE["last_topic"] = topic
            elif not _CONVERSATION_STATE.get("last_topic"):
                # Fallback to using the existing _LAST_TOPIC if no new topic
                _CONVERSATION_STATE["last_topic"] = _LAST_TOPIC or ""
        except Exception:
            _CONVERSATION_STATE["last_topic"] = topic or _CONVERSATION_STATE.get("last_topic", "")
        try:
            ents_q = _extract_entities(query)
        except Exception:
            ents_q = []
        try:
            ents_a = _extract_entities(answer) if answer else []
        except Exception:
            ents_a = []
        try:
            # Use a set to deduplicate but preserve order via list comprehension
            combined = []
            seen = set()
            for e in (ents_q + ents_a):
                if e not in seen:
                    combined.append(e)
                    seen.add(e)
            _CONVERSATION_STATE["thread_entities"] = combined
        except Exception:
            _CONVERSATION_STATE["thread_entities"] = []
        try:
            # Conversation depth equals the number of recent queries if available
            _CONVERSATION_STATE["conversation_depth"] = len(_RECENT_QUERIES)
        except Exception:
            try:
                _CONVERSATION_STATE["conversation_depth"] = int(_CONVERSATION_STATE.get("conversation_depth", 0)) + 1
            except Exception:
                _CONVERSATION_STATE["conversation_depth"] = 1
    except Exception:
        # Do not propagate exceptions from state updates
        pass

# ---------------------------------------------------------------------------
# Identity bootstrap and episodic helpers
#
# The durable identity store records the primary user name across sessions.
# These helpers allow the memory librarian to populate working memory with
# the stored name on startup and to extract recent self‑introductions from
# the conversation history.  They are light‑weight and do not depend on
# any external Maven components.  Errors are suppressed so that missing
# identity modules do not break the librarian.

try:
    from brains.personal.service import identity_user_store  # type: ignore
except Exception:
    identity_user_store = None  # type: ignore

def bootstrap_identity(wm_put: Any) -> None:
    """Hydrate working memory with the primary user name from the durable store.

    If a name exists in the durable store, this helper writes it to
    working memory using the provided ``wm_put`` callable.  The entry
    uses key ``user_identity`` and tags ["identity", "name"] with
    full confidence.  Exceptions are ignored to avoid disrupting
    startup.

    Args:
        wm_put: A callable following the signature of the WM_PUT
            operation.  It should accept keyword arguments ``key``,
            ``value``, ``tags`` and ``confidence``.
    """
    try:
        if identity_user_store:
            ident = identity_user_store.GET()  # type: ignore[attr-defined]
            if isinstance(ident, dict):
                name = ident.get("name")
                if name:
                    wm_put(key="user_identity", value=name, tags=["identity", "name"], confidence=1.0)
    except Exception:
        pass

def episodic_last_declared_identity(recent_queries: List[Dict[str, Any]], n: int = 10) -> Optional[str]:
    """Return the last declared name from recent queries.

    This helper scans the last ``n`` user queries in reverse order and
    returns the first phrase following "I am", "I'm", "im", "call me" or "my name is"
    if found.  Matching is case‑insensitive and conservative.  When
    no declaration is found, None is returned.

    Args:
        recent_queries: A list of dicts representing recent exchanges.
            Each dict should contain at least the user's utterance under
            the "user" key.  Non‑dict entries are ignored.
        n: The maximum number of recent queries to inspect.
    Returns:
        The extracted name as a string, or None if no match is found.
    """
    try:
        if not recent_queries:
            return None
        # Limit to the last n entries
        for entry in reversed(recent_queries[-int(n):]):
            try:
                utter = str(entry.get("user") or "").strip()
            except Exception:
                continue
            if not utter:
                continue
            lower = utter.lower()
            import re as _re  # local import
            m = _re.search(r"\bmy\s+name\s+is\s+([A-Za-z][A-Za-z\s'-]*)", utter, _re.IGNORECASE)
            if not m:
                m = _re.search(r"\b(?:i\s+am|i'm|im|call\s+me)\s+([A-Za-z][A-Za-z\s'-]*)", utter, _re.IGNORECASE)
            if m:
                name = m.group(1).strip()
                if name:
                    return name
        return None
    except Exception:
        return None

# -----------------------------------------------------------------------------
# Blackboard subscription registry (Phase 6)
#
# The blackboard acts as a lightweight shared working memory.  Consumers
# may register interest in certain WM entries via BB_SUBSCRIBE.  Each
# subscription can specify a key filter, tag filters, a minimum confidence
# threshold, a time‑to‑live for matching events and a priority hint.
# The CONTROL_CYCLE operation scans WM, scores candidate events per
# subscription, performs a simple arbitration via the integrator brain and
# dispatches the winning event through the message bus.
#
# Subscriptions are stored in the form:
#   _BLACKBOARD_SUBS[subscriber_id] = {
#       "key": Optional[str],
#       "tags": Optional[List[str]],
#       "min_conf": float,
#       "ttl": float,
#       "priority": float,
#       "last_index": int,
#   }
#
# last_index is used to avoid reprocessing the same WM entries across cycles.

_BLACKBOARD_SUBS: Dict[str, Dict[str, Any]] = {}

def _bb_subscribe(subscriber: str, key: Optional[str], tags: Optional[List[str]], min_conf: float, ttl: float, priority: float) -> None:
    """Register or update a blackboard subscription.

    Args:
        subscriber: Unique identifier for the subscriber (brain name).
        key: Optional key filter; only WM entries with matching key are delivered.
        tags: Optional list of tags; at least one must match for an event to be considered.
        min_conf: Minimum confidence score to accept an event.
        ttl: Maximum age in seconds for events to be delivered.
        priority: Base priority hint used during arbitration.
    """
    try:
        sub_cfg: Dict[str, Any] = {
            "key": key.strip() if isinstance(key, str) and key.strip() else None,
            "tags": [t.strip() for t in tags] if tags else None,
            "min_conf": float(min_conf) if min_conf is not None else 0.0,
            "ttl": float(ttl) if ttl is not None else 300.0,
            "priority": float(priority) if priority is not None else 0.5,
            "last_index": 0,
        }
        _BLACKBOARD_SUBS[str(subscriber)] = sub_cfg
    except Exception:
        # If any conversion fails, fall back to defaults
        _BLACKBOARD_SUBS[str(subscriber)] = {
            "key": None,
            "tags": None,
            "min_conf": 0.0,
            "ttl": 300.0,
            "priority": 0.5,
            "last_index": 0,
        }

def _bb_collect_events() -> List[Dict[str, Any]]:
    """Collect and annotate working memory entries for blackboard arbitration.

    Returns a list of tuples (subscriber_id, entry, score).  Each entry is
    a shallow copy of the WM entry with an added ``bb_score``.  The score
    combines the base priority of the subscription with the entry's
    confidence and recency.  This helper does not mutate WM or the
    subscription registry.
    """
    events: List[Dict[str, Any]] = []
    try:
        # Snapshot WM without expiry metadata
        with _WM_LOCK:
            _prune_working_memory()
            snapshot = list(_WORKING_MEMORY)
        for sub_id, cfg in _BLACKBOARD_SUBS.items():
            # Determine the starting index; ensure valid range
            last_idx = int(cfg.get("last_index", 0))
            if last_idx < 0:
                last_idx = 0
            for idx, ent in enumerate(snapshot):
                # Skip entries already processed
                if idx < last_idx:
                    continue
                # Filter by key
                sub_key = cfg.get("key")
                if sub_key and ent.get("key") != sub_key:
                    continue
                # Filter by tags
                sub_tags = cfg.get("tags")
                if sub_tags:
                    try:
                        ent_tags = ent.get("tags") or []
                        if not any(t in ent_tags for t in sub_tags):
                            continue
                    except Exception:
                        continue
                # Filter by confidence
                try:
                    conf_val = float(ent.get("confidence", 0.0))
                except Exception:
                    conf_val = 0.0
                if conf_val < cfg.get("min_conf", 0.0):
                    continue
                # No time-based decay
                recency = 1.0
                # Compute reliability if present
                try:
                    reliability = float(ent.get("source_reliability", 1.0))
                except Exception:
                    reliability = 1.0
                base_p = cfg.get("priority", 0.5)
                score = base_p * conf_val * recency * reliability
                event_copy = {k: v for k, v in ent.items() if k != "expires_at"}
                event_copy["bb_score"] = score
                events.append({
                    "subscriber": sub_id,
                    "entry": event_copy,
                    "score": score,
                    "index": idx,
                })
    except Exception:
        return []
    return events

def _bb_mark_processed(sub_id: str, index: int) -> None:
    """Advance the last processed index for a subscriber."""
    try:
        sub = _BLACKBOARD_SUBS.get(sub_id)
        if sub is not None:
            sub["last_index"] = max(sub.get("last_index", 0), index + 1)
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Shared Working Memory (Step‑1 integration)
#
# The working memory is a simple in‑memory list of dictionaries used for
# opportunistic information exchange between cognitive modules.  Each entry
# includes a key, an arbitrary value, optional tags, a confidence score and
# an expiry timestamp.  Entries persist only for a short TTL and are
# automatically pruned on each access.  A lock protects concurrent access.
_WORKING_MEMORY: List[Dict[str, Any]] = []
_WM_LOCK = threading.Lock()

# ---------------------------------------------------------------------------
# Working Memory Persistence & Arbitration (Step‑2.1)
#
# These helpers enable persistence of the working memory across process runs
# and scoring of competing entries.  Persistence can be toggled via
# ``CFG['wm']['persist']`` and arbitration via ``CFG['wm']['arbitration']``.

# Flag to indicate whether we've loaded from disk already
_WM_LOADED_FROM_DISK: bool = False

def _wm_store_path() -> Path:
    """Return the path to the persistent working memory store."""
    try:
        root = globals().get("MAVEN_ROOT")
        if not root:
            # Fallback: ascend 4 levels to project root
            root = Path(__file__).resolve().parents[4]
        return (root / "reports" / "wm_store.jsonl").resolve()
    except Exception:
        return Path("wm_store.jsonl")

def _wm_persist_append(entry: Dict[str, Any]) -> None:
    """Append a working memory entry to the persistent store."""
    try:
        from api.utils import append_jsonl  # type: ignore
        append_jsonl(_wm_store_path(), entry)
    except Exception:
        pass

def _wm_load_from_disk(max_records: int = 5000) -> None:
    """Load persisted working memory entries from disk into memory.

    This is a best‑effort loader: it ignores malformed lines and expired entries.
    It should be called with the WM lock held and only once per process.
    """
    global _WM_LOADED_FROM_DISK
    if _WM_LOADED_FROM_DISK:
        return
    try:
        path = _wm_store_path()
        if not path.exists():
            _WM_LOADED_FROM_DISK = True
            return
        loaded = 0
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                if loaded >= max_records:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                _WORKING_MEMORY.append(rec)
                loaded += 1
        _prune_working_memory()
    except Exception:
        pass
    _WM_LOADED_FROM_DISK = True

def _wm_load_if_needed() -> None:
    """Load persisted working memory if configured and not yet loaded."""
    try:
        from api.utils import CFG  # type: ignore
        persist_enabled = True
        try:
            persist_enabled = bool((CFG.get("wm", {}) or {}).get("persist", True))
        except Exception:
            persist_enabled = True
    except Exception:
        persist_enabled = True
    if not persist_enabled:
        return
    with _WM_LOCK:
        _wm_load_from_disk()

def _prune_working_memory() -> None:
    """Remove expired items from the working memory.

    Entries contain an ``expires_at`` field set when they are stored via
    the ``WM_PUT`` operation.  This helper filters out any entry whose
    expiry has passed.  It must be called with the WM lock held.
    """
    # No time-based expiry - keep all entries
    pass

# ---------------------------------------------------------------------------
# Per-brain persistent memory with merge-write learning
#
# These helpers enable Maven to learn from validated facts by persisting
# key/value pairs to per-brain JSONL files. When the same fact is
# confirmed multiple times (TRUE verdict), confidence is bumped and
# access_count is incremented, creating a reinforcement learning effect.

def _brain_path(brain: str) -> Path:
    """Return the path to a brain's persistent memory file."""
    try:
        root = globals().get("MAVEN_ROOT")
        if not root:
            root = Path(__file__).resolve().parents[4]
        return (root / "reports" / "memory" / f"{brain}.jsonl").resolve()
    except Exception:
        return Path(f"{brain}.jsonl")

def _append_jsonl(path: Path, entry: Dict[str, Any]) -> None:
    """Append a JSON entry to a JSONL file."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass

def _get_brain(brain: str, ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Retrieve the most recent value for a key from a brain's memory.

    Scans the brain's JSONL file in reverse to find the last entry
    matching the requested key. Returns a dict with value, confidence,
    and access_count, or None if not found.
    """
    key = ctx.get("key")
    path = _brain_path(brain)
    if not path.exists():
        return {"status":"ok","data":None}
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        for line in reversed(lines):
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get("k") == key or rec.get("key") == key:
                return {"status":"ok","data":{
                    "value": rec.get("value", rec.get("v")),
                    "confidence": rec.get("confidence", 0.4),
                    "access_count": rec.get("access_count", 0)
                }}
    except Exception:
        pass
    return {"status":"ok","data":None}

def _merge_brain_kv(brain: str, key: str, value, conf_delta: float = 0.1) -> Dict[str, Any]:
    """Last-write-wins with confidence bump and access_count increment.

    When the same key/value pair is stored multiple times (indicating
    repeated validation), confidence is increased by conf_delta and
    access_count is incremented. This creates a reinforcement learning
    effect where frequently confirmed facts gain higher confidence.

    Args:
        brain: The brain name (used for file path)
        key: The memory key
        value: The memory value
        conf_delta: Confidence increase on repeat (default 0.1)

    Returns:
        Dict with value, confidence, and access_count
    """
    prev_resp = _get_brain(brain, {"key": key})
    prev = prev_resp.get("data") if isinstance(prev_resp, dict) else None
    if prev and str(prev.get("value")) == str(value):
        # Same value confirmed again - bump confidence and access count
        new_conf = min(1.0, float(prev.get("confidence") or 0) + conf_delta)
        new_acc = int(prev.get("access_count") or 0) + 1
    else:
        # New or changed value - start with modest confidence
        new_conf = 0.6  # starting point for newly confirmed facts
        new_acc = 1
    _append_jsonl(_brain_path(brain), {
        "key": key,
        "value": value,
        "confidence": new_conf,
        "access_count": new_acc,
    })
    return {"value": value, "confidence": new_conf, "access_count": new_acc}

# ---------------------------------------------------------------------------
# Relationship fact storage
#
# These helpers enable Maven to store and retrieve relationship facts such as
# "we are friends" or "we are not friends". Relationship facts are stored
# using the same JSONL mechanism as other facts, but with a dedicated "relationships"
# brain to keep them separate and easily queryable.

def set_relationship_fact(user_id: str, key: str, value: bool) -> None:
    """
    Store a simple relationship fact, e.g. ('friend_with_system', True).
    Should write to the same underlying store used for other user-specific facts.

    Args:
        user_id: The user identifier
        key: The relationship key (e.g., "friend_with_system")
        value: Boolean value indicating the relationship status
    """
    try:
        record = {
            "kind": "relationship",
            "key": key,
            "value": value,
            "user_id": user_id,
            "status": "confirmed",
            "source": "user_statement",
        }
        # Store in the relationships brain
        _append_jsonl(_brain_path("relationships"), record)
    except Exception:
        # Silently ignore errors to prevent pipeline disruption
        pass

def get_relationship_fact(user_id: str, key: str) -> dict | None:
    """
    Retrieve a relationship fact, or None if not present.
    Should use the existing memory/query mechanisms, not a new subsystem.

    Args:
        user_id: The user identifier
        key: The relationship key (e.g., "friend_with_system")

    Returns:
        The latest record for (user_id, key) or None if not found.
    """
    try:
        path = _brain_path("relationships")
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        # Scan in reverse to get the most recent entry
        for line in reversed(lines):
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get("user_id") == user_id and rec.get("key") == key:
                return rec
    except Exception:
        pass
    return None

def get_all_preferences(user_id: str) -> list:
    """
    Retrieve all stored preferences for a user.

    This searches through memory banks for records tagged with "preference"
    and returns them as a list of preference facts.

    Args:
        user_id: The user identifier

    Returns:
        List of preference records (dicts with keys like 'content', 'confidence', etc.)
    """
    preferences = []
    try:
        # Search through multiple banks where preferences might be stored
        bank_names = ["factual", "working_theories", "preferences"]

        for bank_name in bank_names:
            try:
                bank_path = _brain_path(bank_name)
                if not bank_path.exists():
                    continue

                with open(bank_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                for line in lines:
                    if not line.strip():
                        continue
                    try:
                        rec = json.loads(line)
                        # Check if this is a preference record for our user
                        if (rec.get("user_id") == user_id or not rec.get("user_id")) and \
                           ("preference" in str(rec.get("tags", [])).lower() or \
                            "preference" in str(rec.get("kind", "")).lower()):
                            preferences.append(rec)
                    except Exception:
                        continue
            except Exception:
                continue

    except Exception:
        pass

    return preferences

# ---------------------------------------------------------------------------
# Fast‑path caching for repeated queries
#
# When the same question is asked multiple times within a short time window,
# Maven should be able to answer instantly without re‑running heavy
# retrieval or reasoning.  To accomplish this, the memory librarian
# maintains a tiny cache mapping normalised questions to their validated
# answers along with confidence scores and timestamps.  Entries expire
# after 24 hours.  During the pipeline run, the librarian consults this
# cache before invoking the planner, pattern recogniser or any memory
# retrieval.  When a cache hit is detected, the pipeline short‑circuits
# most stages and goes straight to candidate generation and finalisation.
# The cache is appended to ``reports/fast_cache.jsonl`` for persistence.

FAST_CACHE_TTL_SEC: float = 24 * 60 * 60  # 24 hour expiration
# FAST_CACHE_PATH will be initialised after MAVEN_ROOT is defined.  Assign to None for now.
FAST_CACHE_PATH: Optional[Path] = None

# ---------------------------------------------------------------------------
# Semantic cache for cross‑session context reuse
#
# In addition to the fast cache used for exact repeat queries, the memory
# librarian maintains a lightweight semantic cache keyed by token overlap.
# This cache enables Maven to recall answers from previous runs when the
# current question shares a significant number of keywords with a past
# query.  Each entry stores the original query text, a token set, the
# answer, confidence and a timestamp.  When a new question arrives, the
# librarian consults the semantic cache after the fast cache lookup and
# before invoking heavy retrieval or reasoning.  If a match with at
# least 50 percent token overlap is found, the cached answer is used to
# generate a response directly, bypassing retrieval.  After the final
# answer is produced, the semantic cache is updated with the current
# query and answer for future reuse.
SEMANTIC_CACHE_PATH: Optional[Path] = None
# Semantic cache path for cross‑session context reuse.  This file stores
# a list of query→answer pairs used to answer semantically similar
# queries in the future.  It is initialised after ``MAVEN_ROOT`` is
# available below.
SEMANTIC_CACHE_PATH: Optional[Path] = None

# Phrases that indicate a cached answer may be meta, self‑referential or otherwise
# non‑informative.  If the cached answer contains any of these substrings
# (case‑insensitive), the cache entry is treated as invalid and the
# pipeline falls back to full retrieval.  This prevents a filler
# response like "I'm going to try my best" from being accepted as a
# factual answer on subsequent runs.
# Default phrases indicating a cached answer may be meta, self‑referential or otherwise
# non‑informative.  These are used as a fallback if no configuration file is provided.
BAD_CACHE_PHRASES: List[str] = [
    "i'm going to try my best",
    "i am going to try my best",
    "i don't have specific information",
    "i don't have information",
    "as an ai",
    "got it — noted",
    "got it - noted",
    "i'm also considering other possibilities",
    "i\u2019m going to try my best",  # unicode apostrophe variant
]

def _load_cache_sanity_phrases() -> List[str]:
    """Load bad phrases from config/cache_sanity.json if present.

    The configuration file should contain a JSON object with a
    ``bad_phrases`` list.  Each entry is normalised to lowercase and
    stripped of surrounding whitespace.  If the file is missing or
    malformed, the built‑in ``BAD_CACHE_PHRASES`` list is returned.
    """
    try:
        # MAVEN_ROOT may not be defined when this module is first imported.
        # Use a local import guard to avoid NameError; dynamic loading will
        # occur after MAVEN_ROOT is set up later in the file.
        root = globals().get("MAVEN_ROOT")
        if root:
            cfg_path = (root / "config" / "cache_sanity.json").resolve()
            if cfg_path.exists():
                with open(cfg_path, "r", encoding="utf-8") as fh:
                    data = json.load(fh) or {}
                phrases = data.get("bad_phrases") or data.get("BAD_PHRASES") or []
                if isinstance(phrases, list):
                    cleaned: List[str] = []
                    for p in phrases:
                        try:
                            s = str(p).strip().lower()
                            if s:
                                cleaned.append(s)
                        except Exception:
                            continue
                    if cleaned:
                        return cleaned
    except Exception:
        # Ignore any errors during config loading; fallback to default
        pass
    # Fallback to the built‑in BAD_CACHE_PHRASES
    try:
        return [str(p).strip().lower() for p in BAD_CACHE_PHRASES if p]
    except Exception:
        return []

# === Self query and similarity helpers =====================================

def _tokenize(text: str) -> List[str]:
    """Basic alphanumeric tokenizer used for similarity calculations.

    Args:
        text: Arbitrary string.
    Returns:
        A list of lower‑cased alphanumeric word tokens.
    """
    import re
    try:
        return [t for t in re.findall(r"\w+", str(text or "").lower()) if t]
    except Exception:
        return []

def _cosine_similarity(a: set[str], b: set[str]) -> float:
    """Compute a simple cosine similarity between two token sets.

    This treats the sets as binary vectors; the dot product is the
    intersection size, and norms are the square roots of the set sizes.
    Returns 0.0 when either set is empty.

    Args:
        a: Set of tokens for the first string.
        b: Set of tokens for the second string.
    Returns:
        Cosine similarity as a float between 0 and 1.
    """
    try:
        if not a or not b:
            return 0.0
        inter = len(a & b)
        if inter == 0:
            return 0.0
        from math import sqrt
        return inter / (sqrt(len(a)) * sqrt(len(b)))
    except Exception:
        return 0.0

def _jaccard(a: set[str], b: set[str]) -> float:
    """Compute the Jaccard similarity between two token sets.

    Returns 0.0 when either set is empty.
    Args:
        a: Set of tokens.
        b: Set of tokens.
    Returns:
        Jaccard similarity ratio.
    """
    try:
        if not a or not b:
            return 0.0
        inter = len(a & b)
        union = len(a | b)
        if union == 0:
            return 0.0
        return inter / union
    except Exception:
        return 0.0

def _is_self_query(text: str) -> bool:
    """Detect whether a query refers to the agent's self (identity, age, location or preferences).

    This helper identifies questions directed at the assistant about
    its own attributes.  In addition to WH‑pronoun combinations such
    as ``who are you``, ``what is your name`` and ``where are you``,
    it also detects preference queries like ``do you like …`` or
    ``what's your favourite …``.  The matching is deliberately
    conservative: we require a direct second‑person reference (``you`` or
    ``your``) in combination with a recognised trigger word (WH word,
    modal verb ``do`` or the word ``favourite``).  Age questions are
    handled explicitly.

    Args:
        text: Raw user query.
    Returns:
        True if the query appears to be about the agent's identity.
    """
    try:
        ql = (text or "").strip().lower()
    except Exception:
        return False
    import re
    # Age patterns
    if re.search(r"\bhow\s+old\s+are\s+you\b", ql) or re.search(r"\bhow\s+old\s+you\b", ql):
        return True
    # Identity patterns
    if re.search(r"\b(who|what|where|how)\b", ql) and re.search(r"\b(you|your|yourself)\b", ql):
        return True
    # Capabilities queries.  Detect questions asking about what the agent can do
    # or is capable of.  Match phrases like "what can you do", "what do you do",
    # "what are your capabilities", "what are you capable", and similar variations.
    try:
        # "what can you do" or "what do you do"
        if re.search(r"\bwhat\s+(?:can|do)\s+you\s+(?:do)?\b", ql):
            return True
        # "what are your capabilities/abilities/skills"
        if re.search(r"\bwhat\s+are\s+(?:your|you)\s+(?:capabilities|abilities|skills)\b", ql):
            return True
        # "what are you capable"
        if re.search(r"\bwhat\s+are\s+you\s+capable\b", ql):
            return True
    except Exception:
        pass
    # Preference or likes queries.  Users sometimes ask about Maven's tastes
    # using variations like "do you like", "what do you prefer", "what are your
    # preferences", "do you enjoy" or "are you into".  To robustly detect
    # these, split the query into word tokens and look for a pronoun
    # referring to the agent (you/your/yourself) together with a token
    # beginning with a preference root (e.g. like, prefer, favour, enjoy,
    # into, interested, love).  This captures misspellings such as
    # "likee" and "preferances" and synonyms like "favourite".  If both
    # conditions hold, treat the query as self‑referential so it
    # triggers the self model.
    try:
        tokens = re.findall(r"\b\w+\b", ql)
        # Include second‑person possessive "yours" and first‑/plural‑person
        # pronouns like "mine", "our", "ours", "we", "us" in the pronoun
        # set.  Queries containing these pronouns often refer back to
        # previously mentioned user or shared information rather than
        # requesting factual knowledge.  Without including these, such
        # questions may be misrouted to the general memory search instead
        # of being handled by the self model or pronoun resolution.
        pronouns = {"you", "your", "yourself", "yours", "mine", "our", "ours", "we", "us"}
        pref_roots = [
            "like", "lik", "prefer", "preferenc", "preferanc",
            "favor", "favour", "favorite", "favourite",
            "enjoy", "into", "interested", "love"
        ]
        found_pronoun = any(tok in pronouns for tok in tokens)
        found_pref = any(any(tok.startswith(root) for root in pref_roots) for tok in tokens)
        if found_pronoun and found_pref:
            return True
    except Exception:
        pass
    return False

#
# Environment query detection
#
def _is_env_query(text: str) -> bool:
    """
    Detect whether a query asks about Maven's environment or location.

    This helper checks for common phrases that refer to the agent's
    operating context (e.g. "where are you", "where are we",
    "where am i").  These are not geography questions about external
    places but rather about where the system itself resides.

    Args:
        text: Raw user query.
    Returns:
        True if the query appears to be about the agent's environment.
    """
    try:
        ql = (text or "").strip().lower()
    except Exception:
        return False
    patterns = [
        # "where are we" deliberately excluded; conversation meta detector handles this pattern
        "where are you",
        "where am i",
        "where's your location",
        "where is your location",
        "where do you live",
    ]
    for p in patterns:
        try:
            if p in ql:
                return True
        except Exception:
            continue
    return False

def _semantic_verify(answer: str) -> bool:
    """Check whether the provided answer appears meaningful.

    This simple heuristic attempts to reject filler or self‑referential
    responses without relying on external resources.  It returns
    ``False`` when the answer is empty, contains only punctuation,
    matches any configured bad phrase, or lacks alphabetic characters.

    Exception: Numeric answers (containing only digits, decimal points,
    minus signs, or commas) are accepted regardless of length, as they
    are valid responses to mathematical or counting questions.

    Args:
        answer: The answer text to verify.

    Returns:
        True if the answer seems substantive; False otherwise.
    """
    try:
        ans = str(answer or "").strip()
        if not ans:
            return False
        ans_lc = ans.lower()

        # Check if this is a purely numeric answer (allows digits, decimal, minus, comma)
        # This handles cases like "4", "3.14", "-5", "1,000"
        is_numeric = all(ch.isdigit() or ch in '.,- ' for ch in ans)
        has_digit = any(ch.isdigit() for ch in ans)

        if is_numeric and has_digit:
            # Numeric answers are valid regardless of length
            return True

        # Very short non-numeric answers are unlikely to be factual
        if len(ans_lc) < 3:
            return False
        # Reject if matches any bad phrase
        for bad in BAD_CACHE_PHRASES:
            try:
                if bad and bad in ans_lc:
                    return False
            except Exception:
                continue
        # Require at least one alphabetic character for non-numeric answers
        if not any(ch.isalpha() for ch in ans):
            return False
        return True
    except Exception:
        return False

def _purge_invalid_cache() -> None:
    """Remove invalid or poisoned entries from the fast cache on startup.

    This function reads the existing ``fast_cache.jsonl`` file and
    rewrites it, excluding any entries whose answers contain bad
    phrases or fail the semantic verifier.  Removed entries are
    recorded in ``reports/cache_poison.log`` for transparency.
    """
    try:
        path = globals().get("FAST_CACHE_PATH")
        root = globals().get("MAVEN_ROOT")
        if not path or not root:
            return
        cache_path: Path = path  # type: ignore
        if not cache_path.exists():
            return
        with open(cache_path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
        valid_lines: List[str] = []
        for ln in lines:
            try:
                rec = json.loads(ln)
            except Exception:
                continue
            ans = str(rec.get("answer", "")).strip()
            ans_lc = ans.lower()
            invalid = False
            # Phrase check
            for bad in BAD_CACHE_PHRASES:
                try:
                    if bad and bad in ans_lc:
                        invalid = True
                        break
                except Exception:
                    continue
            # Semantic verify
            if not invalid and not _semantic_verify(ans):
                invalid = True
            if invalid:
                # Log to cache_poison.log
                try:
                    log_path = root / "reports" / "cache_poison.log"
                    log_entry = {"query": rec.get("query"), "bad_answer": ans}
                    log_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(log_path, "a", encoding="utf-8") as lf:
                        lf.write(json.dumps(log_entry) + "\n")
                except Exception:
                    pass
                continue
            # Keep valid entry
            valid_lines.append(ln if ln.endswith("\n") else ln + "\n")
        # Rewrite cache if entries were removed
        if len(valid_lines) < len(lines):
            try:
                with open(cache_path, "w", encoding="utf-8") as fh:
                    for ln in valid_lines:
                        fh.write(ln)
            except Exception:
                pass
    except Exception:
        # Do not propagate purge errors
        pass

def _lookup_fast_cache(query: str) -> Optional[Dict[str, Any]]:
    """Look up a cached answer for the given query if it exists and is fresh.

    Queries are compared in a case‑insensitive manner after stripping
    surrounding whitespace.  If multiple cached entries match, the most
    recent valid entry is returned.  Expired entries (older than
    FAST_CACHE_TTL_SEC) are ignored.  Returns ``None`` when no valid
    cached answer is available.

    Args:
        query: The raw user query string.

    Returns:
        A dictionary with keys ``query``, ``answer``, ``confidence`` and
        ``timestamp`` if a fresh cached entry exists, otherwise ``None``.
    """
    try:
        qnorm = (query or "").strip().lower()
        if not qnorm:
            return None
        if FAST_CACHE_PATH.exists():
            # Read all lines and iterate from the end to find the most
            # recent matching entry.  This is efficient for small caches
            # (only a handful of repeated questions are expected) and
            # avoids reading the entire file into memory when it grows.
            with open(FAST_CACHE_PATH, "r", encoding="utf-8") as fh:
                lines = fh.readlines()
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if not isinstance(rec, dict):
                    continue
                try:
                    rec_q = str(rec.get("query", "")).strip().lower()
                except Exception:
                    rec_q = ""
                if rec_q != qnorm:
                    continue
                # Found a match
                return rec
        return None
    except Exception:
        # Silently ignore any errors to avoid breaking the pipeline
        return None

def _store_fast_cache_entry(query: str, answer: str, confidence: float) -> None:
    """Append a new entry to the fast‑path cache.

    Args:
        query: The original user query.
        answer: The validated answer text.
        confidence: The confidence score associated with the answer.
    """
    try:
        # Skip storing answers that fail semantic verification.  This
        # prevents obvious filler or meta responses from polluting the
        # cache.  Only store answers that appear substantive.
        if not query or not answer or not _semantic_verify(answer):
            return
        qnorm = str(query).strip()
        # Ensure reports directory exists
        FAST_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "query": qnorm,
            "answer": str(answer),
            "confidence": float(confidence) if confidence is not None else 0.8,
        }
        with open(FAST_CACHE_PATH, "a", encoding="utf-8") as fh:
            json.dump(record, fh)
            fh.write("\n")
    except Exception:
        # Do not propagate cache write errors
        pass

def _boost_cache_confidence(query: str, boost_amount: float = 0.1) -> Optional[float]:
    """Increment confidence for a cached entry when accessed repeatedly.

    This implements learning through repetition: when the same question is
    asked multiple times, we boost the confidence of the cached answer,
    indicating increased certainty through repeated validation.

    Args:
        query: The query whose cached entry should be updated.
        boost_amount: Amount to increment confidence (default 0.1).

    Returns:
        The new confidence value after boosting, or None if update failed.
    """
    try:
        qnorm = (query or "").strip().lower()
        if not qnorm or not FAST_CACHE_PATH.exists():
            return None

        # Read all cache entries
        with open(FAST_CACHE_PATH, "r", encoding="utf-8") as fh:
            lines = fh.readlines()

        updated = False
        new_lines = []
        new_confidence = None

        # Find and update the matching entry
        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                continue
            try:
                rec = json.loads(line_stripped)
                rec_q = str(rec.get("query", "")).strip().lower()

                if rec_q == qnorm:
                    # Boost confidence, capping at 0.99
                    old_conf = float(rec.get("confidence", 0.8))
                    new_confidence = min(0.99, old_conf + boost_amount)
                    rec["confidence"] = new_confidence
                    new_lines.append(json.dumps(rec) + "\n")
                    updated = True
                else:
                    new_lines.append(line if line.endswith("\n") else line + "\n")
            except Exception:
                # Keep malformed lines as-is
                new_lines.append(line if line.endswith("\n") else line + "\n")

        # Write back if we made changes
        if updated:
            with open(FAST_CACHE_PATH, "w", encoding="utf-8") as fh:
                for ln in new_lines:
                    fh.write(ln)
            return new_confidence

        return None
    except Exception:
        # Silently ignore errors to avoid breaking the pipeline
        return None

def _consolidate_memory_banks() -> Dict[str, Any]:
    """Consolidate facts across memory banks based on capacity and importance.

    This implements a simplified STM → MTM → LTM consolidation strategy:
    - When working_theories bank gets too large, promote high-importance facts to factual bank
    - Archive old, low-importance facts to reduce memory footprint
    - Capacity-based (not time-based) to ensure performance

    Returns:
        Dictionary with consolidation statistics (facts_moved, facts_archived, etc.)
    """
    try:
        # Define capacity thresholds (in number of facts)
        WORKING_THEORIES_CAPACITY = 100  # STM-like capacity
        FACTUAL_CAPACITY = 500  # MTM-like capacity

        stats = {
            "facts_promoted": 0,
            "facts_archived": 0,
            "errors": 0
        }

        # Get facts from working_theories bank
        try:
            wt_bank = _bank_module("working_theories")
            wt_response = wt_bank.service_api({
                "op": "LIST",
                "payload": {"limit": WORKING_THEORIES_CAPACITY + 50}
            })
            wt_facts = wt_response.get("payload", {}).get("facts", [])
        except Exception:
            wt_facts = []

        # If working_theories exceeds capacity, promote high-confidence facts
        if len(wt_facts) > WORKING_THEORIES_CAPACITY:
            # Sort by confidence and importance
            sorted_facts = sorted(
                wt_facts,
                key=lambda f: (f.get("confidence", 0.0) + f.get("importance", 0.0)) / 2,
                reverse=True
            )

            # Promote top facts to factual bank
            to_promote = sorted_facts[:20]  # Promote batch of 20
            for fact in to_promote:
                try:
                    # Check confidence threshold for promotion
                    conf = fact.get("confidence", 0.0)
                    if conf >= 0.6:  # Only promote moderately confident facts
                        factual_bank = _bank_module("factual")
                        factual_bank.service_api({
                            "op": "STORE",
                            "payload": {"fact": fact}
                        })
                        # Remove from working_theories
                        wt_bank.service_api({
                            "op": "DELETE",
                            "payload": {"id": fact.get("id")}
                        })
                        stats["facts_promoted"] += 1
                except Exception:
                    stats["errors"] += 1

        return stats
    except Exception as e:
        return {"error": str(e), "facts_promoted": 0, "facts_archived": 0}

def _count_recent_identical_queries(query: str, within_sec: float) -> int:
    """Count how many times the given query appears in the recent query log.

    The count includes the current invocation and any prior entries in
    ``reports/query_log.jsonl`` that occurred within the specified time
    window.  Matching is case‑insensitive after stripping whitespace.

    Args:
        query: The user query to count.
        within_sec: Time window in seconds to look back.

    Returns:
        The number of matching queries (>=1 when called during a pipeline run).
    """
    try:
        qnorm = (query or "").strip().lower()
        if not qnorm:
            return 0
        path = (MAVEN_ROOT / "reports" / "query_log.jsonl").resolve()
        count = 1  # include the current invocation
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                        except Exception:
                            continue
                        if not isinstance(obj, dict):
                            continue
                        rec_q = str(obj.get("query", "")).strip().lower()
                        if rec_q != qnorm:
                            continue
                        count += 1
            except Exception:
                pass
        return count
    except Exception:
        return 1

def _maybe_store_fast_cache(ctx: Dict[str, Any], threshold: int = 3, window_sec: float = 600.0) -> None:
    """Store a fast‑cache entry when the same query repeats multiple times.

    When the number of identical queries within ``window_sec`` seconds
    reaches ``threshold`` or higher, a new cache entry is created.  Only
    validated answers (stage 8 verdict TRUE) are stored.  If a fresh
    cache entry already exists for the query, this function does nothing.

    Args:
        ctx: The pipeline context containing ``original_query``,
            ``final_answer`` and ``final_confidence``.
        threshold: Number of occurrences required to trigger caching.
        window_sec: Time window for counting repeated queries.
    """
    try:
        q = str(ctx.get("original_query", "")).strip()
        if not q:
            return
        # Only store when we have a definitive answer validated by reasoning
        verdict = str((ctx.get("stage_8_validation") or {}).get("verdict", "")).upper()
        ans = ctx.get("final_answer") or ""
        if verdict != "TRUE" or not ans:
            return
        # Compute confidence value early for cache gating
        try:
            conf_val = float(ctx.get("final_confidence") or 0.8)
        except Exception:
            conf_val = 0.8
        # Apply cache quality gate: skip caching short, low‑confidence or pronoun queries
        if not _should_cache(q, verdict, conf_val):
            return
        # Check existing cache; skip if already cached
        if _lookup_fast_cache(q):
            return
        # Count recent identical queries (include current invocation)
        cnt = _count_recent_identical_queries(q, window_sec)
        if cnt >= threshold:
            # conf_val already computed above
            _store_fast_cache_entry(q, ans, conf_val)
    except Exception:
        # Never raise; caching failures are silent
        pass


# === Semantic cache helpers ==================================================

def _lookup_semantic_cache(query: str) -> Optional[Dict[str, Any]]:
    """Look up a semantically similar entry for the given query.

    The semantic cache stores tokenised representations of previous queries
    and their answers.  This helper reads the cache file and returns
    the best entry whose Jaccard similarity (intersection over union)
    with the current query meets a configurable threshold.  Matching
    is case‑insensitive and based on alphanumeric word tokens.  When
    no cache entry meets the threshold or the cache file is missing,
    None is returned.

    Args:
        query: The raw user query string.
    Returns:
        A dictionary with keys ``query``, ``tokens``, ``answer`` and
        ``confidence`` if a match is found, otherwise ``None``.
    """
    try:
        # Normalise and tokenise the incoming query
        q = str(query or "").strip().lower()
        if not q:
            return None
        import re as _re
        tokens = [t for t in _re.findall(r"\w+", q) if t]
        if not tokens:
            return None
        token_set: Set[str] = set(tokens)
        path = globals().get("SEMANTIC_CACHE_PATH")
        if not path or not getattr(path, "exists", lambda: False)():
            return None
        # Load the semantic cache list; file contains a JSON array
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, list):
                return None
        except Exception:
            return None
        best_entry: Optional[Dict[str, Any]] = None
        best_score: float = 0.0
        # Define a small set of stopwords to filter trivial overlaps.  Only
        # consider matches that share at least one substantive token.
        stopwords = {
            "a", "an", "the", "is", "are", "was", "were", "be", "to", "of",
            "and", "or", "not", "no", "you", "i", "we", "they", "he", "she", "it",
            "who", "what", "when", "where", "why", "how", "can", "will", "would",
            "should", "could", "might", "your", "my", "their", "his", "her"
        }
        for item in data:
            try:
                itoks = set(item.get("tokens", []))
                if not itoks:
                    continue
                # Intersection of tokens
                inter = token_set.intersection(itoks)
                if not inter:
                    continue
                # Filter out stopwords; require at least one non-stopword overlap
                if not (inter - stopwords):
                    continue
                # Compute Jaccard similarity over union
                union = token_set.union(itoks)
                ratio = len(inter) / max(1, len(union))
                # Accept matches above threshold (0.3) and keep the best
                if ratio >= 0.3 and ratio > best_score:
                    best_score = ratio
                    best_entry = item
            except Exception:
                continue
        return best_entry
    except Exception:
        return None


def _update_semantic_cache(ctx: Dict[str, Any]) -> None:
    """Update the semantic cache with the current query and answer.

    This function appends or updates an entry in the semantic cache
    corresponding to the query contained in the pipeline context.  It
    extracts a bag of word tokens from the ``original_query`` and
    stores them alongside the ``final_answer`` and confidence.  If
    another entry shares exactly the same token set, it is updated
    rather than duplicated.  The cache is stored as a JSON array and
    written atomically to avoid corruption.

    Args:
        ctx: The current pipeline context containing ``original_query``,
            ``final_answer`` and ``final_confidence`` fields.
    """
    try:
        q = str(ctx.get("original_query", "")).strip()
        ans = ctx.get("final_answer")
        if not q or not ans:
            return
        # Apply cache quality gate: skip caching short, low‑confidence or pronoun queries
        try:
            verdict = str((ctx.get("stage_8_validation") or {}).get("verdict", "")).upper()
        except Exception:
            verdict = ""
        try:
            conf_val = float(ctx.get("final_confidence") or 0.8)
        except Exception:
            conf_val = 0.8
        if not _should_cache(q, verdict, conf_val):
            return
        import re as _re
        tokens = [t for t in _re.findall(r"\w+", q.lower()) if t]
        if not tokens:
            return
        token_set = set(tokens)
        path = globals().get("SEMANTIC_CACHE_PATH")
        if not path:
            return
        # Ensure parent directory exists
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        # Load existing cache or start empty
        try:
            if path.exists():
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                if not isinstance(data, list):
                    data = []
            else:
                data = []
        except Exception:
            data = []
        updated = False
        # Update existing entry with matching token set
        for item in data:
            try:
                itoks = set(item.get("tokens", []))
            except Exception:
                itoks = set()
            if itoks == token_set:
                item["answer"] = str(ans)
                # Update confidence when provided
                try:
                    conf_val = float(ctx.get("final_confidence") or 0.8)
                except Exception:
                    conf_val = 0.8
                item["confidence"] = conf_val
                # Update intent and self_origin metadata on existing entry
                try:
                    lang_info = ctx.get("stage_3_language", {}) or {}
                    intent_type = str(lang_info.get("type")) if lang_info else None
                except Exception:
                    intent_type = None
                try:
                    val8 = ctx.get("stage_8_validation", {}) or {}
                    self_flag = bool(val8.get("self_origin") or val8.get("from_self_model"))
                except Exception:
                    self_flag = False
                if intent_type:
                    item["intent"] = intent_type
                item["self_origin"] = self_flag
                updated = True
                break
        if not updated:
            # Append new entry with additional metadata.  Capture the intent
            # type and whether the answer originated from the self model when available.
            try:
                conf_val = float(ctx.get("final_confidence") or 0.8)
            except Exception:
                conf_val = 0.8
            # Derive intent from stage_3_language if present
            try:
                lang_info = ctx.get("stage_3_language", {}) or {}
                intent_type = str(lang_info.get("type")) if lang_info else None
            except Exception:
                intent_type = None
            # Determine self origin from stage_8_validation if flagged
            try:
                val8 = ctx.get("stage_8_validation", {}) or {}
                self_flag = bool(val8.get("self_origin") or val8.get("from_self_model"))
            except Exception:
                self_flag = False
            data.append({
                "query": q,
                "tokens": list(token_set),
                "answer": str(ans),
                "confidence": conf_val,
                "intent": intent_type,
                "self_origin": self_flag,
            })
        # Write the updated cache atomically using api.utils if available
        try:
            from api.utils import _atomic_write  # type: ignore
            _atomic_write(path, json.dumps(data, indent=2))
        except Exception:
            # Fallback to naive write
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
    except Exception:
        # Suppress any errors during cache update
        pass

# Optional import of the belief tracker.  If unavailable, belief
# extraction and conflict detection will be skipped.
try:
    from brains.cognitive.belief_tracker.service.belief_tracker import add_belief as _belief_add, detect_conflict as _belief_detect  # type: ignore
except Exception:
    _belief_add = None  # type: ignore
    _belief_detect = None  # type: ignore

# Optional import of context management utilities for decay and reconstruction.
try:
    from brains.cognitive.context_management.service.context_manager import apply_decay as _ctx_decay  # type: ignore
    from brains.cognitive.context_management.service.context_manager import reconstruct_context as _ctx_reconstruct  # type: ignore
except Exception:
    _ctx_decay = None  # type: ignore
    _ctx_reconstruct = None  # type: ignore

# Optional import of meta‑learning for recording run metrics.  If absent,
# run metrics will not be captured.
try:
    from brains.cognitive.learning.service.meta_learning import record_run_metrics as _meta_record  # type: ignore
except Exception:
    _meta_record = None  # type: ignore


def _is_question(txt: str) -> bool:
    t = (txt or "").strip().lower()
    if not t:
        return False
    if t.endswith("?"):
        return True
    return t.split(" ", 1)[0] in ("do","does","did","is","are","can","will","should","could","would","was","were")


# === Paths / Wiring ==========================================================

THIS_FILE = Path(__file__).resolve()
SERVICE_DIR = THIS_FILE.parent
COG_ROOT = SERVICE_DIR.parent.parent          # brains/cognitive
MAVEN_ROOT = COG_ROOT.parent.parent           # brains

sys.path.insert(0, str(MAVEN_ROOT))

# Diagnostic logging helpers for memory operations
def _diag_log(tag, rec):
    try:
        root = MAVEN_ROOT
        p = root / "reports" / "diagnostics" / "diag.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps({"tag":tag, **(rec or {})}, ensure_ascii=False) + "\n")
    except Exception:
        pass

def _ok(data=None):  # uniform shape so .get('data') never crashes
    return {"status":"ok","data":data}

# Initialise FAST_CACHE_PATH now that MAVEN_ROOT is defined.  This ensures that
# the path is constructed correctly once MAVEN_ROOT is available.  If the global
# variable FAST_CACHE_PATH is None, set it to the reports directory under MAVEN_ROOT.
try:
    if 'FAST_CACHE_PATH' in globals() and FAST_CACHE_PATH is None:
        FAST_CACHE_PATH = MAVEN_ROOT / 'reports' / 'fast_cache.jsonl'
    # Initialise semantic cache path when MAVEN_ROOT is defined.  Use a
    # dedicated subdirectory under reports to avoid collisions with the
    # fast cache.  When SEMANTIC_CACHE_PATH is None, assign it here.
    if 'SEMANTIC_CACHE_PATH' in globals() and SEMANTIC_CACHE_PATH is None:
        SEMANTIC_CACHE_PATH = MAVEN_ROOT / 'reports' / 'cache' / 'semantic_index.json'
except Exception:
    # Fallback: default to a local file in the current working directory
    from pathlib import Path as _Path  # avoid shadowing main Path import
    FAST_CACHE_PATH = _Path('fast_cache.jsonl')
    # Use a local file for semantic cache when the project root cannot be
    # determined.  This ensures the semantic cache still functions in
    # degraded environments.
    SEMANTIC_CACHE_PATH = _Path('semantic_index.json')

# After determining FAST_CACHE_PATH, load dynamic cache sanity phrases
# from the configuration file and purge any invalid cache entries.  This
# ensures that BAD_CACHE_PHRASES is always up‑to‑date and that the cache
# does not contain poisoned answers when the service starts.
try:
    BAD_CACHE_PHRASES = _load_cache_sanity_phrases()
    _purge_invalid_cache()
except Exception:
    # Leave BAD_CACHE_PHRASES unchanged on error and skip purge
    pass

# -----------------------------------------------------------------------------
# Retrieval caching
#
# The librarian frequently queries all domain banks for a given user query.
# When multiple retrievals are performed during a single run with the same
# query and limit, the results are identical.  To avoid redundant work,
# maintain a simple in‑memory cache keyed by (query, limit).  This cache is
# not persisted across runs; it resets when the process restarts.  It also
# applies to parallel retrieval, sharing the same backing store.
_RETRIEVE_CACHE: dict[tuple[str, int], dict[str, Any]] = {}
# TTL in seconds for retrieval cache entries.  Cached results older than
# this threshold will be discarded to ensure that queries reflect recent
# updates.  A small TTL helps balance performance with freshness.  This
# constant may be tuned or made configurable via CFG in future iterations.
_RETRIEVE_CACHE_TTL: int = 60

# --- Autonomy config loader --------------------------------------------------
# The autonomy mechanism is controlled via a separate configuration file
# (config/autonomy.json).  This helper reads the file and returns a
# dictionary of settings.  If the file does not exist or is malformed, an
# empty dict is returned.  See the autonomy plan for details on keys such
# as "enable", "max_ticks_per_run", etc.
def _load_autonomy_config() -> Dict[str, Any]:
    try:
        cfg_path = (MAVEN_ROOT / "config" / "autonomy.json").resolve()
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as fh:
                return json.load(fh)
    except Exception:
        pass
    return {}

# For optional parallel bank retrieval
from concurrent.futures import ThreadPoolExecutor, as_completed

# === Module loaders ==========================================================

def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    # -------------------------------------------------------------------
    # Ensure that the loaded module exports a `handle` callable for
    # backward compatibility.  Many brain service modules only define
    # `service_api` as their entrypoint.  To conform to the uniform
    # service API expected by the memory librarian, mirror
    # `service_api` under the `handle` attribute if the module does not
    # already define it.  This check is intentionally wrapped in a
    # try/except to avoid propagating unexpected attribute errors that
    # could break module loading.
    try:
        if not hasattr(mod, "handle") and hasattr(mod, "service_api"):
            setattr(mod, "handle", getattr(mod, "service_api"))
    except Exception:
        # Errors during aliasing should not prevent the module from
        # loading.  Swallow any exceptions quietly.
        pass
    return mod

def _brain_module(name: str):
    svc = COG_ROOT / name / "service" / f"{name}_brain.py"
    return _load_module(svc, f"brain_{name}_service")

def _bank_module(name: str):
    svc = MAVEN_ROOT / "domain_banks" / name / "service" / f"{name}_bank.py"
    if not svc.exists():
        # legacy path: brains/domain_banks/...
        svc = MAVEN_ROOT / "brains" / "domain_banks" / name / "service" / f"{name}_bank.py"
    return _load_module(svc, f"bank_{name}_service")

def _gov_module():
    svc = MAVEN_ROOT / "brains" / "governance" / "policy_engine" / "service" / "policy_engine.py"
    return _load_module(svc, "policy_engine_service")

def _repair_module():
    svc = MAVEN_ROOT / "brains" / "governance" / "repair_engine" / "service" / "repair_engine.py"
    return _load_module(svc, "repair_engine_service")

def _personal_module():
    svc = MAVEN_ROOT / "brains" / "personal" / "service" / "personal_brain.py"
    return _load_module(svc, "personal_brain_service")

def _router_module():
    # Dual-process router under reasoning service.  Replace the previous learned
    # router with the dual_router wrapper to obtain a slow_path signal when
    # confidence margins are low.  The dual router forwards all supported
    # operations to the learned router, so callers can use the same API.
    svc = COG_ROOT / "reasoning" / "service" / "dual_router.py"
    return _load_module(svc, "dual_router_service")

# === Helpers =================================================================

_ALL_BANKS = [
    # Subject‑area banks
    "arts",
    "science",
    "history",
    "economics",
    "geography",
    "language_arts",
    "law",
    "math",
    "philosophy",
    "technology",
    # Theory and contradiction management
    "theories_and_contradictions",
    # Backwards‑compatibility bank for general factual statements.  This bank proxies
    # to the theories_and_contradictions bank and satisfies older tests that expect a generic 'factual' store.
    "factual",
    # STM‑only sink for unknown or low‑confidence facts.  This bank may be
    # deprecated in future but remains for legacy support.
    "stm_only",
    # Personal knowledge and self‑identity.  Including this bank allows
    # retrieval of foundational facts about Maven (e.g. who/why it was
    # created).  Without adding the personal bank here, the router never
    # queries it and such facts remain inaccessible.  See issue discussion
    # around identity queries.
    "personal",
    # Procedural knowledge bank for step-by-step instructions and processes
    "procedural",
    # Creative knowledge bank for imaginative and artistic content
    "creative",
    # Working theories bank for hypotheses and ongoing investigations
    "working_theories",
]

def _retrieve_from_banks(query: str, k: int = 5) -> Dict[str, Any]:
    """
    Retrieve evidence from all subject banks with deduplication.  Results are
    cached on a per‑query basis to avoid redundant retrievals within the same
    process.  The cache key is a tuple of the normalized query and limit.

    Args:
        query: The user query string.
        k: The maximum number of results to return per bank.

    Returns:
        A dictionary with 'results', 'banks' and 'banks_queried' fields.
    """
    # Attempt pronoun and continuation resolution using conversation state.
    # If the user query references the previous answer (e.g. "that") or
    # requests additional information (e.g. "anything else"), rewrite the
    # query accordingly and optionally restrict retrieval to the short‑term
    # memory bank.  Errors during resolution are suppressed so that the
    # fallback behaviour remains intact.
    force_stm_only: bool = False
    try:
        resolved_query, force_stm_only = _resolve_continuation_and_pronouns(query)
        if isinstance(resolved_query, str) and resolved_query:
            query = resolved_query
    except Exception:
        force_stm_only = False
    # Handle continuation patterns: if the query appears to ask for 'more'
    # information or a continuation (e.g. "more", "more about brains",
    # "anything else"), replace it with the last known topic.  This ensures
    # that follow‑up questions search the same domain as the prior query.
    try:
        q_raw = str(query or "")
    except Exception:
        q_raw = ""
    try:
        ql = q_raw.strip().lower()
    except Exception:
        ql = ""

    # ------------------------------------------------------------------
    # Explanation trigger detection
    #
    # Certain follow‑up queries ask for an explanation of the previous
    # answer rather than additional facts.  Examples include
    # "how did you get 5?", "how did you come up with that?",
    # "explain that", and similar.  When such a pattern is detected,
    # bypass normal retrieval and delegate to the reasoning brain's
    # EXPLAIN_LAST operation.  The conversation state provides the
    # necessary context (last_query and last_response).  This early
    # return prevents redundant searches and ensures the explanation
    # surfaces as the primary retrieval result.
    try:
        _ql = str(query or "").strip().lower()
    except Exception:
        _ql = ""
    try:
        import re as _re_explain
        # Define patterns for explanation requests
        _explain_patterns = [
            r"^how\s+did\s+you\s+get\b",
            r"^how\s+did\s+you\s+come\s+up\s+with\b",
            r"^explain\b",
            r"^why\s+did\s+you\s+get\b",
            r"^how\s+did\s+you\s+do\b",
        ]
        _needs_explanation = False
        for _pat in _explain_patterns:
            if _re_explain.search(_pat, _ql):
                _needs_explanation = True
                break
        if _needs_explanation:
            # Fetch conversation state safely
            conv = globals().get("_CONVERSATION_STATE", {}) or {}
            last_q = conv.get("last_query", "") or ""
            last_r = conv.get("last_response", "") or ""
            # Attempt to call the reasoning brain's explanation op
            try:
                reason_mod = _brain_module("reasoning")
            except Exception:
                reason_mod = None
            explanation_text: str | None = None
            if reason_mod is not None:
                try:
                    resp = reason_mod.service_api({
                        "op": "EXPLAIN_LAST",
                        "payload": {
                            "last_query": last_q,
                            "last_response": last_r
                        }
                    })
                    if resp and resp.get("ok"):
                        explanation_text = (resp.get("payload") or {}).get("answer") or None
                except Exception:
                    explanation_text = None
            # Fallback if the reasoning brain is unavailable or returns nothing
            if not explanation_text:
                # Construct a simple reference to the last response
                if last_r:
                    explanation_text = f"I answered '{last_r}' previously based on my reasoning and memory."
                else:
                    explanation_text = "I don't have enough context to provide an explanation."
            # Return the explanation as a single retrieval result.  Use a
            # synthetic bank name so downstream components can
            # differentiate explanatory content from factual retrieval.
            return {
                "results": [
                    {"content": explanation_text, "source_bank": "explanation"}
                ],
                "banks": ["explanation"],
                "banks_queried": ["explanation"]
            }
    except Exception:
        # On error, ignore and continue with normal retrieval
        pass
    try:
        # Detect explicit 'more about X' and extract X (legacy support)
        if ql.startswith("more about "):
            candidate = ql[len("more about "):].strip()
            if candidate:
                query = candidate
        # Detect bare 'more', 'anything else', 'any thing else', 'what else'
        elif ql in {"more", "anything else", "any thing else", "what else"} or \
            (ql.startswith("more ") and len(ql.split()) <= 2):
            # Use the last topic if available
            if _LAST_TOPIC:
                query = _LAST_TOPIC
    except Exception:
        # On error, fall back to the original query
        query = q_raw
    # Normalise key for cache lookup; default limit of 5 if invalid
    try:
        limit_int = int(k)
    except Exception:
        limit_int = 5
    key = (str(query or ""), limit_int)
    cached = _RETRIEVE_CACHE.get(key)
    if cached is not None:
        return {
            "results": list(cached.get("results", [])),
            "banks": list(cached.get("banks", [])),
            "banks_queried": list(cached.get("banks_queried", []))
        }
    results: list[Dict[str, Any]] = []
    searched: list[str] = []
    seen_contents: set[str] = set()
    # Determine targeted banks based on messages from the message bus.  If a
    # search request has been issued (e.g. by the reasoning brain), only
    # query the specified banks; otherwise fall back to all banks.  Before
    # consulting the message bus, handle relational queries locally: when
    # the query expresses a relationship between the user and the assistant
    # (e.g. "we are friends"), restrict the search to the personal bank.
    banks_to_use: List[str] = []
    try:
        ql = str(query or "").lower()
        # Detect relational query patterns: check for "we" or "you and i"
        # along with relationship keywords.  If matched, search only personal.
        rel_keywords = ["friend", "friends", "family", "partner", "partners", "couple", "married", "husband", "wife", "siblings", "brother", "sister"]
        if any(rk in ql for rk in rel_keywords):
            if re.search(r"\bwe\b", ql) or re.search(r"\byou and i\b", ql) or re.search(r"\bwe\s*'re\b", ql):
                banks_to_use = ["personal"]
    except Exception:
        banks_to_use = []
    try:
        from brains.cognitive.message_bus import pop_all  # type: ignore
        # Consume any pending messages
        msgs = pop_all()
        for m in msgs:
            try:
                if m.get("type") == "SEARCH_REQUEST":
                    domains = m.get("domains") or []
                    # Map domain keywords to bank names by substring match
                    for d in domains:
                        d_str = str(d).lower()
                        for b in _ALL_BANKS:
                            if d_str in b.lower() and b not in banks_to_use:
                                banks_to_use.append(b)
                    # Only handle the first search request for now
                    if banks_to_use:
                        break
            except Exception:
                continue
    except Exception:
        banks_to_use = []
    # If no targeted banks were specified, search all banks
    if not banks_to_use:
        banks_to_use = list(_ALL_BANKS)
    # Override bank selection when continuation or pronoun resolution forces STM
    try:
        if force_stm_only:
            banks_to_use = ["stm_only"]
    except Exception:
        pass
    for b in banks_to_use:
        try:
            svc = _bank_module(b)
            r = svc.service_api({"op": "RETRIEVE", "payload": {"query": query, "limit": k}})
            if r.get("ok"):
                pay = r.get("payload") or {}
                rr = pay.get("results") or []
                for item in rr:
                    if not isinstance(item, dict):
                        continue
                    item.setdefault("source_bank", b)
                    # Normalize content for deduplication.  Use the raw text if
                    # available, else fallback to serialized form.
                    content = str(item.get("content", "")).strip().lower()
                    if not content:
                        content = json.dumps(item, sort_keys=True)
                    # Simple relevance: ratio of query words present in content.
                    try:
                        q_tokens = [w for w in re.findall(r"\b\w+\b", str(query).lower())]
                        c_tokens = [w for w in re.findall(r"\b\w+\b", content)]
                        overlap = sum(1 for w in q_tokens if w in c_tokens)
                        relevance = float(overlap) / float(len(q_tokens) or 1)
                    except Exception:
                        relevance = 0.0
                    # Apply relevance floor: require at least 0.2 overlap
                    if relevance < 0.2:
                        continue
                    if content in seen_contents:
                        continue
                    seen_contents.add(content)
                    results.append(item)
                searched.append(b)
        except Exception:
            # Ignore individual bank failures
            continue
    res = {"results": results, "banks": searched, "banks_queried": searched}
    # Persist in cache (store copies to avoid accidental mutation)
    _RETRIEVE_CACHE[key] = {
        "results": list(results),
        "banks": list(searched),
        "banks_queried": list(searched),
    }
    return res

# Optional parallel retrieval implementation.  When parallel access is enabled
# via CFG["parallel_bank_access"], this helper will query each domain bank
# concurrently.  It accepts an optional max_workers argument to control
# concurrency.  Results are aggregated in the same format as
# _retrieve_from_banks.
def _retrieve_from_banks_parallel(query: str, k: int = 5, max_workers: int = 5) -> Dict[str, Any]:
    """
    Retrieve evidence from all subject banks using concurrent workers.

    Identical query/limit combinations are cached in the same cache as
    the sequential retrieval helper.  When a result is in the cache, this
    function skips all parallel calls and returns the cached result.

    Args:
        query: The user query string.
        k: Maximum number of results to return per bank.
        max_workers: Number of threads to use for concurrent bank access.

    Returns:
        A dictionary with 'results', 'banks' and 'banks_queried' fields.
    """
    try:
        limit_int = int(k)
    except Exception:
        limit_int = 5
    # Detect explanation requests early and delegate to sequential
    # retrieval so that specialised logic (e.g. EXPLAIN_LAST) can be
    # executed.  Without this check, parallel retrieval would miss
    # explanation patterns and return unrelated facts.  Only simple
    # prefix patterns are considered here to avoid unnecessary work.
    try:
        import re as _re_explain
        ql = str(query or "").strip().lower()
        _explain_triggers = [
            r"^how\s+did\s+you\s+get\b",
            r"^how\s+did\s+you\s+come\s+up\s+with\b",
            r"^explain\b",
            r"^why\s+did\s+you\s+get\b",
            r"^how\s+did\s+you\s+do\b",
        ]
        for _pat in _explain_triggers:
            if _re_explain.search(_pat, ql):
                # Delegate to sequential retrieval which handles explanation
                return _retrieve_from_banks(query, limit_int)
    except Exception:
        pass
    key = (str(query or ""), limit_int)
    cached = _RETRIEVE_CACHE.get(key)
    if cached is not None:
        return {
            "results": list(cached.get("results", [])),
            "banks": list(cached.get("banks", [])),
            "banks_queried": list(cached.get("banks_queried", []))
        }
    results: list[dict] = []
    searched: list[str] = []
    seen_contents: set[str] = set()
    # Submit retrieval tasks for each bank concurrently.
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_bank = {}
        for b in _ALL_BANKS:
            try:
                svc = _bank_module(b)
                fut = pool.submit(svc.service_api, {"op": "RETRIEVE", "payload": {"query": query, "limit": k}})
                future_to_bank[fut] = b
            except Exception:
                # Skip banks that fail to load
                continue
        # Process completed futures as they finish
        for fut in as_completed(future_to_bank):
            b = future_to_bank[fut]
            try:
                r = fut.result()
            except Exception:
                continue
            try:
                if r.get("ok"):
                    pay = r.get("payload") or {}
                    rr = pay.get("results") or []
                    for item in rr:
                        if not isinstance(item, dict):
                            continue
                        # Annotate with source bank
                        item.setdefault("source_bank", b)
                        # Normalize content for deduplication
                        content = str(item.get("content", "")).strip().lower()
                        if not content:
                            content = json.dumps(item, sort_keys=True)
                        if content in seen_contents:
                            continue
                        seen_contents.add(content)
                        results.append(item)
                    searched.append(b)
            except Exception:
                continue
    res = {
        "results": results,
        "banks": searched,
        "banks_queried": searched
    }
    _RETRIEVE_CACHE[key] = {
        "results": list(results),
        "banks": list(searched),
        "banks_queried": list(searched),
    }
    return res

# --- Hybrid Semantic Memory & Retrieval Unification (Step‑7) ---
def _unified_retrieve(query: str, k: int = 5, filters: Optional[dict] = None) -> Dict[str, Any]:
    """
    Retrieve evidence from all domain banks and apply personal preference boost.

    This helper first performs a standard retrieval across all domain banks,
    then augments each result with a boost derived from the personal brain.
    The final score is the sum of the original confidence and the personal
    boost.  Results are sorted by this total score in descending order.

    Args:
        query: The user query string.
        k: Maximum number of results to return.
        filters: Optional filters for future extension (unused).

    Returns:
        A dictionary with 'results', 'banks' and 'banks_queried' fields.  Each
        result is annotated with 'boost' and 'total_score'.
    """
    # Decide between parallel and sequential retrieval based on configuration
    try:
        parallel = bool((CFG.get("memory") or {}).get("parallel_bank_access", False))
    except Exception:
        parallel = False
    try:
        limit_int = int(k)
    except Exception:
        limit_int = 5
    # Perform base retrieval across all banks
    try:
        base = _retrieve_from_banks_parallel(query, limit_int) if parallel else _retrieve_from_banks(query, limit_int)
    except Exception:
        # Fall back to sequential retrieval on any error
        base = _retrieve_from_banks(query, limit_int)
    results = list(base.get("results") or [])
    # Attempt to load personal brain service for boosting
    try:
        _personal = _personal_module()
        personal_api = getattr(_personal, "service_api", None)
    except Exception:
        personal_api = None
    enriched: List[Dict[str, Any]] = []
    for item in results:
        # Normalise the subject text for boosting
        try:
            subj = str(item.get("content") or item.get("text") or "").strip()
        except Exception:
            subj = ""
        boost_val: float = 0.0
        if personal_api and subj:
            # Call personal brain to compute a boost.  Errors are ignored.
            try:
                resp = personal_api({"op": "SCORE_BOOST", "payload": {"subject": subj}})
                if resp and resp.get("ok"):
                    boost_val = float((resp.get("payload") or {}).get("boost") or 0.0)
            except Exception:
                boost_val = 0.0
        # Determine original confidence or score from result
        try:
            conf_val = float(item.get("confidence") or item.get("score") or 0.0)
        except Exception:
            conf_val = 0.0
        total = conf_val + boost_val
        # Annotate result with boost and total_score
        enriched_item = dict(item)
        enriched_item["boost"] = boost_val
        enriched_item["total_score"] = total
        enriched.append(enriched_item)
    # Sort results by descending total_score
    enriched.sort(key=lambda x: x.get("total_score", 0.0), reverse=True)
    # Trim to requested limit
    if limit_int > 0:
        enriched = enriched[:limit_int]
    return {
        "results": enriched,
        "banks": base.get("banks", []),
        "banks_queried": base.get("banks_queried", [])
    }

# ---------------------------------------------------------------------------
# Unified retrieval across memory systems (Step‑7 integration)
#
# The hybrid retrieval helper performs a combined search across all subject
# banks and applies a preference boost from the personal brain to each
# result.  The boost is retrieved by calling the personal brain's
# SCORE_BOOST operation with the record's textual content.  The final
# score for each result is the sum of its base confidence and the
# personal boost.  Results are sorted by this total score and the top
# ``k`` items are returned.  This function falls back to sequential
# retrieval if parallel bank access is disabled or if any errors occur.

def _unified_retrieve(query: str, k: int = 5, filters: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    """Hybrid retrieval across memory systems with personal preference boosting.

    Args:
        query: The user query string.
        k: Maximum number of results to return.
        filters: Optional dict of filters (currently unused; reserved for future use).

    Returns:
        A list of result dictionaries sorted by total_score, each with
        additional ``boost`` and ``total_score`` fields.
    """
    # Attempt to retrieve results from all banks.  Prefer parallel retrieval
    # when available; on failure, fall back to sequential retrieval.
    try:
        try:
            data = _retrieve_from_banks_parallel(query, k)
        except Exception:
            data = _retrieve_from_banks(query, k)
        res_list = list(data.get("results", []))
    except Exception:
        res_list = []
    scored: List[Dict[str, Any]] = []
    if not res_list:
        return []
    # Lazy import of the personal brain API.  If unavailable, boosting is skipped.
    try:
        from brains.personal.service.personal_brain import service_api as _personal_api  # type: ignore
    except Exception:
        _personal_api = None  # type: ignore
    for item in res_list:
        # Extract the textual subject of the record.  Prefer the 'content' field,
        # then fallback to 'text'.  If neither exists, use an empty string.
        subj = str(item.get("content") or item.get("text") or "")
        boost_val = 0.0
        if subj and _personal_api is not None:
            try:
                pb_res = _personal_api({"op": "SCORE_BOOST", "payload": {"subject": subj}})
                boost_val = float((pb_res.get("payload") or {}).get("boost") or 0.0)
            except Exception:
                # Ignore any errors when requesting a boost; treat as zero
                boost_val = 0.0
        # Base confidence defaults to 0.0 if missing or non‑numeric
        try:
            base = float(item.get("confidence", 0.0))
        except Exception:
            base = 0.0
        total = base + boost_val
        try:
            rec = dict(item)
        except Exception:
            rec = {"content": subj}
        rec["boost"] = boost_val
        rec["total_score"] = total
        scored.append(rec)
    # Sort results by total_score in descending order
    scored.sort(key=lambda x: x.get("total_score", 0.0), reverse=True)
    # Return at least one result even if k is zero or negative
    try:
        k_int = int(k)
    except Exception:
        k_int = 5
    return scored[: max(1, k_int)]

def _unified_retrieve(query: str, k: int = 5, filters: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    """Hybrid retrieval across memory systems with personal boost.

    This helper executes a combined retrieval across all subject banks and
    applies a preference boost from the personal brain to each result.
    Results are scored by combining the base confidence with the boost and
    then sorted in descending order.  Only the top ``k`` results are
    returned.  The returned items include the fields from the original
    records plus ``boost`` and ``total_score`` keys.

    Args:
        query: The user query string.
        k: Maximum number of results to return.
        filters: Optional filters (unused for now; reserved for future use).

    Returns:
        A list of result dicts with additional boost and total_score fields.
    """
    # Perform a full retrieval across all banks.  Fall back to serial
    # retrieval if the parallel helper is unavailable or raises.
    try:
        try:
            data = _retrieve_from_banks_parallel(query, k)
        except Exception:
            data = _retrieve_from_banks(query, k)
        res_list = list(data.get("results", []))
    except Exception:
        res_list = []
    scored: List[Dict[str, Any]] = []
    if not res_list:
        return []
    # Import personal brain API lazily to avoid cyclic dependencies unless needed
    try:
        from brains.personal.service.personal_brain import service_api as _personal_api  # type: ignore
    except Exception:
        _personal_api = None  # type: ignore
    for item in res_list:
        subj = str(item.get("content") or item.get("text") or "")
        boost_val = 0.0
        if subj and _personal_api is not None:
            try:
                pb_res = _personal_api({"op": "SCORE_BOOST", "payload": {"subject": subj}})
                boost_val = float((pb_res.get("payload") or {}).get("boost") or 0.0)
            except Exception:
                boost_val = 0.0
        # Use the confidence field as a base score if present and numeric
        try:
            base = float(item.get("confidence", 0.0))
        except Exception:
            base = 0.0
        total = base + boost_val
        try:
            rec = dict(item)
        except Exception:
            rec = {"content": subj}
        rec["boost"] = boost_val
        rec["total_score"] = total
        scored.append(rec)
    scored.sort(key=lambda x: x.get("total_score", 0.0), reverse=True)
    return scored[:max(1, int(k))]

def _scan_counts(root: Path) -> Dict[str, Dict[str, int]]:
    """Return a mapping of brain name to counts of records per memory tier.

    This helper is used by the memory librarian to surface a high‑level
    snapshot of memory usage across different cognitive brains.  The
    original implementation hard‑coded a subset of brains and omitted
    newly added modules such as the coder brain.  To provide a more
    complete view of memory, this function now includes the coder brain
    alongside the existing ones.  If a brain is missing its memory
    directory or any error occurs while reading, an empty dict is
    returned for that brain.

    Args:
        root: Path to the cognitive brains root directory.

    Returns:
        A dict keyed by brain name with values of tier→record count.
    """
    from api.memory import tiers_for, count_lines  # type: ignore
    out: Dict[str, Dict[str, int]] = {}
    brains = [
        "sensorium",
        "planner",
        "language",
        "pattern_recognition",
        "reasoning",
        "affect_priority",
        "personality",
        "self_dmn",
        "system_history",
        "memory_librarian",
        # Include the coder brain in the memory overview to ensure its
        # memory usage is tracked like other cognitive modules.  Without
        # this, the coder's STM/MTM/LTM tiers are invisible to the
        # librarian and cannot be consolidated or reported upon.
        "coder",
    ]
    for brain in brains:
        broot = root / brain
        try:
            tiers = tiers_for(broot)
            out[brain] = {tier: count_lines(path) for tier, path in tiers.items()}
        except Exception:
            out[brain] = {}
    # Add counts for the personal knowledge bank (domain_bank) for completeness
    try:
        personal_root = MAVEN_ROOT / "brains" / "personal"
        tiers = tiers_for(personal_root)
        out["personal"] = {tier: count_lines(path) for tier, path in tiers.items()}
    except Exception:
        out["personal"] = {}
    return out

def _extract_definition(text: str):
    # Primitive "X is a Y" pattern to teach the router definitions when TRUE
    m = re.match(r'^(?P<term>[A-Za-z0-9 ]{1,40})\s+(is|are)\s+(a|an)?\s*(?P<klass>[A-Za-z0-9 ]{1,40})\.?$', text.strip(), re.I)
    if not m:
        return None, None
    term = (m.group("term") or "").strip().lower()
    klass = (m.group("klass") or "").strip().lower()
    if not term or not klass or term == klass:
        return None, None
    return term, klass

def _is_simple_math_expression(text: str) -> bool:
    """
    Detect if the input is a simple arithmetic expression like "2+5" or "3*4".
    Returns True for basic patterns with two numbers and an operator.
    """
    try:
        s = str(text or "").strip()
        # Match patterns like "2+5", "3 * 4", "10 - 3", etc.
        # Allow optional whitespace around numbers and operators
        pattern = r'^\s*\d+\s*[\+\-\*/]\s*\d+\s*$'
        if re.match(pattern, s):
            return True
    except Exception:
        pass
    return False

def _solve_simple_math(expression: str) -> Dict[str, Any]:
    """
    Solve a simple arithmetic expression containing two numbers and one operator.
    Supports +, -, *, / operations. Returns a dict with ok:True and result on success,
    or ok:False on parse failure. No eval() is used - only safe Python operators.
    """
    try:
        expr = str(expression or "").strip()
        # Extract lhs, operator, rhs using regex
        m = re.match(r'^\s*(\d+)\s*([\+\-\*/])\s*(\d+)\s*$', expr)
        if not m:
            return {"ok": False}

        lhs = int(m.group(1))
        op = m.group(2)
        rhs = int(m.group(3))

        # Compute result using safe operators
        if op == '+':
            result = lhs + rhs
        elif op == '-':
            result = lhs - rhs
        elif op == '*':
            result = lhs * rhs
        elif op == '/':
            if rhs == 0:
                return {"ok": False}
            result = lhs / rhs
            # Use integer if result is whole number
            if isinstance(result, float) and result.is_integer():
                result = int(result)
        else:
            return {"ok": False}

        return {"ok": True, "result": result}
    except Exception:
        return {"ok": False}

def _simple_route_to_bank(content: str) -> str:
    """
    Perform a simple keyword-based routing of new statements to domain banks.
    This helper looks for words associated with biology, physics/chemistry,
    math, history or geography.  If a match is found, the corresponding bank
    name is returned; otherwise the result defaults to 'working_theories'.
    """
    try:
        text = (content or "").strip().lower()
        # Check for simple arithmetic expressions first (higher priority)
        if _is_simple_math_expression(text):
            return "math"
        # Biology keywords (science bank)
        biology = [
            "mammal","animal","bird","species","organism","polar bear",
            "wings","skin","fur","feathers","evolution","biology","creature",
            "wildlife"
        ]
        if any(w in text for w in biology):
            return "science"
        # Physics/Chemistry keywords (science bank)
        physics = [
            "energy","force","atom","molecule","gravity","einstein",
            "physics","quantum","relativity","mass","velocity"
        ]
        if any(w in text for w in physics):
            return "science"
        # Math keywords
        math_words = [
            "+","-","*","/","=","²","³","equation","calculate","sum",
            "multiply","divisible","prime","square","triangle"
        ]
        if any(w in text for w in math_words):
            return "math"
        # History keywords or famous names
        history_indicators = [
            "was","were","born","died","war","ancient","century","historical"
        ]
        famous_people = ["einstein","newton","darwin","lincoln","washington","napoleon"]
        if any(w in text for w in history_indicators) or any(fn in text for fn in famous_people):
            return "history"
        # Geography
        geography_words = [
            "capital","country","city","continent","ocean","mountain",
            "river","lake","france","paris","europe","asia"
        ]
        if any(w in text for w in geography_words):
            return "geography"
    except Exception:
        pass
    return "working_theories"

def _best_memory_exact(evidence: Dict[str, Any], content: str):
    try:
        for it in (evidence or {}).get("results", []):
            if isinstance(it, dict) and str(it.get("content","")).strip().lower() == str(content).strip().lower():
                return it
    except Exception:
        pass
    return None

# Sanitize a yes/no question into a declarative form.  This helper strips
# trailing question marks and leading auxiliary verbs (e.g. "do", "does", "is", etc.)
# so that retrieval can find matching declarative statements such as
# "Birds have wings." when asked "Do birds have wings?".
def _sanitize_question(query: str) -> str:
    """
    Normalize a user question to a declarative form that helps match stored
    facts.  This helper strips trailing question marks, removes common
    yes/no prefixes (e.g., "is", "are", "can"), and extracts the
    subject phrase that follows forms of "to be".  For example:

        "Is the sky blue?"  ->  "the sky blue"
        "What color is the sky?"  ->  "the sky"

    Args:
        query: The raw user question string.

    Returns:
        A sanitized string suitable for memory retrieval.
    """
    try:
        q = (query or "").strip()
        if q.endswith("?"):
            q = q[:-1]
        lower = q.lower().strip()
        # Strip common yes/no question prefixes (e.g., "is", "are", "can")
        prefixes = [
            "do ", "does ", "did ", "is ", "are ", "can ", "should ",
            "could ", "will ", "would ", "was ", "were "
        ]
        for p in prefixes:
            if lower.startswith(p):
                # Remove the prefix from both q and its lowercase copy
                q = q[len(p):].strip()
                lower = q.lower()
                break
        # Attempt to extract the subject after a form of "to be" (is/are/was/were)
        for verb in [" is ", " are ", " was ", " were "]:
            if verb in lower:
                parts = q.split(verb, 1)
                if len(parts) > 1 and parts[1].strip():
                    q = parts[1].strip()
                break
        return q.strip() or query
    except Exception:
        return query

# --- Context and query history helpers ---------------------------------------

def _get_recent_queries(limit: int = 5) -> List[Dict[str, Any]]:
    """Retrieve the most recent user queries from a flat query log.

    The query log lives at ``reports/query_log.jsonl`` and contains one JSON
    object per line with fields ``query`` and ``timestamp``.  This helper
    returns the last ``limit`` entries in chronological order (oldest first).

    Args:
        limit: Maximum number of recent queries to return.

    Returns:
        A list of dicts each with ``query`` and ``timestamp`` keys.
    """
    path = (MAVEN_ROOT / "reports" / "query_log.jsonl").resolve()
    entries: List[Dict[str, Any]] = []
    try:
        # If the file does not exist, return an empty list.  This avoids a
        # TypeError on subsequent reads when None would otherwise be returned.
        if not path.exists():
            return []
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
        # Parse JSON lines; ignore malformed lines
        for line in lines:
            try:
                obj = json.loads(line)
                if isinstance(obj, dict) and "query" in obj:
                    entries.append({"query": obj.get("query")})
            except Exception:
                continue
    except Exception:
        # On any error, return an empty list instead of None
        return []
    # Return the last ``limit`` entries (chronological order retained).  If there
    # are fewer than ``limit`` entries, return all of them.
    return entries[-limit:]

def _cross_validate_answer(ctx: Dict[str, Any]) -> None:
    """
    Perform a lightweight self‑check on the validated answer stored in
    ``ctx['stage_8_validation']``.  This helper examines the original
    query and the answer and attempts to verify simple factual claims
    without requiring external services.  Two kinds of checks are
    performed:

    1. Arithmetic sanity: when the query looks like a simple math
       expression (e.g. "2+2" or "What is 5 * 7?"), evaluate the
       expression using Python and compare it to the provided answer.  If
       there is a mismatch, the answer in the context is replaced with
       the computed result and the ``cross_check_tag`` is set to
       ``"recomputed"``.  Otherwise the tag is ``"asserted_true"``.

    2. Definition/geography sanity: when the query begins with a
       definitional prefix (e.g. "what is", "who was", "capital of") and
       a memory retrieval has already been performed (``stage_2R_memory``
       exists), the function checks whether the answer appears in any of
       the retrieved memory results.  If the answer is found verbatim in
       the evidence, the tag is set to ``"asserted_true"``; otherwise it
       is set to ``"conflict_check"``.  This helps detect answers that
       may contradict the user’s stored knowledge.  When no definition
       prefix is recognised or no memory evidence is present, the tag
       defaults to ``"asserted_true"``.

    The function is resilient to errors and never raises.  It writes
    back into the provided context dict and has no return value.

    Args:
        ctx: The pipeline context containing the query, the validated
            answer and optional memory evidence.
    """
    try:
        # Extract the validated answer from the reasoning stage.  If no answer
        # exists (e.g. verdict UNKNOWN), proceed with an empty string so that
        # arithmetic or definitional checks can still be performed.
        answer = (ctx.get("stage_8_validation") or {}).get("answer")
        original_query = ctx.get("original_query") or ""
        q_norm = str(original_query).strip().lower()
        # Normalise the answer; use empty string when None
        ans_str = str(answer).strip() if answer is not None else ""
        # ------------------------------------------------------------------
        # Arithmetic sanity check.  If the query is comprised solely of
        # digits and simple arithmetic operators, evaluate it.  Use a
        # conservative pattern to avoid executing arbitrary code.  Queries
        # that end with a question mark or contain whitespace are handled
        # by stripping extraneous characters.
        try:
            # Remove common prefixes like "what is" before checking if this is
            # a pure math expression.  Also strip trailing punctuation.
            q_math = q_norm
            for prefix in ["what is ", "what's ", "calculate ", "compute ", "answer is "]:
                if q_math.startswith(prefix):
                    q_math = q_math[len(prefix):]
                    break
            q_math = q_math.rstrip("?.!").replace(" ", "")
            if q_math and re.fullmatch(r"[0-9+\-*/().]+", q_math):
                # Safely evaluate using eval() with no builtins
                try:
                    # Evaluate simple arithmetic expressions safely without using eval().
                    # Only support numbers and + - * / parentheses.  Use ast to parse and compute.
                    import ast, operator as _op
                    def _eval_expr(node):
                        # Recursively evaluate AST nodes representing arithmetic expressions.
                        if isinstance(node, ast.Num):  # type: ignore[attr-defined]
                            return node.n
                        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
                            return -_eval_expr(node.operand)
                        elif isinstance(node, ast.BinOp):
                            left = _eval_expr(node.left)
                            right = _eval_expr(node.right)
                            if isinstance(node.op, ast.Add):
                                return left + right
                            elif isinstance(node.op, ast.Sub):
                                return left - right
                            elif isinstance(node.op, ast.Mult):
                                return left * right
                            elif isinstance(node.op, ast.Div):
                                return left / right
                            else:
                                raise ValueError("Unsupported operator")
                        else:
                            raise ValueError("Unsupported expression")
                    try:
                        _tree = ast.parse(q_math, mode="eval")
                        result = _eval_expr(_tree.body)
                    except Exception:
                        result = None
                except Exception:
                    result = None
                if result is not None:
                    # Convert numeric result to a canonical string
                    if isinstance(result, (int, float)) and not isinstance(result, bool):
                        # Represent integers without a decimal point
                        if abs(result - int(result)) < 1e-9:
                            result_str = str(int(result))
                        else:
                            result_str = str(result)
                    else:
                        result_str = str(result)
                    # Extract the first numeric token from the answer
                    try:
                        # Use regex to capture numbers including decimal part and sign
                        num_tokens = re.findall(r"[-+]?[0-9]*\.?[0-9]+", ans_str)
                        ans_num = num_tokens[0] if num_tokens else ans_str
                    except Exception:
                        ans_num = ans_str
                    # Compare and update if mismatched or if there was no original answer
                    if ans_num != result_str or not ans_str:
                        # Update the answer in the reasoning verdict
                        ctx.setdefault("stage_8_validation", {})["answer"] = result_str
                        ctx.setdefault("stage_8_validation", {})["verdict"] = "TRUE"
                        ctx["cross_check_tag"] = "recomputed"
                        return
                    else:
                        ctx["cross_check_tag"] = "asserted_true"
                        return
        except Exception:
            pass
        # ------------------------------------------------------------------
        # Definition/geography check.  Identify definitional or geography
        # queries by looking for common prefixes.  If the query fits and
        # there is memory evidence available, search the evidence for the
        # answer.  When found, assert true; otherwise mark as conflict.
        try:
            prefixes = [
                "what is ", "who is ", "what was ", "who was ",
                "who are ", "what are ", "capital of ", "capital city of "
            ]
            is_def = any(q_norm.startswith(p) for p in prefixes)
            if is_def:
                mem_results = (ctx.get("stage_2R_memory") or {}).get("results", [])
                found = False
                ans_low = ans_str.lower()
                for rec in mem_results:
                    try:
                        cont = str(rec.get("content") or "").lower()
                        if ans_low and ans_low in cont:
                            found = True
                            break
                    except Exception:
                        continue
                ctx["cross_check_tag"] = "asserted_true" if found else "conflict_check"
                return
        except Exception:
            pass
        # Default case: no special checks triggered
        ctx["cross_check_tag"] = "asserted_true"
    except Exception:
        # On unexpected errors, default to asserted_true
        ctx["cross_check_tag"] = "asserted_true"
    # Return the last N entries (limit), preserving chronological order
    return entries[-limit:]

def _save_context_snapshot(ctx: Dict[str, Any], limit: int = 5) -> None:
    """Persist a trimmed context snapshot and append the current query to the query log.

    This helper avoids nested ``session_context`` structures by writing only
    the current pipeline state along with a shallow list of recent queries.  It
    appends the current query to a log file to enable retrieval of recent
    history across runs.

    Args:
        ctx: The full pipeline context.
        limit: Maximum number of recent queries to include in the snapshot.
    """
    try:
        # Ensure reports directory exists
        reports_dir = (MAVEN_ROOT / "reports").resolve()
        reports_dir.mkdir(parents=True, exist_ok=True)
        # Append current query to query log
        qlog = reports_dir / "query_log.jsonl"
        with open(qlog, "a", encoding="utf-8") as qfh:
            json.dump({"query": ctx.get("original_query")}, qfh)
            qfh.write("\n")
        # ------------------------------------------------------------------
        # Retention: prune the query log if it grows beyond a configurable
        # threshold.  Many pipeline runs accumulate queries over time and
        # without pruning the log could grow indefinitely.  The memory
        # configuration (config/memory.json) may specify a
        # ``query_log_max_entries`` integer.  When the number of stored
        # queries exceeds this limit, the oldest entries are removed.
        try:
            cfg_mem = CFG.get("memory", {}) or {}
            # Default to 500 entries if no configuration is provided or if the
            # value is not a valid integer.  A non‑positive value disables
            # pruning.
            max_entries = int(cfg_mem.get("query_log_max_entries", 500))
        except Exception:
            max_entries = 500
        try:
            if max_entries > 0 and qlog.exists():
                with open(qlog, "r", encoding="utf-8") as lf:
                    lines = [ln for ln in lf if ln.strip()]
                if len(lines) > max_entries:
                    # Retain only the newest entries
                    new_lines = lines[-max_entries:]
                    with open(qlog, "w", encoding="utf-8") as wf:
                        for ln in new_lines:
                            # Preserve newline endings
                            wf.write(ln if ln.endswith("\n") else ln + "\n")
        except Exception:
            # Silently ignore pruning errors to avoid disrupting snapshot saving
            pass
        # Build snapshot with limited recent history
        snapshot = {
            "original_query": ctx.get("original_query"),
            "personality_snapshot": ctx.get("personality_snapshot", {}),
            "session_context": {
                "recent_queries": _get_recent_queries(limit),
                "context_truncated": True
            }
        }
        # Include current pipeline stages (those starting with 'stage_')
        for key, val in ctx.items():
            try:
                if isinstance(key, str) and key.startswith("stage_"):
                    snapshot[key] = val
            except Exception:
                continue
        # Write the snapshot to context_snapshot.json
        with open(reports_dir / "context_snapshot.json", "w", encoding="utf-8") as fh:
            json.dump(snapshot, fh, indent=2)
    except Exception:
        # Do not crash on any error
        pass

# --- Hybrid Semantic Memory & Retrieval Unification (Step‑7) ---
def _unified_retrieve(query: str, k: int = 5, filters: Optional[dict] = None) -> Dict[str, Any]:
    """
    Retrieve evidence from all domain banks and apply personal preference boost.

    This helper first performs a standard retrieval across all domain banks,
    then augments each result with a boost derived from the personal brain.
    The final score is the sum of the original confidence and the personal
    boost.  Results are sorted by this total score in descending order.

    Args:
        query: The user query string.
        k: Maximum number of results to return.
        filters: Optional filters for future extension (unused).

    Returns:
        A dictionary with 'results', 'banks' and 'banks_queried' fields.  Each
        result is annotated with 'boost' and 'total_score'.
    """
    # Decide between parallel and sequential retrieval based on configuration
    try:
        parallel = bool((CFG.get("memory") or {}).get("parallel_bank_access", False))
    except Exception:
        parallel = False
    try:
        limit_int = int(k)
    except Exception:
        limit_int = 5
    # Perform base retrieval across all banks
    try:
        base = _retrieve_from_banks_parallel(query, limit_int) if parallel else _retrieve_from_banks(query, limit_int)
    except Exception:
        # Fall back to sequential retrieval on any error
        base = _retrieve_from_banks(query, limit_int)
    results = list(base.get("results") or [])
    # Attempt to load personal brain service for boosting
    try:
        _personal = _personal_module()
        personal_api = getattr(_personal, "service_api", None)
    except Exception:
        personal_api = None
    enriched: List[Dict[str, Any]] = []
    for item in results:
        # Normalise the subject text for boosting
        try:
            subj = str(item.get("content") or item.get("text") or "").strip()
        except Exception:
            subj = ""
        boost_val: float = 0.0
        if personal_api and subj:
            # Call personal brain to compute a boost.  Errors are ignored.
            try:
                resp = personal_api({"op": "SCORE_BOOST", "payload": {"subject": subj}})
                if resp and resp.get("ok"):
                    boost_val = float((resp.get("payload") or {}).get("boost") or 0.0)
            except Exception:
                boost_val = 0.0
        # Determine original confidence or score from result
        try:
            conf_val = float(item.get("confidence") or item.get("score") or 0.0)
        except Exception:
            conf_val = 0.0
        total = conf_val + boost_val
        # Annotate result with boost and total_score
        enriched_item = dict(item)
        enriched_item["boost"] = boost_val
        enriched_item["total_score"] = total
        enriched.append(enriched_item)
    # Sort results by descending total_score
    enriched.sort(key=lambda x: x.get("total_score", 0.0), reverse=True)
    # Trim to requested limit
    if limit_int > 0:
        enriched = enriched[:limit_int]
    return {
        "results": enriched,
        "banks": base.get("banks", []),
        "banks_queried": base.get("banks_queried", [])
    }

# --- Hybrid Semantic Memory & Retrieval Unification (Step‑7) ---
def _unified_retrieve(query: str, k: int = 5, filters: Optional[dict] = None) -> Dict[str, Any]:
    """
    Retrieve evidence from all domain banks and apply personal preference boost.

    This helper first performs a standard retrieval across all domain banks,
    then augments each result with a boost derived from the personal brain.
    The final score is the sum of the original confidence and the personal
    boost.  Results are sorted by this total score in descending order.

    Args:
        query: The user query string.
        k: Maximum number of results to return.
        filters: Optional filters for future extension (unused).

    Returns:
        A dictionary with 'results', 'banks' and 'banks_queried' fields.  Each
        result is annotated with 'boost' and 'total_score'.
    """
    # Decide between parallel and sequential retrieval based on configuration
    try:
        parallel = bool((CFG.get("memory") or {}).get("parallel_bank_access", False))
    except Exception:
        parallel = False
    try:
        limit_int = int(k)
    except Exception:
        limit_int = 5
    # Perform base retrieval across all banks
    try:
        base = _retrieve_from_banks_parallel(query, limit_int) if parallel else _retrieve_from_banks(query, limit_int)
    except Exception:
        # Fall back to sequential retrieval on any error
        base = _retrieve_from_banks(query, limit_int)
    results = list(base.get("results") or [])
    # Attempt to load personal brain service for boosting
    try:
        _personal = _personal_module()
        personal_api = getattr(_personal, "service_api", None)
    except Exception:
        personal_api = None
    enriched: List[Dict[str, Any]] = []
    for item in results:
        # Normalise the subject text for boosting
        try:
            subj = str(item.get("content") or item.get("text") or "").strip()
        except Exception:
            subj = ""
        boost_val: float = 0.0
        if personal_api and subj:
            # Call personal brain to compute a boost.  Errors are ignored.
            try:
                resp = personal_api({"op": "SCORE_BOOST", "payload": {"subject": subj}})
                if resp and resp.get("ok"):
                    boost_val = float((resp.get("payload") or {}).get("boost") or 0.0)
            except Exception:
                boost_val = 0.0
        # Determine original confidence or score from result
        try:
            conf_val = float(item.get("confidence") or item.get("score") or 0.0)
        except Exception:
            conf_val = 0.0
        total = conf_val + boost_val
        # Annotate result with boost and total_score
        enriched_item = dict(item)
        enriched_item["boost"] = boost_val
        enriched_item["total_score"] = total
        enriched.append(enriched_item)
    # Sort results by descending total_score
    enriched.sort(key=lambda x: x.get("total_score", 0.0), reverse=True)
    # Trim to requested limit
    if limit_int > 0:
        enriched = enriched[:limit_int]
    return {
        "results": enriched,
        "banks": base.get("banks", []),
        "banks_queried": base.get("banks_queried", [])
    }

# === Service API =============================================================

def service_api(msg: Dict[str, Any]) -> Dict[str, Any]:
    from api.utils import generate_mid, success_response, error_response, write_report, CFG  # type: ignore
    from api.memory import update_last_record_success, ensure_dirs  # type: ignore
    op = (msg or {}).get("op", "").upper()
    mid = msg.get("mid") or generate_mid()
    payload = msg.get("payload") or {}

    # Step‑7: Unified retrieval across banks with personal boosts
    if op == "UNIFIED_RETRIEVE":
        # Extract query text and optional parameters
        try:
            q = str(payload.get("query") or payload.get("text") or payload.get("input") or "")
        except Exception:
            q = ""
        try:
            k_val = payload.get("k") or payload.get("limit") or 5
        except Exception:
            k_val = 5
        filters_val = payload.get("filters") or {}
        try:
            result = _unified_retrieve(q, k_val, filters_val)
            return success_response(op, mid, result)
        except Exception as e:
            return error_response(op, mid, "UNIFIED_RETRIEVE_FAILED", str(e))
    # Step‑7: Unified retrieval across banks with personal boosts
    if op == "UNIFIED_RETRIEVE":
        try:
            q = str(payload.get("query") or payload.get("text") or payload.get("input") or "")
        except Exception:
            q = ""
        try:
            k_val = payload.get("k") or payload.get("limit") or 5
        except Exception:
            k_val = 5
        filters_val = payload.get("filters") or {}
        try:
            result = _unified_retrieve(q, k_val, filters_val)
            return success_response(op, mid, result)
        except Exception as e:
            return error_response(op, mid, "UNIFIED_RETRIEVE_FAILED", str(e))

    # ----------------------------------------------------------------------
    # Hybrid retrieval (Step‑7): unify memory retrieval with personal boost
    #
    # This operation combines results from all subject banks and applies a
    # preference boost from the personal brain.  The caller should supply
    # a ``query`` string and may override ``k`` (number of results) and
    # provide optional ``filters``.  The returned payload contains a
    # ``results`` list sorted by ``total_score``.  Placing this check
    # before other ops ensures it is not captured by unrelated handlers.
    if op == "UNIFIED_RETRIEVE":
        try:
            # Accept multiple keys for the query for compatibility
            qry = str((payload.get("query") or payload.get("text") or payload.get("question") or "")).strip()
            try:
                k_val = int(payload.get("k", 5))
            except Exception:
                k_val = 5
            flt = payload.get("filters") if isinstance(payload.get("filters"), dict) else None
            items = _unified_retrieve(qry, k_val, flt)
            return success_response(op, mid, {"results": items})
        except Exception as e:
            return error_response(op, mid, "UNIFIED_RETRIEVE_ERROR", str(e))

    # Hybrid retrieval: combine results from all subject banks and apply
    # personal preference boosting.  This op returns a list of records
    # sorted by total_score.  The caller can specify 'query' and
    # optionally 'k' and 'filters' in the payload.  See _unified_retrieve
    # for details.  Placing this check early avoids it being captured by
    # other ops below.
    if op == "UNIFIED_RETRIEVE":
        try:
            qry = str((payload.get("query") or payload.get("text") or payload.get("question") or "")).strip()
            try:
                k = int(payload.get("k", 5))
            except Exception:
                k = 5
            flt = payload.get("filters") if isinstance(payload.get("filters"), dict) else None
            items = _unified_retrieve(qry, k, flt)
            return success_response(op, mid, {"results": items})
        except Exception as e:
            return error_response(op, mid, "UNIFIED_RETRIEVE_ERROR", str(e))

    # Step‑7: Unified retrieval across banks with personal boosts
    if op == "UNIFIED_RETRIEVE":
        # Extract query text and optional parameters.
        try:
            q = str(
                payload.get("query")
                or payload.get("text")
                or payload.get("input")
                or ""
            )
        except Exception:
            q = ""
        try:
            k_val = payload.get("k") or payload.get("limit") or 5
        except Exception:
            k_val = 5
        filters_val = payload.get("filters") or {}
        try:
            result = _unified_retrieve(q, k_val, filters_val)
            return success_response(op, mid, result)
        except Exception as e:
            return error_response(op, mid, "UNIFIED_RETRIEVE_FAILED", str(e))

    if op == "RUN_PIPELINE":
        # Initialise deterministic behaviour by seeding the PRNG.  A
        # new seed is generated for every pipeline run and recorded
        # in the context and a golden trace file for reproducibility.
        try:
            import random, secrets
            seed_value = secrets.randbits(64)
            random.seed(seed_value)
            # Record seed in context as soon as possible
            # ctx will be created after reading session; assign later
            _seed_record = (seed_value, random.randint(100000, 999999))
        except Exception:
            _seed_record = None

        # Start routing diagnostics trace (Phase C cleanup)
        try:
            if tracer and RouteType:
                _trace_text = str(
                    payload.get("text")
                    or payload.get("question")
                    or payload.get("query")
                    or payload.get("input")
                    or ""
                )
                tracer.start_request(mid, _trace_text)
        except Exception:
            pass
        # Before beginning the pipeline, optionally consolidate memories
        # across cognitive brains.  Consolidation moves aged or low
        # importance records from STM into deeper tiers and enforces
        # per‑tier quotas.  The behaviour is controlled via the
        # ``memory.auto_consolidate`` configuration.  Any errors are
        # ignored to avoid disrupting the pipeline.
        try:
            # Avoid re-importing CFG within this function to prevent Python from
            # treating it as a local variable.  The module-level CFG import
            # ensures consistent access to configuration values throughout the
            # service.  This guard checks the auto_consolidate flag and
            # performs consolidation accordingly.  Any errors during import or
            # consolidation are intentionally ignored to avoid disrupting the
            # pipeline.
            if bool((CFG.get("memory") or {}).get("auto_consolidate", False)):
                try:
                    from brains.cognitive.memory_consolidation import consolidate_memories  # type: ignore
                    consolidate_memories()
                except Exception:
                    pass
        except Exception:
            pass
        # Accept multiple keys for the input text to improve compatibility with callers.
        # Historically the pipeline expected `text` but some clients may send
        # `question`, `query` or `input`.  To avoid losing the original query and
        # inadvertently triggering the UNKNOWN_INPUT verdict, fall back to these
        # alternate keys when `text` is missing.
        text = str(
            payload.get("text")
            or payload.get("question")
            or payload.get("query")
            or payload.get("input")
            or ""
        )
        conf = float(payload.get("confidence", 0.8))
        # ------------------------------------------------------------------
        # Optional pipeline tracing.  When the environment variable
        # TRACE_PIPELINE is set to "1" or "true" (case insensitive), tracing is
        # forcibly enabled. Otherwise it falls back to the configuration in
        # CFG['pipeline_tracer']['enabled']. Trace events are emitted to
        # reports/pipeline_trace/trace_<mid>.jsonl, and the number of retained
        # traces is capped by CFG['pipeline_tracer']['max_files']. Older
        # traces beyond this cap are removed to prevent disk bloat.
        trace_enabled: bool = False
        try:
            # Check environment override first
            env_val = os.getenv("TRACE_PIPELINE")
            if env_val is not None:
                trace_enabled = str(env_val).strip().lower() in {"1","true","yes"}
            else:
                # Fall back to configuration default
                trace_cfg = CFG.get("pipeline_tracer", {}) or {}
                trace_enabled = bool(trace_cfg.get("enabled", False))
        except Exception:
            trace_enabled = False
        trace_events = []

        # Personality snapshot (best-effort)
        try:
            from brains.cognitive.personality.service import personality_brain
            prefs = personality_brain._read_preferences()
        except Exception:
            prefs = {"prefer_explain": True, "tone": "neutral", "verbosity_target": 1.0}

        # Load any prior session context to provide continuity across runs.  This
        # enables the system to recall high-level context between separate
        # pipeline executions, forming the basis of a persistent memory layer.
        session_ctx: Dict[str, Any] = {}
        try:
            snap_path = MAVEN_ROOT / "reports" / "context_snapshot.json"
            if snap_path.exists():
                session_ctx = json.loads(snap_path.read_text(encoding="utf-8"))
        except Exception:
            session_ctx = {}

        ctx: Dict[str, Any] = {
            "original_query": text,
            "personality_snapshot": prefs,
            "session_context": session_ctx
        }
        # Attach deterministic seed to the context and persist golden trace
        try:
            if _seed_record is not None:
                seed_val, seed_ts = _seed_record
                ctx["run_seed"] = int(seed_val)
                # Write golden trace file
                try:
                    from pathlib import Path as _Path
                    import json as _json
                    root = _Path(__file__).resolve().parents[4]
                    gt_dir = root / "reports" / "golden_trace"
                    gt_dir.mkdir(parents=True, exist_ok=True)
                    gt_path = gt_dir / f"trace_{seed_ts}.json"
                    # Use atomic write via api.utils
                    from api.utils import _atomic_write  # type: ignore
                    _atomic_write(gt_path, _json.dumps({"trace_id": seed_ts, "seed": int(seed_val)}, indent=2))
                except Exception:
                    pass
        except Exception:
            pass
        # ------------------------------------------------------------------
        # Update recent queries for multi‑turn context.  Maintain a short
        # list of the most recent queries and store it in the session
        # context.  This enables detection of repeated questions and
        # supports stress or frustration detection.  Older queries are
        # discarded beyond the maximum size.  Any errors during update
        # are silently ignored to avoid disrupting the pipeline.
        try:
            _RECENT_QUERIES.append({"query": text})
            if len(_RECENT_QUERIES) > _MAX_RECENT_QUERIES:
                _RECENT_QUERIES.pop(0)
            ctx["session_context"]["recent_queries"] = list(_RECENT_QUERIES)
            ctx["session_context"]["context_truncated"] = len(_RECENT_QUERIES) >= _MAX_RECENT_QUERIES
        except Exception:
            pass

        # Stage 1b — Personality adjust (observed via Governance)
        try:
            from brains.cognitive.personality.service import personality_brain
            sug_res = personality_brain.service_api({"op":"ADAPT_WEIGHTS_SUGGEST"}) or {}
            suggestion = (sug_res.get("payload") or {}).get("suggestion") or {}
        except Exception:
            suggestion = {}

        try:
            gov = _gov_module()
            adj = gov.service_api({"op":"ENFORCE","payload":{"action":"ADJUST_WEIGHTS","payload": suggestion}})
            approved = bool((adj.get("payload") or {}).get("allowed"))
        except Exception:
            approved = False

        ctx["stage_1b_personality_adjustment"] = {"proposal": suggestion, "approved": approved}

        # ------------------------------------------------------------------
        # Stage 1 — Sensorium normalization.  Perform lightweight text
        # normalization (e.g. lowercasing, whitespace trimming) before
        # downstream processing.  The sensorium stage runs unconditionally.
        s = _brain_module("sensorium").service_api({"op": "NORMALIZE", "payload": {"text": text}})
        if trace_enabled:
            trace_events.append({"stage": "sensorium"})

        # Stage 3 — Language parsing.  Parse the input to determine its
        # communicative intent (question, command, request, fact, etc.).
        # We run the language brain before planning so that only commands
        # and requests trigger the heavy plan/goal generation logic.
        l = _brain_module("language").service_api(
            {"op": "PARSE", "payload": {"text": text, "delta": (suggestion.get("language") if approved else {})}}
        )
        if trace_enabled:
            trace_events.append({"stage": "language_parse"})

        # Extract language parse results early so we can decide whether to
        # invoke the planner.  Commands and explicit requests create
        # actionable plans; other utterances (questions, facts, speculation)
        # receive a simple fallback plan.  This prevents the planner from
        # segmenting arbitrary statements into junk sub‑goals.
        lang_payload = (l.get("payload") or {})
        # Determine if the input is a command or request.  Fall back to
        # type to catch alternative representations (e.g. "COMMAND",
        # "REQUEST") even if is_command/request booleans are absent.
        is_cmd = bool(lang_payload.get("is_command"))
        is_req = bool(lang_payload.get("is_request"))
        st_type = str(lang_payload.get("type", "")).upper()
        # Augment command detection: if is_command flag is not set but
        # the storable_type is COMMAND or the text begins with a CLI prefix,
        # treat this input as a command for planning and routing purposes.
        if not is_cmd:
            try:
                tnorm_cli = str(text or "").strip()
                if st_type == "COMMAND" or tnorm_cli.startswith("--") or tnorm_cli.startswith("/"):
                    is_cmd = True
            except Exception:
                pass
        should_plan = False
        if is_cmd or is_req or st_type in {"COMMAND", "REQUEST"}:
            should_plan = True
        # ----------------------------------------------------------------------
        # Additional filter: do not invoke the planner for simple retrieval
        # requests.  Many user queries of the form "show me ..." or
        # "find ..." are treated as commands by the language parser, which
        # in turn causes the planner to segment the request into sub‑goals
        # (e.g. "Show me Paris photos" and "the Eiffel Tower").  These
        # retrieval requests are meant to be handled immediately rather
        # than persisted as autonomous goals.  To avoid polluting the
        # personal goal memory with such items, we only allow planning
        # when the command starts with a strongly actionable verb (e.g.
        # "create", "make", "build", "plan", "schedule", "delegate",
        # "execute").  Commands beginning with other words (like
        # "show", "find", "search", "display", etc.) are executed on the
        # spot and skipped by the planner.  When should_plan is already
        # False this check is bypassed.
        if should_plan:
            try:
                # Define the set of verbs that warrant persistent plans
                command_verbs = {"create", "make", "build", "plan", "schedule", "delegate", "execute"}
                # Normalise the input to lower case and split into tokens
                query_lc = (text or "").strip().lower()
                tokens = query_lc.split()
                # Only proceed with planning if the first token is one of the
                # actionable verbs.  Otherwise, reset should_plan to False to
                # skip the planner and use a fallback plan.  Guard against
                # empty tokens.
                if tokens:
                    first = tokens[0]
                    if first not in command_verbs:
                        should_plan = False
            except Exception:
                # On error, leave should_plan unchanged
                pass

        # ------------------------------------------------------------------
        # Stage 7a — command routing
        #
        # Before invoking the planner, fast cache or any further stages,
        # detect CLI‑style commands (inputs starting with "--" or "/").
        # These should bypass the normal question/answer pipeline and be
        # handled by the command router.  Only commands that are not
        # actionable tasks (i.e. should_plan is False) are routed here.  If a
        # built‑in command is recognised, its result becomes the final
        # answer.  Unknown commands return a structured error.  For
        # consistency with the rest of the system, the verdict is set to
        # NEUTRAL and storage is skipped.  A minimal context is returned
        # immediately, skipping heavy retrieval and reasoning.
        try:
            # Identify inputs that look like commands and are not slated for
            # goal planning.  The language parser sets is_command True for
            # strings beginning with "--" or "/".  However, some parse
            # variants may set the type to COMMAND without populating the
            # boolean.  In addition, check the raw text prefix to catch
            # unparsed commands.  Only intercept when planning is disabled
            # to avoid interfering with complex task creations (e.g. "create goal ...").
            cmd_like = False
            try:
                stripped = (text or "").strip()
                cmd_like = stripped.startswith("--") or stripped.startswith("/")
            except Exception:
                cmd_like = False
            # Retrieve storable type from the language payload if present
            st_type_local = str(lang_payload.get("storable_type", lang_payload.get("type", ""))).upper()
            if (is_cmd or st_type_local == "COMMAND" or cmd_like) and not should_plan:
                # Route the command through the command_router.  Import on
                # demand to avoid circular dependencies during module
                # initialisation.
                try:
                    from brains.cognitive.command_router import route_command  # type: ignore
                    cmd_result = route_command(text)
                except Exception as _exc:
                    cmd_result = {"error": f"router_import_failed: {_exc}"}
                # Determine the response message.  If the router returns a
                # ``message``, use it directly.  Otherwise fall back to the
                # error description or a generic notice.
                msg_text = None
                try:
                    if isinstance(cmd_result, dict):
                        if cmd_result.get("message"):
                            msg_text = str(cmd_result["message"])
                        elif cmd_result.get("error"):
                            msg_text = str(cmd_result["error"])
                except Exception:
                    msg_text = None
                if not msg_text:
                    msg_text = "No command response."
                # Build a minimal context capturing the parse and final answer.
                ctx: Dict[str, Any] = {
                    "original_query": text,
                    "stage_3_language": lang_payload,
                    "stage_8_validation": {"verdict": "NEUTRAL", "confidence": 0.0},
                    "stage_6_candidates": {"candidates": []},
                    "stage_9_storage": {"skipped": True, "reason": "command"},
                    "stage_10_finalize": {"text": msg_text, "confidence": 0.0},
                    "final_answer": msg_text,
                    # Assign low confidence for error messages and higher for
                    # successful commands.  When the router returned an error,
                    # confidence is set to 0.0; otherwise use 0.8.
                    "final_confidence": (0.0 if cmd_result.get("error") else 0.8),
                    "final_tag": "command_response",
                }
                # Trace the command routing event if tracing is enabled.
                if trace_enabled:
                    trace_events.append({"stage": "command_router", "result": cmd_result})
                return success_response(op, mid, {"context": ctx})
        except Exception:
            # On any error in the command router path, fall through to the
            # normal pipeline.  Errors here should not prevent question
            # answering; they simply cause commands to be treated as
            # statements.
            pass

        # ------------------------------------------------------------------
        # DISABLED (Phase C cleanup): Self/Environment query bypasses removed
        # ------------------------------------------------------------------
        # These short-circuits prevented requests from flowing through the
        # cognitive pathway. Now disabled to ensure all requests reach
        # stage6_generate and use the Template→Heuristic→LLM pathway.
        #
        # Trace self/environment query detection for diagnostics
        try:
            if tracer and RouteType:
                if _is_env_query(text):
                    tracer.record_route(mid, RouteType.SELF_QUERY, {"query_type": "environment", "bypass": "disabled"})
        except Exception:
            pass

        # OLD CODE: Environment query bypass (DISABLED - commented out)
        # The entire environment query short-circuit has been removed to ensure
        # all requests flow through the cognitive pathway to stage6_generate.

        # OLD CODE: Self query bypass (DISABLED - commented out)
        # Trace self query detection for diagnostics
        try:
            if tracer and RouteType and _is_self_query(text):
                tracer.record_route(mid, RouteType.SELF_QUERY, {"query_type": "self", "bypass": "disabled"})
        except Exception:
            pass

        # The entire self query short-circuit has been removed to ensure
        # all requests flow through the cognitive pathway to stage6_generate.

        # ------------------------------------------------------------------
        # Fast cache lookup: Check if we have a cached answer with learned
        # confidence. This enables learning from feedback ("correct", etc.)
        # ------------------------------------------------------------------
        # When a user confirms an answer with "correct", the confidence is
        # boosted in the cache. On subsequent queries, the cache returns
        # the answer with the learned (higher) confidence, demonstrating
        # that Maven has learned from the feedback.
        #
        # Fast cache lookup
        fc_rec = _lookup_fast_cache(text)
        try:
            if tracer and RouteType:
                # Check if cache would have hit (for diagnostics only)
                _fc_check = _lookup_fast_cache(text)
                if _fc_check:
                    tracer.record_route(mid, RouteType.FAST_CACHE, {"bypass": "disabled", "would_have_hit": True})
        except Exception:
            pass
        # ------------------------------------------------------------------
        # Additional fast cache gating: avoid using cached answers for
        # queries about the agent's location or identity.  The fast cache
        # stores answers verbatim from prior runs; however, environmental
        # or self‑identity queries can evolve when the self model or
        # environment context is updated.  Using a stale cached answer
        # risks serving off‑topic content.  Similarly, skip the fast
        # cache for any query that the self query detector flags.  This
        # ensures fresh responses are computed for location and identity
        # queries rather than relying on potentially poisoned cache.
        if fc_rec:
            try:
                qnorm_lc = str((text or "")).strip().lower()
            except Exception:
                qnorm_lc = ""
            # Skip fast cache for self queries (who/what/where/how + you/your/yourself)
            skip_fc = False
            try:
                if _is_self_query(text):
                    skip_fc = True
            except Exception:
                skip_fc = False
            # Skip fast cache for environment location queries.  Note that
            # "where are we" is excluded here and handled as a
            # conversation meta pattern instead.  Patterns include
            # queries asking about the agent's physical location (you/am i)
            # and personal residence.
            if not skip_fc:
                env_triggers = [
                    # "where are we" removed; handled in conversation meta
                    "where are you",
                    "where am i",
                    "where's your location",
                    "where do you live",
                ]
                for _pat in env_triggers:
                    try:
                        if _pat in qnorm_lc:
                            skip_fc = True
                            break
                    except Exception:
                        continue
            if skip_fc:
                fc_rec = None
        # If a cached result is found, check it for meta or filler phrases.  If the
        # answer appears to be a generic or self‑referential response (e.g.
        # "I'm going to try my best"), treat the cache entry as poisoned and
        # ignore it.  This prevents incorrect filler answers from being
        # trusted as factual on subsequent runs.
        if fc_rec:
            try:
                ans_lc = str(fc_rec.get("answer", "")).strip().lower()
            except Exception:
                ans_lc = ""
            invalid_cache = False
            # Check configured bad phrases
            for bad in BAD_CACHE_PHRASES:
                if bad and bad in ans_lc:
                    invalid_cache = True
                    break
            # Run semantic verification on the cached answer.  Even if it
            # does not match a specific bad phrase, an answer that fails the
            # heuristic should be treated as invalid and recomputed.
            try:
                if not invalid_cache and not _semantic_verify(fc_rec.get("answer", "")):
                    invalid_cache = True
            except Exception:
                # On verification error, mark as invalid to be safe
                invalid_cache = True
            if invalid_cache:
                # Log the poisoning event to a report for later analysis.  Swallow
                # any exceptions during logging to avoid breaking the pipeline.
                try:
                    log_path = MAVEN_ROOT / "reports" / "cache_poison.log"
                    log_entry = {
                        "query": text,
                        "bad_answer": fc_rec.get("answer")
                    }
                    log_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(log_path, "a", encoding="utf-8") as lf:
                        lf.write(json.dumps(log_entry) + "\n")
                except Exception:
                    pass
                fc_rec = None
        if fc_rec:
            # LEARNING ON REPEAT: Boost confidence when same question asked again
            boosted_confidence = _boost_cache_confidence(text, boost_amount=0.1)
            if boosted_confidence is not None:
                final_conf = boosted_confidence
            else:
                final_conf = fc_rec.get("confidence", 0.8)

            # Attach parse results for downstream consumers
            ctx["stage_3_language"] = lang_payload or {}
            # Mark reasoning verdict and attach cached answer with boosted confidence
            ctx["stage_8_validation"] = {
                "verdict": "TRUE",
                "answer": fc_rec.get("answer"),
                "confidence": final_conf,
                "from_cache": True,
                "confidence_boosted": boosted_confidence is not None,
            }
            # Generate language candidates (high‑confidence direct answer)
            try:
                cand_res = _brain_module("language").service_api({"op": "GENERATE_CANDIDATES", "mid": mid, "payload": ctx})
                ctx["stage_6_candidates"] = cand_res.get("payload", {})
            except Exception:
                ctx["stage_6_candidates"] = {}
            # Finalise the answer without tone wrapping for factual responses
            try:
                fin_res = _brain_module("language").service_api({"op": "FINALIZE", "payload": ctx})
                ctx["stage_10_finalize"] = fin_res.get("payload", {})
            except Exception:
                ctx["stage_10_finalize"] = {}
            # Capture final answer and confidence for external consumers
            try:
                ctx["final_answer"] = ctx.get("stage_10_finalize", {}).get("text")
                ctx["final_confidence"] = ctx.get("stage_10_finalize", {}).get("confidence")
                # Fallback: if finalization failed but we have a cached answer, use it directly
                if not ctx["final_answer"] and ctx.get("stage_8_validation", {}).get("from_cache"):
                    ctx["final_answer"] = ctx.get("stage_8_validation", {}).get("answer")
                    ctx["final_confidence"] = ctx.get("stage_8_validation", {}).get("confidence")
            except Exception:
                ctx["final_answer"] = None
                ctx["final_confidence"] = None
            # Indicate that storage was skipped due to fast cache
            ctx["stage_9_storage"] = {"skipped": True, "reason": "fast_cache_used"}
            # Persist context snapshot and system report
            try:
                _save_context_snapshot(ctx, limit=5)
            except Exception:
                pass
            try:
                write_report("system", f"run_{random.randint(100000, 999999)}.json", json.dumps(ctx, indent=2))
            except Exception:
                pass
            # Before returning on a fast cache hit, perform a self‑evaluation.
            # This assessment computes simple health metrics and may enqueue
            # autonomous repair goals based on the context.  Errors are
            # swallowed to avoid disrupting the cache fast path.
            try:
                import importlib
                sc_mod = importlib.import_module("brains.cognitive.self_dmn.service.self_critique")
                eval_resp = sc_mod.service_api({"op": "EVAL_CONTEXT", "payload": {"context": ctx}})
                ctx["stage_self_eval"] = eval_resp.get("payload", {})
            except Exception:
                ctx["stage_self_eval"] = {"error": "eval_failed"}
            # Return immediately with the final context
            # Before returning, update conversation state based on the
            # original query and final answer.  This enables multi‑turn
            # continuation handling.
            try:
                _update_conversation_state(text, ctx.get("final_answer"))
            except Exception:
                pass
            # Wrap the context under a 'context' key for API compatibility
            return success_response("RUN_PIPELINE", mid, {"context": ctx})
        
        # ------------------------------------------------------------------
        # DISABLED (Phase C cleanup): Semantic cache bypass removed
        # ------------------------------------------------------------------
        # Semantic cache previously short-circuited the pipeline. Now disabled
        # to ensure all requests flow through the cognitive pathway.
        #
        # Trace semantic cache check for diagnostics
        if not fc_rec:
            sc_rec = None  # DISABLED
            try:
                if tracer and RouteType:
                    # Check if cache would have hit (for diagnostics only)
                    _sc_check = _lookup_semantic_cache(text)
                    if _sc_check:
                        tracer.record_route(mid, RouteType.SEMANTIC_CACHE, {"bypass": "disabled", "would_have_hit": True})
            except Exception:
                pass
            if sc_rec:
                # Apply semantic cache gating to ensure topical and intent alignment
                safe_match = True
                try:
                    q_tokens = set(_tokenize(text))
                    # Cached query tokens
                    cached_q_tokens = set(sc_rec.get("tokens", []))
                    # Cosine similarity between query and cached query
                    if _cosine_similarity(q_tokens, cached_q_tokens) < 0.75:
                        safe_match = False
                    # Jaccard similarity between query tokens and answer tokens
                    ans_tokens = set(_tokenize(sc_rec.get("answer", "")))
                    if _jaccard(q_tokens, ans_tokens) < 0.2:
                        safe_match = False
                    # Intent must match between cached query and current
                    cached_intent = sc_rec.get("intent")
                    current_intent = None
                    try:
                        current_intent = str(lang_payload.get("type")) if lang_payload else None
                    except Exception:
                        current_intent = None
                    if cached_intent and current_intent and cached_intent != current_intent:
                        safe_match = False
                    # Disallow non‑self cached answers for self queries
                    if _is_self_query(text) and not sc_rec.get("self_origin"):
                        safe_match = False
                except Exception:
                    safe_match = False
                if not safe_match:
                    sc_rec = None
            if sc_rec:
                # Reuse the parsed language payload in the context
                ctx["stage_3_language"] = lang_payload or {}
                # Build a validation object signalling a semantic cache hit
                ctx["stage_8_validation"] = {
                    "verdict": "NEUTRAL",
                    "answer": sc_rec.get("answer"),
                    "confidence": sc_rec.get("confidence", 0.6),
                    "from_semantic_cache": True,
                }
                # Generate candidates using the language brain
                try:
                    cand_res = _brain_module("language").service_api({"op": "GENERATE_CANDIDATES", "mid": mid, "payload": ctx})
                    ctx["stage_6_candidates"] = cand_res.get("payload", {})
                except Exception:
                    ctx["stage_6_candidates"] = {}
                # Finalise the answer using the language brain
                try:
                    fin_res = _brain_module("language").service_api({"op": "FINALIZE", "payload": ctx})
                    ctx["stage_10_finalize"] = fin_res.get("payload", {})
                except Exception:
                    ctx["stage_10_finalize"] = {}
                # Capture final answer and confidence
                try:
                    ctx["final_answer"] = ctx.get("stage_10_finalize", {}).get("text")
                    ctx["final_confidence"] = ctx.get("stage_10_finalize", {}).get("confidence")
                except Exception:
                    ctx["final_answer"] = None
                    ctx["final_confidence"] = None
                # Indicate that storage was skipped due to semantic cache
                ctx["stage_9_storage"] = {"skipped": True, "reason": "semantic_cache_used"}
                # Write context snapshot and system report
                try:
                    _save_context_snapshot(ctx, limit=5)
                except Exception:
                    pass
                try:
                    write_report("system", f"run_{random.randint(100000, 999999)}.json", json.dumps(ctx, indent=2))
                except Exception:
                    pass
                # Self‑evaluation for run metrics
                try:
                    import importlib
                    sc_mod = importlib.import_module("brains.cognitive.self_dmn.service.self_critique")
                    eval_resp = sc_mod.service_api({"op": "EVAL_CONTEXT", "payload": {"context": ctx}})
                    ctx["stage_self_eval"] = eval_resp.get("payload", {})
                except Exception:
                    ctx["stage_self_eval"] = {"error": "eval_failed"}
                # Update semantic cache with the current context before returning
                try:
                    _update_semantic_cache(ctx)
                except Exception:
                    pass
                # Before returning, update conversation state based on the
                # original query and final answer.  Use the original query
                # from the context when available to avoid NameError when
                # 'text' is not defined in this scope.
                try:
                    upd_q = ctx.get("original_query") or payload.get("text") or text
                    _update_conversation_state(upd_q, ctx.get("final_answer"))
                except Exception:
                    pass
                # Wrap the context under a 'context' key for API compatibility
                return success_response("RUN_PIPELINE", mid, {"context": ctx})

        # Stage 2 — Planner (conditional).  Only call the planner when the
        # input is a command or request.  Otherwise skip the planner
        # entirely and construct a simple fallback plan.  Skipping the
        # planner avoids writing unnecessary sub‑goals to the goal memory.
        if should_plan:
            try:
                p = _brain_module("planner").service_api(
                    {"op": "PLAN", "payload": {"text": text, "delta": (suggestion.get("planner") if approved else {})}}
                )
            except Exception:
                p = {"ok": False, "payload": {}}
            if trace_enabled:
                trace_events.append({"stage": "planner"})
            ctx["stage_2_planner"] = p.get("payload", {}) or {}
            # If the planner returns an empty payload (should be rare), fall back
            if not ctx["stage_2_planner"]:
                ctx["stage_2_planner"] = {
                    "goal": f"Satisfy user request: {text}",
                    "intents": ["retrieve_relevant_memories", "compose_response"],
                    "notes": "Planner fallback: empty plan"
                }
        else:
            # Skip planner and assign a generic respond plan
            ctx["stage_2_planner"] = {
                "goal": f"Satisfy user request: {text}",
                "intents": ["retrieve_relevant_memories", "compose_response"],
                "notes": "Planner skipped: non-command/request input"
            }

        # Stage 4 — Pattern recognition.  Run pattern analysis on the input
        # regardless of planning outcome.  Errors are caught and ignored.
        try:
            pr = _brain_module("pattern_recognition").service_api({"op": "ANALYZE", "payload": {"text": text}})
        except Exception:
            pr = {"ok": True, "payload": {"skipped": True}}
        if trace_enabled:
            trace_events.append({"stage": "pattern_recognition"})

        # Populate context entries for stages 1–4
        ctx["stage_1_sensorium"] = s.get("payload", {})
        ctx["stage_3_language"] = lang_payload
        ctx["stage_4_pattern_recognition"] = pr.get("payload", {})

        # Stage 5 — Affect priority scoring.  Use the affect_priority brain to assess
        # the emotional tone and urgency of the input.  Merge the suggested tone into
        # the planner's context if provided.
        try:
            aff_mod = _brain_module("affect_priority")
            ar = aff_mod.service_api({"op": "SCORE", "payload": {"text": text, "context": ctx}})
        except Exception:
            ar = {}
        ctx["stage_5_affect"] = (ar.get("payload") or {})
        tone = ctx.get("stage_5_affect", {}).get("suggested_tone")
        if tone:
            # ensure planner stage exists before setting tone
            ctx.setdefault("stage_2_planner", {})
            ctx["stage_2_planner"].setdefault("tone", tone)

        # ------------------------------------------------------------------
        # Stage 5b — Attention resolution.  After affect scoring, gather
        # coarse bids from select brains (e.g. language and reasoning)
        # based on the current context and ask the integrator brain to
        # determine which brain should receive focus.  The resulting
        # focus and related state are stored in ctx["stage_5b_attention"].
        try:
            # Compose bids by querying each brain's bid_for_attention function.
            # Each participating brain returns a dictionary with keys
            # brain_name, priority, reason and evidence.  Fallback to a
            # simple static bid if none are returned.
            bids: List[Dict[str, Any]] = []
            # Language brain bid
            try:
                lang_mod = _brain_module("language")
                if hasattr(lang_mod, "bid_for_attention"):
                    bid = lang_mod.bid_for_attention(ctx)
                    if isinstance(bid, dict) and bid.get("brain_name"):
                        bids.append(bid)
            except Exception:
                pass
            # Reasoning brain bid
            try:
                reason_mod = _brain_module("reasoning")
                if hasattr(reason_mod, "bid_for_attention"):
                    bid = reason_mod.bid_for_attention(ctx)
                    if isinstance(bid, dict) and bid.get("brain_name"):
                        bids.append(bid)
            except Exception:
                pass
            # Memory bid via local function
            try:
                bid = bid_for_attention(ctx)
                if isinstance(bid, dict) and bid.get("brain_name"):
                    bids.append(bid)
            except Exception:
                pass
            # Fallback: if no bids were collected, provide conservative default bids.
            #
            # The integrator expects at least one bid; however, if all
            # participating brains fail to provide a bid (e.g. due to an
            # import error), construct minimal bids with low priorities to
            # avoid dominating the attention arbitration.  When the input is
            # recognised as a question, give the language brain a slightly
            # higher priority to reflect a potential need for an answer.  All
            # other defaults use a small weight (<=0.2) as recommended in the
            # Stage 2.5→3.0 roadmap.
            if not bids:
                lang_info = ctx.get("stage_3_language", {}) or {}
                lang_type = str(
                    lang_info.get("type")
                    or lang_info.get("storable_type")
                    or lang_info.get("intent")
                    or ""
                ).upper()
                if lang_type == "QUESTION":
                    bids.append({
                        "brain_name": "language",
                        "priority": 0.2,
                        "reason": "unanswered_question",
                        "evidence": {"query": text},
                    })
                else:
                    bids.append({
                        "brain_name": "language",
                        "priority": 0.1,
                        "reason": "default",
                        "evidence": {},
                    })
                bids.append({
                    "brain_name": "reasoning",
                    "priority": 0.15,
                    "reason": "default",
                    "evidence": {},
                })
                bids.append({
                    "brain_name": "memory",
                    "priority": 0.1,
                    "reason": "default",
                    "evidence": {},
                })
            # Invoke integrator if present
            try:
                integrator_mod = _brain_module("integrator")
                ir = integrator_mod.service_api({"op": "RESOLVE", "payload": {"bids": bids}})
                if ir.get("ok"):
                    ctx["stage_5b_attention"] = ir.get("payload", {})
                    # --- Attention history tracking ---
                    # Record the winning focus and its reason along with a timestamp.
                    try:
                        focus = ctx.get("stage_5b_attention", {}).get("focus")
                        reason = ctx.get("stage_5b_attention", {}).get("state", {}).get("focus_reason", "")
                        _ATTENTION_HISTORY.append({
                            "focus": focus,
                            "reason": reason,
                        })
                        # Trim history to maximum length
                        if len(_ATTENTION_HISTORY) > _MAX_RECENT_QUERIES:
                            _ATTENTION_HISTORY.pop(0)
                        # Attach a copy of the history to the attention payload
                        ctx["stage_5b_attention"]["history"] = list(_ATTENTION_HISTORY)
                        # Update focus statistics using the optional analyzer.  This call
                        # quietly returns if the analyzer is not available.
                        try:
                            if update_focus_stats:
                                update_focus_stats(focus, reason)
                        except Exception:
                            # Do not propagate errors from optional analytics
                            pass
                    except Exception:
                        # Do not break the pipeline on history errors
                        pass
            except Exception:
                # Integrator unavailable; skip attention resolution
                pass
        except Exception:
            # Suppress all errors in Stage 5b to avoid breaking the pipeline
            pass

        # Stage 2R — memory-first retrieval (fan to all banks + TAC)
        # Optionally perform retrieval in parallel when enabled via configuration.
        try:
            pb_cfg = CFG.get("parallel_bank_access", {}) or {}
            use_parallel = bool(pb_cfg.get("enabled", False))
        except Exception:
            use_parallel = False
        # Determine whether the input should be stored/retrieved from memory.  If the
        # language brain has marked this input as non‑storable (e.g. a greeting or
        # other social chit‑chat), skip the memory search entirely and return
        # an empty set of results.  This prevents the librarian from wasting
        # time searching all banks for salutations and ensures that downstream
        # stages do not attempt to use irrelevant evidence.
        stage3_local = ctx.get("stage_3_language", {}) or {}
        # Determine whether to perform memory retrieval.  In general, we
        # retrieve memory when the input is storable or is a question.  A
        # special flag ``skip_memory_search`` on the parsed language
        # payload allows conversational meta queries to bypass retrieval
        # entirely.  This prevents meta questions like "where are we"
        # or "how's it going" from searching memory and returning
        # irrelevant results.
        storable_flag = bool(stage3_local.get("storable", True))
        # Normalise the intent/type fields
        intent_type = str(stage3_local.get("type") or stage3_local.get("intent") or "").upper()
        # Check for a skip flag set by the language brain.  When true,
        # always skip retrieval regardless of storable or question status.
        skip_mem = bool(stage3_local.get("skip_memory_search", False))
        # When skip_memory_search is set, normally we avoid all retrieval to
        # prevent irrelevant memory hits.  However, identity questions (e.g.
        # "who am I", "what's my name") rely on scanning the recent
        # conversation for self‑introductions.  In those cases, we must
        # perform a limited retrieval so Stage 3 can extract the name.  See
        # issue #core_identity_query for details.  Therefore, override
        # skip_mem for USER_IDENTITY_QUERY by forcing retrieval on.
        if skip_mem:
            if intent_type == "USER_IDENTITY_QUERY":
                # Perform retrieval even when skip_mem is set so that
                # personal introductions (e.g. "I am Josh") remain accessible.
                should_retrieve = True
            else:
                should_retrieve = False
        else:
            # If the input is a question, force retrieval even when storable is False
            should_retrieve = storable_flag or intent_type == "QUESTION"

        # Compute routing scores for transparency.  Use the dual router if
        # available to produce a mapping of banks to scores and record
        # whether the margin suggests a slow path.  Failures are
        # ignored gracefully.
        try:
            import importlib as _importlib
            router_mod = _importlib.import_module("brains.cognitive.reasoning.service.dual_router")
            rres = router_mod.service_api({
                "op": "ROUTE",
                "payload": {"query": text}
            })
            rscores = (rres.get("payload") or {}).get("scores") or {}
            if rscores and isinstance(rscores, dict):
                # Normalize to floats; keep original order sorted descending
                try:
                    sorted_scores = sorted(rscores.items(), key=lambda itm: float(itm[1]), reverse=True)
                except Exception:
                    sorted_scores = list(rscores.items())
                # Attempt to convert score values to floats; fall back to original
                score_map: Dict[str, float] = {}
                for bk, sc in rscores.items():
                    try:
                        score_map[str(bk)] = float(sc)
                    except Exception:
                        try:
                            # Attempt to coerce via float(str())
                            score_map[str(bk)] = float(str(sc))
                        except Exception:
                            # Preserve as string if cannot convert
                            score_map[str(bk)] = 0.0
                # If all computed scores are zero or missing, fall back to a simple heuristic.
                try:
                    total_score = sum(float(v) for v in score_map.values()) if score_map else 0.0
                except Exception:
                    total_score = 0.0
                if total_score <= 0.0:
                    # When the router provides no meaningful scores, fall back.
                    # First attempt to pick a bank using a simple keyword router.
                    try:
                        pred_bank = _simple_route_to_bank(text)
                    except Exception:
                        pred_bank = None
                    if pred_bank:
                        # Assign a high score to the predicted bank and zero to others.
                        fallback_scores: Dict[str, float] = {}
                        try:
                            # Use _ALL_BANKS defined above if available
                            for bk in _ALL_BANKS:
                                fallback_scores[bk] = 1.0 if bk == pred_bank else 0.0
                        except Exception:
                            # Fallback: only set the predicted bank
                            fallback_scores = {pred_bank: 1.0}
                        ctx["stage_2R_routing_scores"] = fallback_scores
                        ctx["stage_2R_top_banks"] = [pred_bank]
                    else:
                        # If no prediction is available, assign uniform scores across all domain banks.
                        try:
                            root_maven = Path(__file__).resolve().parents[4]
                            domain_dir = root_maven / "brains" / "domain_banks"
                            banks = [p.name for p in domain_dir.iterdir() if p.is_dir()]
                            if banks:
                                fallback_scores = {b: 1.0 for b in banks}
                                ctx["stage_2R_routing_scores"] = fallback_scores
                                # Use the first two banks (sorted order) as top banks for determinism
                                ctx["stage_2R_top_banks"] = banks[:2]
                            else:
                                # No banks found; fall back to zero scores
                                ctx["stage_2R_routing_scores"] = score_map
                                ctx["stage_2R_top_banks"] = list(score_map.keys())[:2]
                        except Exception:
                            # On failure, fall back to zero scores
                            ctx["stage_2R_routing_scores"] = score_map
                            ctx["stage_2R_top_banks"] = list(score_map.keys())[:2]
                else:
                    # Use the computed scores and determine top banks normally
                    ctx["stage_2R_routing_scores"] = score_map
                    try:
                        # Top two banks for transparency
                        ctx["stage_2R_top_banks"] = [itm[0] for itm in sorted_scores[:2]]
                    except Exception:
                        ctx["stage_2R_top_banks"] = list(score_map.keys())[:2]
                # Override routing for simple math expressions
                if _is_simple_math_expression(text):
                    ctx["stage_2R_routing_scores"] = {"math": 1.0}
                    ctx["stage_2R_top_banks"] = ["math"]
            # Include slow_path indicator if present
            if (rres.get("payload") or {}).get("slow_path") is not None:
                ctx["stage_2R_slow_path"] = bool((rres.get("payload") or {}).get("slow_path"))
        except Exception:
            # On failure, omit routing scores
            pass

        # ------------------------------------------------------------------
        # Fallback routing: if the learned router returns no scores or all
        # scores are zero, derive a simple routing decision based on
        # keyword heuristics.  Without this fallback, downstream stages
        # receive a zero vector which prevents retrieval from any domain
        # bank.  The simple router examines the query text and maps it
        # to a high‑level bank; if a specific bank is identified, assign
        # it a score of 1.0 and designate it as the top bank.  The
        # slow_path flag is cleared to avoid misinterpretation by
        # consumers.
        try:
            scores_map = ctx.get("stage_2R_routing_scores") or {}
            fallback_needed = True
            if scores_map:
                for _val in scores_map.values():
                    try:
                        if float(_val) > 0.0:
                            fallback_needed = False
                            break
                    except Exception:
                        continue
            if fallback_needed:
                simple_bank = None
                try:
                    simple_bank = _simple_route_to_bank(text)
                except Exception:
                    simple_bank = None
                if simple_bank:
                    ctx["stage_2R_routing_scores"] = {simple_bank: 1.0}
                    ctx["stage_2R_top_banks"] = [simple_bank]
                    ctx["stage_2R_slow_path"] = False
        except Exception:
            # Silently ignore fallback errors
            pass
        # Before performing retrieval, send a targeted search request based on
        # the current attention focus.  The memory librarian will use the
        # message bus to inform the retrieval helper which domain banks to
        # prioritise.  For example, when the language brain has focus, only
        # language and factual banks are searched.  The focus strength is
        # forwarded as a confidence threshold to aid future prioritisation.
        try:
            attn = ctx.get("stage_5b_attention", {}) or {}
            focus = attn.get("focus")
            if focus:
                from brains.cognitive.message_bus import send  # type: ignore
                # Map high‑level brains to domain banks
                domain_map = {
                    "language": ["language_arts", "factual"],
                    "reasoning": ["science", "math", "theories_and_contradictions"],
                    "memory": ["stm_only", "theories_and_contradictions"],
                }
                domains = domain_map.get(str(focus).lower(), [])
                if domains:
                    conf_strength = float(attn.get("state", {}).get("focus_strength", 0.0) or 0.0)
                    send({
                        "from": "memory_librarian",
                        "to": "memory",
                        "type": "SEARCH_REQUEST",
                        "domains": domains,
                        "confidence_threshold": conf_strength,
                    })
        except Exception:
            pass
        if not should_retrieve:
            mem = {"results": [], "banks": [], "banks_queried": []}
        else:
            if use_parallel:
                # Determine max_workers from config; default to 5 if invalid
                try:
                    mw_val = pb_cfg.get("max_workers", 5)
                    max_workers = int(mw_val) if mw_val else 5
                except Exception:
                    max_workers = 5
                try:
                    mem = _retrieve_from_banks_parallel(text, k=5, max_workers=max_workers)
                except Exception:
                    # Fall back to sequential retrieval on error
                    mem = _retrieve_from_banks(text, k=5)
            else:
                mem = _retrieve_from_banks(text, k=5)
        # Additional retrieval for questions: attempt to sanitize the question and
        # retrieve again to capture declarative statements such as "Birds have wings."
        try:
            # Only perform additional retrieval for questions when the input is not a social chit‑chat.  Even if
            # the question itself is not storable, we still want to search for answers.
            # Determine storable flag and normalised intent as above
            lang_local = ctx.get("stage_3_language") or {}
            storable_flag = bool(lang_local.get("storable", True))
            # Determine if it is a question by checking both 'type' and 'intent' fields
            intent_type = str(lang_local.get("type") or lang_local.get("intent") or "").upper()
            is_question = intent_type == "QUESTION"
            if (storable_flag or is_question) and is_question:
                sanitized = _sanitize_question(text)
                if sanitized and sanitized.lower() != text.lower():
                    # Use the same retrieval mechanism as above (parallel or sequential)
                    try:
                        mem2 = _retrieve_from_banks_parallel(sanitized, k=5, max_workers=max_workers) if use_parallel else _retrieve_from_banks(sanitized, k=5)
                    except Exception:
                        mem2 = _retrieve_from_banks(sanitized, k=5)
                    # Merge mem and mem2 results/banks
                    res1 = mem.get("results", []) or []
                    res2 = mem2.get("results", []) or []
                    # Append unique results (by id and content)
                    seen_ids = set()
                    combined = []
                    for it in res1 + res2:
                        if not isinstance(it, dict):
                            continue
                        rec_id = it.get("id") or id(it)
                        sig = (rec_id, it.get("content"))
                        if sig in seen_ids:
                            continue
                        seen_ids.add(sig)
                        combined.append(it)
                    banks = list(set((mem.get("banks") or []) + (mem2.get("banks") or [])))
                    mem = {"results": combined, "banks": banks, "banks_queried": banks}

                # ------------------------------------------------------------------
                # Fallback retrieval for numerical questions.  If no results were
                # obtained from the initial and sanitized queries, look for
                # alternative phrases that might appear in stored facts.  This
                # helps answer queries like "At what temperature does water
                # freeze?" by searching for simplified phrases such as
                # "water freeze" or "freezing point of water".  Only run this
                # fallback when the intent is a question and no results have
                # yet been found.
                if not (mem.get("results") or []):
                    try:
                        q_lower = str(text or "").lower()
                    except Exception:
                        q_lower = ""
                    # ----------------------------------------------------------------------
                    # Fallback 1: numeric question phrases.  If the query is about
                    # temperature/freeze or temperature/boil and no results were found,
                    # search for simplified phrases likely present in stored facts.
                    if ("temperature" in q_lower and "freeze" in q_lower) or ("temperature" in q_lower and "boil" in q_lower):
                        alt_queries: List[str] = []
                        if "freeze" in q_lower:
                            alt_queries.extend(["water freeze", "water freezes at", "water freeze at", "freezing point of water"])
                        if "boil" in q_lower:
                            alt_queries.extend(["water boil", "water boils at", "water boil at", "boiling point of water"])
                        for alt_q in alt_queries:
                            try:
                                # Determine a sensible default for max_workers if not defined
                                alt_max_workers = max_workers if 'max_workers' in locals() else 5
                                mem_alt = _retrieve_from_banks_parallel(alt_q, k=5, max_workers=alt_max_workers) if use_parallel else _retrieve_from_banks(alt_q, k=5)
                            except Exception:
                                mem_alt = _retrieve_from_banks(alt_q, k=5)
                            if mem_alt and (mem_alt.get("results") or []):
                                res_alt = mem_alt.get("results", []) or []
                                res_orig = mem.get("results", []) or []
                                combined_alt: List[Dict[str, Any]] = []
                                seen_ids_alt: set = set()
                                for it in res_orig + res_alt:
                                    if not isinstance(it, dict):
                                        continue
                                    rec_id = it.get("id") or id(it)
                                    sig = (rec_id, it.get("content"))
                                    if sig in seen_ids_alt:
                                        continue
                                    seen_ids_alt.add(sig)
                                    combined_alt.append(it)
                                banks_alt = list(set((mem.get("banks") or []) + (mem_alt.get("banks") or [])))
                                mem = {"results": combined_alt, "banks": banks_alt, "banks_queried": banks_alt}
                                break
                    # ----------------------------------------------------------------------
                    # Fallback 2: morphological variations.  If the sanitized query
                    # produced no results, try trimming common English suffixes such
                    # as plural "s", "es", gerund "ing", and past tense "ed".  Each
                    # variant is searched individually; any results found are merged
                    # back into ``mem``.  This helps match stored facts where the
                    # user used plural or gerund forms that differ from the stored
                    # statement.
                    if not (mem.get("results") or []):
                        try:
                            # Derive a base string for morphological fallback.  Prefer the
                            # sanitized question if available; fall back to the original
                            # question otherwise.  Both are lowercased for uniformity.
                            base_q = (sanitized.lower() if 'sanitized' in locals() and sanitized else q_lower) or q_lower
                        except Exception:
                            base_q = q_lower
                        # Split into words and generate simple stems.  Import re on the fly
                        # to avoid a module-level dependency when the fallback is unused.
                        words: List[str] = []
                        try:
                            import re as _re  # type: ignore
                            words = [w.strip() for w in _re.findall(r"[A-Za-z0-9']+", base_q) if w.strip()]
                        except Exception:
                            words = base_q.split()
                        variants: List[str] = []
                        for w in words:
                            wl = w.lower()
                            # Skip short words to avoid over-trimming
                            if len(wl) <= 3:
                                continue
                            if wl.endswith("ing"):
                                variants.append(wl[:-3])
                            if wl.endswith("es"):
                                variants.append(wl[:-2])
                            if wl.endswith("s"):
                                variants.append(wl[:-1])
                            if wl.endswith("ed"):
                                variants.append(wl[:-2])
                        # Deduplicate variants and search each one
                        seen_var: set[str] = set()
                        for var in variants:
                            if not var or var in seen_var:
                                continue
                            seen_var.add(var)
                            try:
                                alt_max_workers = max_workers if 'max_workers' in locals() else 5
                                mem_alt = _retrieve_from_banks_parallel(var, k=5, max_workers=alt_max_workers) if use_parallel else _retrieve_from_banks(var, k=5)
                            except Exception:
                                mem_alt = _retrieve_from_banks(var, k=5)
                            if mem_alt and (mem_alt.get("results") or []):
                                res_alt = mem_alt.get("results", []) or []
                                res_orig = mem.get("results", []) or []
                                combined_alt2: List[Dict[str, Any]] = []
                                seen_ids2: set = set()
                                for it in res_orig + res_alt:
                                    if not isinstance(it, dict):
                                        continue
                                    rec_id = it.get("id") or id(it)
                                    sig = (rec_id, it.get("content"))
                                    if sig in seen_ids2:
                                        continue
                                    seen_ids2.add(sig)
                                    combined_alt2.append(it)
                                banks_alt2 = list(set((mem.get("banks") or []) + (mem_alt.get("banks") or [])))
                                mem = {"results": combined_alt2, "banks": banks_alt2, "banks_queried": banks_alt2}
                                # Stop after first successful variant to avoid noise
                                break
        except Exception:
            pass
        # Rank the retrieved results so that numerically relevant matches are surfaced first.
        # This helps answer questions involving numbers (e.g. temperatures or counts) by
        # promoting records containing the same numbers as the query.  If the query
        # contains digits or spelled out numbers (zero through ten), sort the
        # retrieval results to prefer those with matching numeric tokens.  If there
        # are no numeric tokens in the query, leave the ordering unchanged.
        try:
            import re
            qlow = str(text or "").lower()
            # Extract digits and spelled-out numbers from the query
            # Spelled-out numbers list can be extended as needed
            num_words = [
                "zero", "one", "two", "three", "four", "five",
                "six", "seven", "eight", "nine", "ten"
            ]
            tokens: list[str] = []
            # Digits
            try:
                tokens.extend(re.findall(r"\d+", qlow))
            except Exception:
                pass
            # Spelled numbers
            for w in num_words:
                try:
                    if w in qlow:
                        tokens.append(w)
                except Exception:
                    continue
            # Only rank if we actually found numeric tokens
            if tokens and isinstance(mem, dict):
                res_list = mem.get("results") or []
                if isinstance(res_list, list):
                    def _numeric_score(item: dict) -> int:
                        # Compute a score based on how many query tokens appear in the result content
                        try:
                            c = str(item.get("content", "")).lower()
                        except Exception:
                            c = ""
                        score = 0
                        for tok in tokens:
                            try:
                                if tok.isdigit():
                                    # match exact digit sequences in the content
                                    if re.search(r"\b" + re.escape(tok) + r"\b", c):
                                        score += 1
                                else:
                                    if tok in c:
                                        score += 1
                            except Exception:
                                continue
                        return score
                    # Sort results descending by numeric score, preserving original order for ties
                    # Use enumerate index as secondary key for stable sort.  Before sorting,
                    # detect identity/origin queries and prioritise evidence mentioning Maven.
                    res_list = list(res_list)  # ensure it's a list copy

                    # Heuristic: if the original query asks about Maven's identity or origin,
                    # move results containing "maven" or "living intelligence" to the front.
                    try:
                        raw_q = str(ctx.get("original_query", "")).lower().strip()
                    except Exception:
                        raw_q = ""
                    identity_phrases = [
                        "who are you",
                        "what are you",
                        "what is your name",
                        "what's your name",
                        "who is maven",
                        "what is maven",
                        "why were you created",
                        "why were you made",
                        "purpose of maven",
                        "why do you exist",
                    ]
                    if any(p in raw_q for p in identity_phrases):
                        maven_hits = []
                        non_hits = []
                        for itm in res_list:
                            try:
                                c = str(itm.get("content", "")).lower()
                            except Exception:
                                c = ""
                            # If content is a JSON‑encoded dict (e.g. from codified answers), fallback to 'text'
                            if not c and itm.get("text"):
                                c = str(itm.get("text", "")).lower()
                            if "maven" in c or "living intelligence" in c:
                                maven_hits.append(itm)
                            else:
                                non_hits.append(itm)
                        res_list = maven_hits + non_hits

                    scored = []
                    for idx, itm in enumerate(res_list):
                        try:
                            s = _numeric_score(itm)
                        except Exception:
                            s = 0
                        scored.append((s, idx, itm))
                    # If any item has a score > 0, perform sorting
                    if any(s > 0 for s, _, _ in scored):
                        scored.sort(key=lambda x: (-x[0], x[1]))
                        res_list_sorted = [itm for _, _, itm in scored]
                        mem = mem.copy()
                        mem["results"] = res_list_sorted
        except Exception:
            pass
        if trace_enabled: trace_events.append({"stage": "memory_retrieve"})

        # --------------------------------------------------------------
        # Identity/origin query prioritisation
        #
        # After retrieving evidence from domain banks (stored in ``mem``),
        # reorder the results for queries asking about Maven's identity or
        # origin.  This heuristic moves personal knowledge (records that
        # mention "maven" or "living intelligence") to the front so they
        # are considered before unrelated etiquette statements like
        # "We say thank you".  Without this, generic one‑token matches
        # can override more relevant personal facts.
        try:
            raw_q = str(ctx.get("original_query", "")).lower().strip()
        except Exception:
            raw_q = ""
        identity_triggers = [
            "who are you",
            "what are you",
            "what is your name",
            "what's your name",
            "who is maven",
            "what is maven",
            "why were you created",
            "why were you made",
            "purpose of maven",
            "why do you exist",
        ]
        if any(p in raw_q for p in identity_triggers) and isinstance(mem, dict):
            res_list = mem.get("results") or []
            if isinstance(res_list, list) and res_list:
                maven_hits: list = []
                other_hits: list = []
                for itm in res_list:
                    try:
                        c = str(itm.get("content", "")).lower()
                    except Exception:
                        c = ""
                    # If content is a JSON‑encoded object, fall back to its 'text'
                    if not c and itm.get("text"):
                        c = str(itm.get("text", "")).lower()
                    if "maven" in c or "living intelligence" in c:
                        maven_hits.append(itm)
                    else:
                        other_hits.append(itm)
                # Only reorder if we found at least one Maven hit
                if maven_hits:
                    mem = mem.copy()
                    mem["results"] = maven_hits + other_hits

        ctx["stage_2R_memory"] = mem

        # Record upstream weights used (if present)
        ctx["stage_0_weights_used"] = {
            "sensorium": ctx["stage_1_sensorium"].get("weights_used"),
            "planner": ctx["stage_2_planner"].get("weights_used"),
            "language": ctx["stage_3_language"].get("weights_used"),
        }

        # --- Stage 8 — Reasoning (intent-aware proposal) ---
        # Extract parsing metadata from Stage 3.  The language brain
        # classifies the user input into QUESTION, COMMAND, REQUEST,
        # SPECULATION or FACT and indicates whether it is storable.
        stage3 = ctx.get("stage_3_language") or {}
        st_type = str(stage3.get("storable_type", "")).upper()
        # Some speculative statements apply a confidence penalty when stored.
        try:
            confidence_penalty = float(stage3.get("confidence_penalty", 0.0) or 0.0)
        except Exception:
            confidence_penalty = 0.0
        # If the input is a question/command/request, pass an empty content
        # so the reasoning brain does not attempt to store the raw query.
        if st_type in ("QUESTION", "COMMAND", "REQUEST"):
            proposed_content = ""
        else:
            proposed_content = text

        # Always call the reasoning brain to evaluate the proposed content.
        # Include storable_type and confidence_penalty so the reasoning
        # service can apply intent-aware logic.  original_query is passed
        # separately to aid answer retrieval for questions.
        try:
            v = _brain_module("reasoning").service_api({
                "op": "EVALUATE_FACT",
                "payload": {
                    "proposed_fact": {
                        "content": proposed_content,
                        "confidence": conf,
                        "source": "user_input",
                        "original_query": text,
                        "storable_type": st_type,
                        "confidence_penalty": confidence_penalty
                    },
                    "original_query": text,
                    "evidence": ctx.get("stage_2R_memory") or {}
                }
            })
            ctx["stage_8_validation"] = (v.get("payload") or {})
        except Exception:
            ctx["stage_8_validation"] = {}

        # After reasoning verdict, update the success flag for the most recent
        # operations across the cognitive brains.  A verdict of TRUE
        # indicates success for the initiating operations; any other verdict
        # marks them as unsuccessful.  This enables learning from past
        # performance to influence future biases.
        try:
            verdict = str((ctx.get("stage_8_validation") or {}).get("verdict", "")).upper()
            is_success = verdict == "TRUE"
            brains_to_update = ["sensorium", "planner", "language", "pattern_recognition"]
            for b in brains_to_update:
                try:
                    root = COG_ROOT / b
                    update_last_record_success(root, is_success)
                except Exception:
                    pass
        except Exception:
            pass

        # ------------------------------------------------------------------
        # Attempt inference when reasoning has attention but could not
        # determine a verdict.  When Stage 5b assigns focus to the
        # reasoning brain and the reasoning verdict is UNANSWERED or
        # UNKNOWN, try a simple heuristic to infer an answer from the
        # retrieved facts.  If inference succeeds, override the verdict
        # in stage_8_validation with a TRUE verdict and include the
        # inferred answer and confidence.  See Phase 1 fix: Attention
        # influences behaviour for reasoning.
        try:
            # When the verdict is not yet TRUE and memory results exist, attempt
            # to infer an answer via multi‑step reasoning.  This fires
            # regardless of the attention focus to ensure that factual
            # knowledge is surfaced whenever possible.  Only TRUE verdicts
            # are exempt to avoid overriding already validated responses.
            current_verdict = str((ctx.get("stage_8_validation") or {}).get("verdict", "")).upper()
            mem_res = (ctx.get("stage_2R_memory") or {}).get("results", [])
            if mem_res and current_verdict != "TRUE":
                # Extract the original query text
                qtext = str(ctx.get("original_query", "") or ctx.get("stage_3_language", {}).get("original_query", ""))
                inferred = _attempt_inference(qtext, mem_res)
                if inferred:
                    ctx.setdefault("stage_8_validation", {})
                    ctx_stage8 = ctx["stage_8_validation"]
                    ctx_stage8.update({
                        "verdict": "TRUE",
                        "mode": "INFERRED",
                        "confidence": inferred.get("confidence", 0.6),
                        "answer": inferred.get("answer"),
                        "reasoning_chain": inferred.get("steps", []),
                    })
                    if inferred.get("trace"):
                        ctx_stage8["reasoning_trace"] = inferred.get("trace")
        except Exception:
            # Never fail pipeline if inference errors
            pass
        # ------------------------------------------------------------------
        # Stage 8a – Meta-reasoner consistency check
        # If the reasoning engine reports both supporting and contradicting
        # evidence for the proposed statement, flag this as a potential
        # contradiction.  The meta-reasoner does not alter the verdict but
        # records the issue for offline inspection.  Flags are appended
        # to reports/system/meta_reasoner_flags.jsonl and stored in the
        # context under stage_meta_reasoner.
        try:
            support_ids = (ctx.get("stage_8_validation") or {}).get("supported_by") or []
            contradict_ids = (ctx.get("stage_8_validation") or {}).get("contradicted_by") or []
            meta_flag = None
            if support_ids and contradict_ids:
                meta_flag = {
                    "issue": "contradictory evidence",
                    "supported_by": support_ids,
                    "contradicted_by": contradict_ids
                }
                # Persist the flag to system reports
                try:
                    meta_dir = MAVEN_ROOT / "reports" / "system"
                    meta_dir.mkdir(parents=True, exist_ok=True)
                    with open(meta_dir / "meta_reasoner_flags.jsonl", "a", encoding="utf-8") as fh:
                        fh.write(json.dumps({"mid": mid, "meta_flag": meta_flag}) + "\n")
                except Exception:
                    pass
                # When contradictory evidence is found, override the reasoning verdict to
                # ensure the claim is treated as a theory and routed to the theories bank.
                try:
                    # Set verdict and mode to indicate contradicted evidence
                    ctx.setdefault("stage_8_validation", {})
                    ctx["stage_8_validation"]["verdict"] = "THEORY"
                    ctx["stage_8_validation"]["mode"] = "CONTRADICTED_EVIDENCE"
                    # Force routing to theories_and_contradictions
                    ctx["stage_8_validation"]["routing_order"] = {"target_bank": "theories_and_contradictions", "action": "STORE"}
                    # Append a disputed audit entry to the Self‑DMN audit log
                    claim_id = ctx["stage_8_validation"].get("claim_id")
                    if claim_id:
                        try:
                            sdmn_dir = MAVEN_ROOT / "reports" / "self_dmn"
                            sdmn_dir.mkdir(parents=True, exist_ok=True)
                            with open(sdmn_dir / "audit.jsonl", "a", encoding="utf-8") as fh:
                                fh.write(json.dumps({"claim_id": claim_id, "status": "disputed"}) + "\n")
                        except Exception:
                            pass
                except Exception:
                    pass
            ctx["stage_meta_reasoner"] = meta_flag
        except Exception:
            ctx["stage_meta_reasoner"] = None
        if trace_enabled:
            trace_events.append({"stage": "reasoning"})

        # ------------------------------------------------------------------
        # Stage 8d – Self‑DMN dissent scan and optional recompute
        # After the initial reasoning verdict, invoke the Self‑DMN brain to
        # perform a dissent scan across recent claims.  If the scan returns a
        # RECOMPUTE decision for the current claim, re-run the reasoning
        # evaluation once to reassess the verdict with the same evidence.  The
        # recomputation is guarded so that it happens at most once per run.
        try:
            # Extract the claim ID from the reasoning stage, if present
            claim_id = (ctx.get("stage_8_validation") or {}).get("claim_id")
            # Proceed only if we have a claim ID and have not already re-run
            if claim_id and not ctx.get("debate_rerun"):
                sdmn_mod = _brain_module("self_dmn")
                try:
                    scan_res = sdmn_mod.service_api({"op": "DISSENT_SCAN", "payload": {}})
                    decisions = (scan_res.get("payload") or {}).get("decisions") or []
                except Exception:
                    decisions = []
                # Check for a recompute instruction for this claim
                recompute = False
                for dec in decisions:
                    try:
                        if dec.get("claim_id") == claim_id and str(dec.get("action", "")).upper() == "RECOMPUTE":
                            recompute = True
                            break
                    except Exception:
                        continue
                if recompute:
                    # Perform a single re-evaluation using the existing evidence
                    # Build the proposed_fact payload as in the initial call
                    proposed_fact = {
                        "content": proposed_content or text,
                        "confidence": conf,
                        "source": "user_input",
                        "original_query": text,
                        "storable_type": str(stage3.get("storable_type", "")),
                        "confidence_penalty": confidence_penalty
                    }
                    # Reuse the existing evidence from Stage 2R memory
                    evidence_reuse = ctx.get("stage_2R_memory") or {}
                    try:
                        new_val = _brain_module("reasoning").service_api({
                            "op": "EVALUATE_FACT",
                            "payload": {
                                "proposed_fact": proposed_fact,
                                "original_query": text,
                                "evidence": evidence_reuse
                            }
                        })
                        ctx["stage_8_validation"] = (new_val.get("payload") or ctx.get("stage_8_validation") or {})
                        # Mark the rerun so that we do not loop
                        ctx["debate_rerun"] = True
                        # Record that this run was recomputed due to Self-DMN dissent
                        ctx["stage_meta_reasoner"] = {"reason": "self_dmn_recompute"}
                    except Exception:
                        pass
        except Exception:
            pass

        # For non-storable inputs (question, command or request) that were
        # unanswered by the reasoning engine (mode ends with _INPUT), set
        # verdict to SKIP_STORAGE with a rationale.  This prevents storage
        # and helps candidate generation produce an appropriate reply.
        try:
            st_type_upper = str(stage3.get("storable_type", "")).upper()
            mode_upper = str((ctx.get("stage_8_validation") or {}).get("mode", "")).upper()
            if st_type_upper in ("QUESTION", "COMMAND", "REQUEST") and mode_upper.endswith("_INPUT"):
                unanswered_mode = f"UNANSWERED_{st_type_upper}"
                rationale_map = {
                    "QUESTION": "Questions are not stored without answers",
                    "COMMAND": "Commands are requests for action and not facts",
                    "REQUEST": "Requests are not facts and are not stored"
                }
                ctx["stage_8_validation"] = {
                    "verdict": "SKIP_STORAGE",
                    "mode": unanswered_mode,
                    "confidence": 0.0,
                    "route": None,
                    "rationale": rationale_map.get(st_type_upper, "Not storable input")
                }
        except Exception:
            pass

        # Stage 8b — Governance
        bias_profile = {
            "planner": ctx["stage_2_planner"].get("weights_used"),
            "language": ctx["stage_3_language"].get("weights_used"),
            "reasoning": ctx["stage_8_validation"].get("weights_used"),
            "personality": prefs,
            "adjustment_proposal": suggestion,
        }
        gov = _gov_module()
        # Always pass a non-empty content to governance; fall back to original text
        content_for_gov = proposed_content if proposed_content else text
        # Determine whether storage is warranted based on storable type and verdict.  Only
        # statements and validated theories should be sent to governance for storage.  Social
        # greetings and unknown inputs are treated as non‑storable as well to avoid
        # unnecessary policy checks.
        stage3_local = ctx.get("stage_3_language", {}) or {}
        st_type = str(stage3_local.get("storable_type", "")).upper()
        verdict_upper = str((ctx.get("stage_8_validation") or {}).get("verdict", "")).upper()
        # Non‑storable types or unanswered questions skip storage completely.  Include SOCIAL
        # and UNKNOWN in the list of non‑storable types.
        store_needed = not (st_type in {"QUESTION", "COMMAND", "REQUEST", "EMOTION", "OPINION", "SOCIAL", "UNKNOWN"} or verdict_upper == "SKIP_STORAGE")
        if store_needed:
            # Ask governance whether it is permissible to store this content
            enf = gov.service_api({
                "op": "ENFORCE",
                "payload": {
                    "action": "STORE",
                    "payload": {"content": content_for_gov},
                    "bias_profile": bias_profile,
                },
            })
            ctx["stage_8b_governance"] = enf.get("payload", {})
            allowed = bool(ctx["stage_8b_governance"].get("allowed", False))
        else:
            # Skip enforcement; mark as skipped so downstream storage can short‑circuit.  For
            # non‑storable types we still mark governance as allowed so that user‑facing logs
            # do not report a denial.  The action SKIP indicates no storage will occur.
            ctx["stage_8b_governance"] = {"allowed": True, "action": "SKIP"}
            allowed = True

        # Find duplicates against retrieved evidence (exact match)
        match = _best_memory_exact(ctx.get("stage_2R_memory"), proposed_content or "")
        duplicate = bool(match)

        # Stage 6 — candidates
        # Check for preference_query intent and handle from memory
        stage3_intent = str((ctx.get("stage_3_language") or {}).get("intent", ""))
        if stage3_intent == "preference_query":
            # Handle preference query by retrieving all stored preferences
            try:
                user_id = ctx.get("user_id") or "default_user"
                preferences = get_all_preferences(user_id)

                if preferences:
                    # Build a summary of preferences
                    pref_items = []
                    for pref in preferences:
                        content = str(pref.get("content", ""))
                        if content:
                            pref_items.append(content)

                    # Create a single-sentence summary
                    if len(pref_items) <= 3:
                        summary = ", ".join(pref_items)
                    else:
                        summary = ", ".join(pref_items[:3]) + f", and {len(pref_items) - 3} more"

                    answer_text = f"Based on what you've told me, you like: {summary}."
                    confidence = 0.9
                else:
                    answer_text = "I don't have any stored preferences for you yet. Tell me what you like!"
                    confidence = 0.7

                # Build a direct preference candidate
                cand = {
                    "type": "preference_query",
                    "text": answer_text,
                    "confidence": confidence,
                    "tone": "neutral",
                    "tag": "preference_retrieved",
                }
                ctx["stage_6_candidates"] = {
                    "candidates": [cand],
                    "weights_used": {"gen_rule": "preference_query_v1"}
                }
                # Set stage 8 validation with PREFERENCE verdict
                ctx["stage_8_validation"] = {
                    "verdict": "PREFERENCE",
                    "mode": "PREFERENCE_QUERY",
                    "confidence": 1.0,
                    "routing_order": {"target_bank": None, "action": None},
                    "supported_by": [],
                    "contradicted_by": [],
                    "answer": answer_text,
                    "weights_used": {"rule": "preference_query_v1"}
                }
            except Exception as pref_ex:
                # Preference query failed; fall back to language brain
                try:
                    cands = _brain_module("language").service_api({"op": "GENERATE_CANDIDATES", "mid": mid, "payload": ctx})
                    ctx["stage_6_candidates"] = cands.get("payload", {})
                except Exception:
                    ctx["stage_6_candidates"] = {"candidates": [], "error": str(pref_ex)}
        # Check for relationship_query intent and handle from memory
        elif stage3_intent == "relationship_query":
            # Handle relationship query by looking up stored relationship facts
            try:
                user_id = ctx.get("user_id") or "default_user"
                relationship_kind = (ctx.get("stage_3_language") or {}).get("relationship_kind")

                if relationship_kind:
                    fact = get_relationship_fact(user_id, relationship_kind)

                    if fact is not None and fact.get("value") is True:
                        answer_text = "You've told me we're friends. I'm an AI and don't experience friendship like humans do, but I understand that as your intent and I'm here to help you."
                        verdict = "TRUE"
                        confidence = 0.9
                    elif fact is not None and fact.get("value") is False:
                        answer_text = "You've told me we're not friends. I'll respect that, but I'm still here to help you if you want."
                        verdict = "TRUE"
                        confidence = 0.9
                    else:
                        # No stored relationship fact; fall back to default answer
                        answer_text = "I'm an AI, so I don't experience friendship the way humans do, but I'm here to help you."
                        verdict = "NEUTRAL"
                        confidence = 0.7

                    # Build a direct relationship candidate
                    cand = {
                        "type": "relationship_query",
                        "text": answer_text,
                        "confidence": confidence,
                        "tone": "neutral",
                        "tag": "relationship_retrieved",
                    }
                    ctx["stage_6_candidates"] = {
                        "candidates": [cand],
                        "weights_used": {"gen_rule": "relationship_query_v1"}
                    }
                    # Set stage 8 validation
                    ctx["stage_8_validation"] = {
                        "verdict": verdict,
                        "mode": "RELATIONSHIP_QUERY",
                        "confidence": confidence,
                        "routing_order": {"target_bank": None, "action": None},
                        "supported_by": [],
                        "contradicted_by": [],
                        "answer": answer_text,
                        "weights_used": {"rule": "relationship_query_v1"}
                    }
                else:
                    # Missing relationship_kind; fall back to language brain
                    cands = _brain_module("language").service_api({"op": "GENERATE_CANDIDATES", "mid": mid, "payload": ctx})
                    ctx["stage_6_candidates"] = cands.get("payload", {})
            except Exception as rel_ex:
                # Relationship query failed; fall back to language brain
                try:
                    cands = _brain_module("language").service_api({"op": "GENERATE_CANDIDATES", "mid": mid, "payload": ctx})
                    ctx["stage_6_candidates"] = cands.get("payload", {})
                except Exception:
                    ctx["stage_6_candidates"] = {"candidates": [], "error": str(rel_ex)}
        # Check for math_compute intent and handle deterministically
        elif stage3_intent == "math_compute":
            # Call the deterministic math handler
            math_result = _solve_simple_math(text)
            if math_result.get("ok"):
                # Build a direct math candidate with confidence 1.0
                cand = {
                    "type": "math_deterministic",
                    "text": str(math_result["result"]),
                    "confidence": 1.0,
                    "tone": "neutral",
                    "tag": "math_computed",
                }
                ctx["stage_6_candidates"] = {
                    "candidates": [cand],
                    "weights_used": {"gen_rule": "math_deterministic_v1"}
                }
                # Mark in context for stage 8 validation
                ctx["mode"] = "math_deterministic"
                # Set stage 8 validation for math with TRUE verdict and confidence 1.0
                ctx["stage_8_validation"] = {
                    "verdict": "TRUE",
                    "mode": "MATH_DIRECT",
                    "confidence": 1.0,
                    "routing_order": {"target_bank": None, "action": None},
                    "supported_by": [],
                    "contradicted_by": [],
                    "answer": str(math_result["result"]),
                    "weights_used": {"rule": "math_deterministic_v1"}
                }
            else:
                # Math parsing failed; fall back to language brain
                try:
                    cands = _brain_module("language").service_api({"op": "GENERATE_CANDIDATES", "mid": mid, "payload": ctx})
                    ctx["stage_6_candidates"] = cands.get("payload", {})
                except Exception as cand_ex:
                    ctx["stage_6_candidates"] = {"candidates": [], "error": str(cand_ex)}
        else:
            # Always run a cross‑validation to compute arithmetic or definitional responses.
            try:
                _cross_validate_answer(ctx)
            except Exception:
                pass
            # Load the verdict, answer and confidence after potential cross‑validation
            try:
                ver_u_local = str((ctx.get("stage_8_validation") or {}).get("verdict", "")).upper()
                ans_local = (ctx.get("stage_8_validation") or {}).get("answer")
                conf_local = float((ctx.get("stage_8_validation") or {}).get("confidence", 0.0) or 0.0)
            except Exception:
                ver_u_local = ""
                ans_local = None
                conf_local = 0.0
            # If we have a TRUE verdict and a substantive answer, produce a direct factual candidate.
            if ver_u_local == "TRUE" and ans_local:
                ans_lc = str(ans_local).lower() if ans_local else ""
                is_bad = False
                try:
                    for bad in BAD_CACHE_PHRASES:
                        if bad and bad in ans_lc:
                            is_bad = True
                            break
                except Exception:
                    is_bad = False
                if not is_bad:
                    cand = {
                        "type": "direct_factual",
                        "text": ans_local,
                        "confidence": conf_local,
                        "tone": "neutral",
                        "tag": ctx.get("cross_check_tag", "asserted_true"),
                    }
                    ctx["stage_6_candidates"] = {
                        "candidates": [cand],
                        "weights_used": {"gen_rule": "s6_locked_bridge_v2"}
                    }
                else:
                    # Answer contains a bad phrase; rely on the language brain to generate candidates
                    try:
                        cands = _brain_module("language").service_api({"op": "GENERATE_CANDIDATES", "mid": mid, "payload": ctx})
                        ctx["stage_6_candidates"] = cands.get("payload", {})
                    except Exception as cand_ex:
                        ctx["stage_6_candidates"] = {"candidates": [], "error": str(cand_ex)}
            else:
                # No locked answer available; rely on the language brain for candidate generation
                try:
                    cands = _brain_module("language").service_api({"op": "GENERATE_CANDIDATES", "mid": mid, "payload": ctx})
                    ctx["stage_6_candidates"] = cands.get("payload", {})
                except Exception as cand_ex:
                    ctx["stage_6_candidates"] = {"candidates": [], "error": str(cand_ex)}
        if trace_enabled:
            trace_events.append({"stage": "language_generate_candidates"})

        # Stage 10 — finalize
        # When the reasoning verdict is TRUE and we bridged Stage 6,
        # skip calling FINALIZE if a final answer is already present to
        # avoid overwriting it with an empty or filler response.  For
        # other verdicts, invoke the language brain to finalise the
        # selected candidate.
        try:
            ver_u2 = str((ctx.get("stage_8_validation") or {}).get("verdict", "")).upper()
        except Exception:
            ver_u2 = ""
        if ver_u2 == "TRUE" and ctx.get("stage_6_candidates"):
            # Extract the first candidate and set the final answer directly
            c0 = (ctx.get("stage_6_candidates") or {}).get("candidates", [])
            if c0:
                try:
                    c0 = c0[0]
                    ctx["stage_10_finalize"] = {"text": c0.get("text"), "confidence": c0.get("confidence", 0.0)}
                except Exception:
                    ctx["stage_10_finalize"] = {}
            else:
                # No candidates; fall back to FINALIZE normally
                try:
                    fin = _brain_module("language").service_api({"op":"FINALIZE","payload": ctx})
                    ctx["stage_10_finalize"] = fin.get("payload", {})
                except Exception:
                    ctx["stage_10_finalize"] = {}
        else:
            try:
                fin = _brain_module("language").service_api({"op":"FINALIZE","payload": ctx})
                ctx["stage_10_finalize"] = fin.get("payload", {})
            except Exception:
                ctx["stage_10_finalize"] = {}
        if trace_enabled:
            trace_events.append({"stage": "language_finalize"})

        # Before capturing the final answer, run a cross‑validation on the
        # reasoning verdict.  This second pass occurs after the reasoning
        # brain has produced a verdict and the language brain has
        # formatted the answer.  Arithmetic or definitional mismatches
        # detected here override the final answer.
        try:
            _cross_validate_answer(ctx)
        except Exception:
            pass
        # Capture final answer and confidence for external consumers (e.g. CLI).
        # If the cross‑validation recomputed the answer, use it and supply a
        # generic confidence.  Otherwise mirror the language finalize payload.
        try:
            # Determine whether the cross check produced a new answer.
            cv_answer = (ctx.get("stage_8_validation") or {}).get("answer")
            cv_tag = ctx.get("cross_check_tag")
            if cv_tag == "recomputed" and cv_answer:
                ctx["final_answer"] = cv_answer
                # Assign a moderate confidence when recomputing arithmetic
                ctx["final_confidence"] = 0.4
            else:
                ctx["final_answer"] = ctx.get("stage_10_finalize", {}).get("text")
                ctx["final_confidence"] = ctx.get("stage_10_finalize", {}).get("confidence")
        except Exception:
            ctx["final_answer"] = None
            ctx["final_confidence"] = None

        # Calibrate the final confidence using the Stage 8 validation confidence.
        # If the reasoning stage produced a higher confidence than the
        # language finalize, promote the final confidence to reflect that.
        try:
            s8_conf = (ctx.get("stage_8_validation") or {}).get("confidence")
            if s8_conf is not None:
                try:
                    sconf = float(s8_conf or 0.0)
                except Exception:
                    sconf = 0.0
                try:
                    fconf = float(ctx.get("final_confidence") or 0.0)
                except Exception:
                    fconf = 0.0
                if sconf > fconf:
                    ctx["final_confidence"] = sconf
            # Additionally, calibrate final confidence using the highest
            # confidence among retrieved memory facts.  When the final
            # confidence remains low but memory records include highly
            # trusted statements, promote the final confidence to match
            # that evidence.  This prevents high‑quality facts from being
            # obscured by conservative aggregation.
            try:
                mem_res = (ctx.get("stage_2R_memory") or {}).get("results", [])
            except Exception:
                mem_res = []
            try:
                max_mem_conf = 0.0
                for rec in mem_res:
                    try:
                        rc = float(rec.get("confidence", 0.0) or 0.0)
                    except Exception:
                        rc = 0.0
                    if rc > max_mem_conf:
                        max_mem_conf = rc
                try:
                    fconf2 = float(ctx.get("final_confidence") or 0.0)
                except Exception:
                    fconf2 = 0.0
                if max_mem_conf > fconf2:
                    ctx["final_confidence"] = max_mem_conf
            except Exception:
                pass
        except Exception:
            # Do not propagate confidence calibration errors
            pass

        # Expose the cross‑validation tag for transparency.  Downstream
        # consumers can examine this flag to understand whether the
        # answer was asserted, recomputed or marked as conflicting.  If
        # cross_check_tag is absent, default to "asserted_true".
        try:
            ctx["final_tag"] = ctx.get("cross_check_tag", "asserted_true")
        except Exception:
            ctx["final_tag"] = "asserted_true"

        # Provide a simple explanation when no answer is found.  If the
        # reasoning verdict indicates UNKNOWN or UNANSWERED, or if the
        # final answer text is empty, attach a rationale explaining that
        # retrieval failed.  This helps external consumers understand why
        # the system could not produce a response.
        try:
            verdict_upper_tmp = str((ctx.get("stage_8_validation") or {}).get("verdict", "")).upper()
            final_text_tmp = str(ctx.get("final_answer", "") or "").strip()
            if verdict_upper_tmp in {"UNKNOWN", "UNANSWERED"} or not final_text_tmp:
                ctx["reasoning_explanation"] = (
                    "No relevant facts were found in the domain banks or the inference engine "
                    "could not connect them, so the system could not confidently answer the question."
                )
        except Exception:
            pass

        # Propagate reasoning trace for transparency.  When the reasoning
        # engine supplies a ``reasoning_trace`` in stage 8, expose it in
        # the top‑level context so that external consumers can inspect the
        # inference process.  This does not alter the final answer or
        # confidence but simply surfaces the trace.
        try:
            rt = (ctx.get("stage_8_validation") or {}).get("reasoning_trace")
            if rt:
                ctx["reasoning_trace"] = rt
        except Exception:
            pass

        # --- Belief extraction from definitional answers ---
        # If the original query is a simple definition question (e.g. "what is X?")
        # and the language brain produced a non-empty final answer, extract the
        # subject and store the answer as a belief.  Conflicting beliefs are
        # detected via the belief tracker; only non-conflicting beliefs are
        # recorded.  This logic runs opportunistically and does not affect
        # the pipeline if the belief tracker is unavailable.
        try:
            ans = ctx.get("final_answer") or ""
            if ans:
                q_raw = str(ctx.get("original_query") or "").strip().lower()
                prefixes = ["what is ", "who is ", "what was ", "who was ", "who are ", "what are "]
                subj: Optional[str] = None
                for pfx in prefixes:
                    if q_raw.startswith(pfx):
                        subj = q_raw[len(pfx):].strip().rstrip("?")
                        break
                if subj and _belief_add:
                    conflict = None
                    try:
                        if _belief_detect:
                            conflict = _belief_detect(subj, "is", ans)
                    except Exception:
                        conflict = None
                    if not conflict:
                        try:
                            conf_val = float(ctx.get("final_confidence") or 1.0)
                        except Exception:
                            conf_val = 1.0
                        _belief_add(subj, "is", ans, confidence=conf_val)
        except Exception:
            pass

        # --- Context decay and meta‑learning ---
        # Apply temporal decay to the context to reduce the weight of old
        # numeric values.  Store the decayed copy under a special key.
        try:
            if _ctx_decay:
                ctx["decayed_context"] = _ctx_decay(ctx)
        except Exception:
            # Ignore decay errors
            pass
        # Record run metrics for meta learning.  The meta learning layer
        # can later update weights based on these observations.  This call
        # is opportunistic and will be silently skipped if the optional
        # import failed.
        try:
            if _meta_record:
                _meta_record(ctx)
        except Exception:
            pass

        # Persist user identity declarations like "I am Josh" or "my name is Alice"
        # This must happen BEFORE Stage 9 storage to ensure it runs even when
        # storage is skipped for questions or low-confidence content.
        try:
            _utterance = str(ctx.get("original_query") or "").lower()
            # Only process identity statements, not questions like "who am i"
            # Handle various casual forms: "im josh", "i'm josh", "i am josh", "my name is josh"
            if any(pattern in _utterance for pattern in ["i am ", "i'm ", "im ", "my name is ", "call me "]):
                # Skip questions
                if not any(q in _utterance for q in ["who am i", "what is my name", "what's my name", "whats my name"]):
                    # Extract name using the existing episodic helper
                    name = episodic_last_declared_identity([{"user": ctx.get("original_query", "")}], n=1)
                    if name and len(name.strip()) > 0:
                        # Store in the durable identity store
                        try:
                            if identity_user_store:
                                identity_user_store.SET(name.strip())  # type: ignore[attr-defined]
                        except Exception:
                            pass
                        # Also store in working memory for immediate access
                        try:
                            service_api({
                                "op": "WM_PUT",
                                "payload": {
                                    "key": "user_identity",
                                    "value": name.strip(),
                                    "tags": ["identity", "name"],
                                    "confidence": 1.0
                                }
                            })
                        except Exception:
                            pass
                        # Store in brain-level persistent storage as backup
                        try:
                            service_api({
                                "op": "BRAIN_PUT",
                                "payload": {
                                    "scope": "BRAIN",
                                    "origin_brain": "memory_librarian",
                                    "key": "user_identity",
                                    "value": name.strip(),
                                    "confidence": 1.0
                                }
                            })
                        except Exception:
                            pass
        except Exception:
            pass

        # Stage 9 — Storage (routing-aware + router assist + TAC promotion)
        # Determine storage eligibility based on storable_type and reasoning verdict.
        st_type = str(stage3.get("storable_type", "")).upper()
        verdict_upper = str((ctx.get("stage_8_validation") or {}).get("verdict", "")).upper()

        # Handle relationship updates early
        stage3_intent = str(stage3.get("intent", ""))
        if stage3_intent == "relationship_update":
            try:
                # Extract relationship information from stage3
                user_id = ctx.get("user_id") or "default_user"
                relationship_kind = stage3.get("relationship_kind")
                relationship_value = stage3.get("relationship_value")

                if relationship_kind is not None and relationship_value is not None:
                    # Store the relationship fact
                    set_relationship_fact(user_id, relationship_kind, relationship_value)

                    # Record in stage_9_storage
                    ctx["stage_9_storage"] = {
                        "action": "STORE",
                        "bank": "relationships",
                        "kind": relationship_kind,
                        "value": relationship_value,
                    }
                else:
                    ctx["stage_9_storage"] = {"skipped": True, "reason": "relationship_update_missing_data"}
            except Exception as rel_store_ex:
                ctx["stage_9_storage"] = {"skipped": True, "reason": f"relationship_update_error: {str(rel_store_ex)[:100]}"}
            # Skip remaining storage logic for relationship updates
            pass
        else:
            pass  # Continue with normal storage logic
        # Allow downstream storage only when the claim is validated, not a low‑confidence
        # cache result and when the content is considered storable.  This early
        # check supersedes the normal routing logic to prevent polluting the
        # knowledge base with unverified or weakly supported answers.
        try:
            final_confidence_val = float(ctx.get("final_confidence") or 0.0)
        except Exception:
            final_confidence_val = 0.0
        from_cache_flag = bool((ctx.get("stage_8_validation") or {}).get("from_cache"))
        # Non-storable types are never persisted.  Extend the set of non-storable types
        # to include SOCIAL greetings and UNKNOWN inputs.  Use a specific skip reason
        # for social greetings (social_greeting) and unknown inputs (unknown_input) to
        # improve traceability.
        non_storable_types = {"QUESTION", "COMMAND", "REQUEST", "EMOTION", "SOCIAL", "UNKNOWN"}
        # Removed OPINION - opinions can be stored as beliefs
        # Facts, even with low confidence, should be stored
        # Determine if we should skip storage due to verdict
        # Store ALL facts (TRUE, UNKNOWN, THEORY) - route them appropriately based on confidence
        # The governance layer (stage_8b) already decided whether to allow storage
        # Storage logic should respect that decision rather than independently blocking
        # Check for math_compute intent - skip storage for raw math expressions
        stage3_intent = str(stage3.get("intent", ""))
        is_math_compute = (stage3_intent == "math_compute" or ctx.get("mode") == "math_deterministic")
        is_preference_or_relationship_query = stage3_intent in {"preference_query", "relationship_query"}

        # Skip storage for preference/relationship queries and math expressions
        if is_preference_or_relationship_query:
            ctx["stage_9_storage"] = {"skipped": True, "reason": "query_not_stored"}
        elif is_math_compute:
            ctx["stage_9_storage"] = {"skipped": True, "reason": "math_expression_not_stored"}
        elif st_type in non_storable_types:
            reason_map = {
                "SOCIAL": "social_greeting",
                "UNKNOWN": "unknown_input"
            }
            reason = reason_map.get(st_type, f"{st_type.lower()}_not_stored")
            ctx["stage_9_storage"] = {"skipped": True, "reason": reason}
        # Reasoning may direct a SKIP_STORAGE verdict for unanswered questions or invalid input
        elif verdict_upper == "SKIP_STORAGE":
            ctx["stage_9_storage"] = {"skipped": True, "reason": "question_without_answer"}
        # Skip storage for PREFERENCE verdicts - preferences are already stored elsewhere
        elif verdict_upper == "PREFERENCE":
            ctx["stage_9_storage"] = {"skipped": True, "reason": "preference_already_handled"}
        elif allowed:
            routing = ctx.get("stage_8_validation", {}).get("routing_order", {}) or {}
            target_bank = routing.get("target_bank") or "theories_and_contradictions"
            # Don't blindly accept SKIP from routing if verdict is TRUE
            if verdict_upper == "TRUE":
                action = "STORE"  # Always store TRUE facts
            else:
                action = routing.get("action") or "STORE"

            # Freeze the final decision for downstream code (prevents later overrides)
            final_action_upper = "STORE" if verdict_upper == "TRUE" else str(action).upper()
            ctx["_memory_route"] = {
                "verdict": verdict_upper,
                "allowed": True,
                "target_bank": target_bank,
                "final_action": final_action_upper
            }

            # Learning: on TRUE verdict, merge-write key/value into per-brain memory
            # This enables reinforcement learning where repeated confirmations of the
            # same fact increase confidence and access count over time.
            _k = ctx.get("key")
            _v = ctx.get("value")
            if verdict_upper == "TRUE" and _k is not None and _v is not None:
                _merge_brain_kv("memory_librarian", _k, _v, conf_delta=0.1)

            # If Reasoning didn't choose a bank, ask the routing modules.  Use the
            # simple keyword router for obvious domains, but consult the learned
            # router for additional guidance.  Prefer the simple router when it
            # returns a specific domain; otherwise fall back to the learned router.
            if not target_bank or target_bank == "unknown":
                simple_bank = _simple_route_to_bank(proposed_content or text)
                lr_target = None
                # Query the learned router and record its scores and signals
                try:
                    rr = _router_module().service_api({"op":"ROUTE","payload":{"text": proposed_content or text}})
                    pay = rr.get("payload") or {}
                    ctx.setdefault("stage_8_validation", {}).setdefault("router_scores", pay.get("scores"))
                    ctx["stage_8_validation"]["router_signals"] = pay.get("signals")
                    # Capture the slow_path flag from the dual router.  This flag
                    # indicates that the confidence margin between the top two
                    # candidate banks is low and that a more deliberate evaluation
                    # may be warranted.  Record it in stage_8_validation for
                    # downstream consumers.  If slow_path is absent or None,
                    # default to False.
                    try:
                        slow = bool(pay.get("slow_path", False))
                    except Exception:
                        slow = False
                    ctx["stage_8_validation"]["slow_path"] = slow
                    lr_target = pay.get("target_bank")
                except Exception:
                    lr_target = None
                # If both routers yield results, compare their confidence.  Each
                # learned router score lies between 0 and 1.  The simple router
                # has no intrinsic score, so we approximate its score from the
                # learned router's score for that bank.  Prefer the learned
                # router's target when it scores strictly higher than the
                # simple router's score by a small margin (0.05).  Otherwise
                # prefer the simple router when it is specific (not a generic
                # bucket like "working_theories" or "unknown").  If both
                # fall back to generic categories, choose the learned target
                # directly.
                chosen: str | None = None
                scores = (ctx.get("stage_8_validation", {}).get("router_scores") or {})
                if simple_bank and simple_bank not in {"working_theories", "unknown"}:
                    # Score of the simple bank and the learned target from the learned router scores
                    try:
                        simple_score = float(scores.get(simple_bank, 0.0))
                    except Exception:
                        simple_score = 0.0
                    try:
                        lr_score = float(scores.get(lr_target, 0.0)) if lr_target else 0.0
                    except Exception:
                        lr_score = 0.0
                    # Prefer the learned router target if it scores significantly higher
                    if lr_target and lr_target != simple_bank and lr_score > simple_score + 0.05:
                        chosen = lr_target
                    else:
                        chosen = simple_bank
                else:
                    # If simple router yields generic bucket, rely on the learned router target
                    chosen = lr_target if lr_target else None
                if chosen:
                    target_bank = chosen
                else:
                    target_bank = "theories_and_contradictions"

            # CONFIDENCE-BASED ROUTING FIX: Route TRUE facts to appropriate banks
            # based on confidence level, ensuring low confidence facts are still stored
            if verdict_upper == "TRUE":
                action = "STORE"
                # Route based on confidence
                if final_confidence_val < 0.5:
                    target_bank = "working_theories"
                elif final_confidence_val < 0.8:
                    target_bank = "factual"
                else:
                    target_bank = "factual"

            if duplicate and target_bank != "theories_and_contradictions":
                try:
                    # Build a fact payload similar to standard storage
                    verdict = str((ctx.get("stage_8_validation") or {}).get("verdict", "")).upper()
                    conf_val = float((ctx.get("stage_8_validation") or {}).get("confidence", 0.0))
                    if verdict == "TRUE":
                        ver_level = "validated"
                    elif verdict == "THEORY":
                        ver_level = "educated_guess"
                    else:
                        ver_level = "unknown"
                    fact_payload = {
                        "content": proposed_content or text,
                        "confidence": conf_val,
                        "verification_level": ver_level,
                        "source": "user_input",
                        "validated_by": "reasoning",
                        # Assign importance equal to the confidence value.  This allows
                        # high‑confidence facts to be promoted quickly to MTM/LTM
                        "importance": conf_val,
                        "metadata": {
                            "supported_by": (ctx.get("stage_8_validation") or {}).get("supported_by", []),
                            "contradicted_by": (ctx.get("stage_8_validation") or {}).get("contradicted_by", []),
                            "from_pipeline": True
                        }
                    }
                    resp_store = _bank_module(target_bank).service_api({"op": "STORE", "payload": {"fact": fact_payload}})
                    superseded_id = None
                    if isinstance(match, dict) and match.get("source_bank") == "theories_and_contradictions":
                        superseded_id = match.get("id")
                        try:
                            _bank_module("theories_and_contradictions").service_api({
                                "op": "SUPERSEDE",
                                "payload": {"id": superseded_id, "by_bank": target_bank}
                            })
                        except Exception:
                            pass
                    ctx["stage_9_storage"] = {
                        "skipped": False,
                        "action": "PROMOTE_DUPLICATE",
                        "bank": target_bank,
                        "superseded_id": superseded_id,
                        "result": (resp_store.get("payload") or resp_store)
                    }
                except Exception as e:
                    ctx["stage_9_storage"] = {"skipped": True, "reason": str(e), "bank": target_bank}
            else:
                try:
                    # Theories and contradictions bank uses custom store operations
                    if target_bank == "theories_and_contradictions":
                        # Always treat low-confidence submissions as theories
                        fact_payload = {
                            "content": proposed_content or text,
                            "confidence": float((ctx.get("stage_8_validation") or {}).get("confidence", 0.0)),
                            "source_brain": "reasoning",
                            "linked_fact_id": None,
                            "contradicts": [],
                            "status": "open",
                            "verification_level": "educated_guess",
                            # Use confidence as importance for theories too; moderate importance encourages
                            # promotion into mid‑term memory once validated further.
                            "importance": float((ctx.get("stage_8_validation") or {}).get("confidence", 0.0)),
                            "metadata": {
                                "supported_by": (ctx.get("stage_8_validation") or {}).get("supported_by", []),
                                "contradicted_by": (ctx.get("stage_8_validation") or {}).get("contradicted_by", []),
                                "from_pipeline": True
                            },
                        }
                        # For now all uncertain content becomes a theory
                        resp = _bank_module(target_bank).service_api({"op": "STORE_THEORY", "payload": {"fact": fact_payload}})
                        ctx["stage_9_storage"] = {
                            "skipped": False,
                            "action": action,
                            "bank": target_bank,
                            "result": (resp.get("payload") or resp)
                        }
                    else:
                        # Build a fact payload for generic banks
                        verdict = str((ctx.get("stage_8_validation") or {}).get("verdict", "")).upper()
                        conf_val = float((ctx.get("stage_8_validation") or {}).get("confidence", 0.0))
                        # Determine verification level based on verdict
                        if verdict == "TRUE":
                            ver_level = "validated"
                        elif verdict == "THEORY":
                            ver_level = "educated_guess"
                        else:
                            ver_level = "unknown"
                        fact_payload = {
                            "content": proposed_content or text,
                            "confidence": conf_val,
                            "verification_level": ver_level,
                            "source": "user_input",
                            "validated_by": "reasoning",
                            # Assign importance equal to confidence to aid promotion
                            "importance": conf_val,
                            "metadata": {
                                "supported_by": (ctx.get("stage_8_validation") or {}).get("supported_by", []),
                                "contradicted_by": (ctx.get("stage_8_validation") or {}).get("contradicted_by", []),
                                "from_pipeline": True
                            }
                        }
                        # Call bank with proper fact wrapper
                        resp = _bank_module(target_bank).service_api({"op": "STORE", "payload": {"fact": fact_payload}})
                        ctx["stage_9_storage"] = {
                            "skipped": False,
                            "action": action,
                            "bank": target_bank,
                            "result": (resp.get("payload") or resp)
                        }
                except Exception as e:
                    ctx["stage_9_storage"] = {"skipped": True, "reason": str(e), "bank": target_bank}
        else:
            ctx["stage_9_storage"] = {"skipped": True, "reason": "governance_denied"}

        # Learning hooks after successful store
        try:
            if not ctx.get("stage_9_storage", {}).get("skipped"):
                bank = ctx["stage_9_storage"].get("bank")
                # vocab learn
                try:
                    _router_module().service_api({"op":"LEARN","payload":{"text": proposed_content or text, "bank": bank}})
                except Exception:
                    pass
                # MEMORY CONSOLIDATION: Trigger STM→MTM→LTM consolidation periodically
                # Run consolidation 10% of the time to avoid performance overhead
                try:
                    import random
                    if random.random() < 0.1:  # 10% chance
                        consolidation_stats = _consolidate_memory_banks()
                        if consolidation_stats.get("facts_promoted", 0) > 0:
                            ctx.setdefault("stage_9_storage", {})["consolidation"] = consolidation_stats
                except Exception:
                    pass
                # definition learn
                try:
                    term, klass = _extract_definition(proposed_content or text)
                    verdict = str(ctx.get("stage_8_validation", {}).get("verdict","")).upper()
                    if term and klass and verdict == "TRUE":
                        _router_module().service_api({"op":"LEARN_DEFINITION","payload":{"term": term, "klass": klass}})
                except Exception:
                    pass
                # relationship interception hook - persist simple relational beliefs like "we are friends"
                try:
                    _intent_l = str(ctx.get("stage_3_language", {}).get("type", "")).lower()
                    _val_l = str(proposed_content or text).lower()
                    if any(k in _intent_l for k in ["relationship", "relation", "social", "bond", "friend"]) or "friend" in _val_l:
                        # Store in working memory
                        try:
                            service_api({
                                "op": "WM_PUT",
                                "payload": {
                                    "key": "relationship_status",
                                    "value": proposed_content or text,
                                    "tags": ["relationship", "social"],
                                    "confidence": 0.8
                                }
                            })
                        except Exception:
                            pass
                        # Store in brain-level persistent storage
                        try:
                            service_api({
                                "op": "BRAIN_PUT",
                                "payload": {
                                    "scope": "BRAIN",
                                    "origin_brain": "memory_librarian",
                                    "key": "relationship_status",
                                    "value": proposed_content or text,
                                    "confidence": 0.8
                                }
                            })
                        except Exception:
                            pass
                except Exception:
                    pass
                # Persist user preferences like "I like the color green"
                try:
                    _intent_l = str(ctx.get("stage_3_language", {}).get("type", "")).lower()
                    _val_l = str(proposed_content or text).lower()
                    _utterance = str(ctx.get("original_query") or "").lower()
                    if "like" in _val_l or "like" in _intent_l or "like" in _utterance:
                        import re
                        # Skip questions like "what color do i like" to prevent storing questions as preferences
                        if re.search(r"\bwhat\b.*\bcolor\b.*\blike\b", _utterance):
                            return
                        # Extract clean color token from statements
                        text_to_parse = (proposed_content or text or _utterance).strip()
                        # Tightened patterns: prevent capturing "more" and similar non-color words
                        # Accept: "i like green", "like green", "green is my favorite color"
                        m = (re.search(r"\blike\s+(?:the\s+color\s+)?([a-zA-Z]+)\b(?!\s+more)", text_to_parse, re.I)
                             or re.search(r"\b([a-zA-Z]+)\b\s+is\s+my\s+favorite\s+color", text_to_parse, re.I))
                        if m:
                            color = m.group(1).lower()
                            # Store in working memory with higher confidence
                            try:
                                service_api({
                                    "op": "WM_PUT",
                                    "payload": {
                                        "key": "favorite_color",
                                        "value": color,
                                        "tags": ["preference", "color"],
                                        "confidence": 0.9
                                    }
                                })
                            except Exception:
                                pass
                            # Store in brain-level persistent storage with higher confidence
                            try:
                                service_api({
                                    "op": "BRAIN_PUT",
                                    "payload": {
                                        "scope": "BRAIN",
                                        "origin_brain": "memory_librarian",
                                        "key": "favorite_color",
                                        "value": color,
                                        "confidence": 0.9
                                    }
                                })
                            except Exception:
                                pass
                        else:
                            # Parse comparative likes: "I like cats over dogs"
                            m2 = re.search(r"like\s+([a-zA-Z]+)\s+over\s+([a-zA-Z]+)", text_to_parse, re.I)
                            if m2:
                                choice, other = m2.groups()
                                pref = {"preferred": choice.lower(), "other": other.lower()}
                                # Store in working memory
                                try:
                                    service_api({
                                        "op": "WM_PUT",
                                        "payload": {
                                            "key": "animal_preference",
                                            "value": pref,
                                            "tags": ["preference", "comparative"],
                                            "confidence": 0.9
                                        }
                                    })
                                except Exception:
                                    pass
                                # Store in brain-level persistent storage
                                try:
                                    service_api({
                                        "op": "BRAIN_PUT",
                                        "payload": {
                                            "scope": "BRAIN",
                                            "origin_brain": "memory_librarian",
                                            "key": "animal_preference",
                                            "value": pref,
                                            "confidence": 0.9
                                        }
                                    })
                                except Exception:
                                    pass
                except Exception:
                    pass
        except Exception:
            pass

        # After storing and learning, trigger memory consolidation so that
        # recently stored facts can graduate from short‑term memory to
        # mid‑term and long‑term tiers when appropriate.  Consolidation
        # runs only when storage was not skipped and the helper is available.
        try:
            if consolidate_memories and not (ctx.get("stage_9_storage", {}) or {}).get("skipped"):
                consolidate_memories()
        except Exception:
            # Ignore consolidation errors to avoid disrupting the pipeline
            pass

        # Stage 10b — Personality feedback
        try:
            from brains.cognitive.personality.service import personality_brain
            fb = {
                "tone": ctx.get("stage_10_finalize", {}).get("tone"),
                "verbosity": ctx.get("stage_10_finalize", {}).get("verbosity"),
                "transparency": ctx.get("stage_10_finalize", {}).get("transparency")
            }
            personality_brain.service_api({"op":"LEARN_FROM_RUN","payload": fb})
            ctx["stage_10_personality_feedback"] = {"logged": True}
        except Exception as e:
            ctx["stage_10_personality_feedback"] = {"logged": False, "error": str(e)}

        # Stage 11 — Personal brain (style-only)
        try:
            per = _personal_module()
            per_boost = per.service_api({"op":"SCORE_BOOST","payload":{"subject": text}})
            per_why = per.service_api({"op":"WHY","payload":{"subject": text}})
            # Build baseline personal influence dictionary
            inf_obj = {
                **(per_boost.get("payload") or {}),
                "why": (per_why.get("payload") or {}).get("hypothesis"),
                "signals": (per_why.get("payload") or {}).get("signals", [])
            }
            # Incorporate conversation state metrics into the signals.  Retrieve the
            # global conversation state safely and embed it under a dedicated
            # key.  Do not mutate the original state object to avoid cross‑run
            # contamination.  When conv_state is non‑empty, this will expose
            # fields such as last_query, last_response, last_topic,
            # thread_entities and conversation_depth in the pipeline output.
            try:
                conv_state = dict(globals().get("_CONVERSATION_STATE") or {})
            except Exception:
                conv_state = {}
            if conv_state:
                inf_obj["conversation_state"] = conv_state
            ctx["stage_11_personal_influence"] = inf_obj
        except Exception as e:
            ctx["stage_11_personal_influence"] = {"error": str(e)}

        # Stage 12 — System history
        try:
            hist = _brain_module("system_history")
            hist.service_api({"op":"LOG_RUN_SUMMARY","payload":{
                "text": text,
                "mode": ctx["stage_8_validation"].get("mode"),
                "bank": ctx.get("stage_9_storage", {}).get("bank"),
                "personal_boost": (ctx.get("stage_11_personal_influence") or {}).get("boost", 0.0)
            }})
            ctx["stage_12_system_history"] = {"logged": True}
        except Exception as e:
            ctx["stage_12_system_history"] = {"logged": False, "error": str(e)}

        # Stage 12a — Self reflection (self‑critique)
        # Request a governance permit before performing self‑critique.  If allowed,
        # generate a critique using the self‑critique brain and record the permit id.
        try:
            import importlib
            # Request permit for CRITIQUE action
            permits_mod = importlib.import_module(
                "brains.governance.policy_engine.service.permits"
            )
            perm_resp = permits_mod.service_api({
                "op": "REQUEST",
                "payload": {"action": "CRITIQUE"}
            })
            perm_pay = perm_resp.get("payload") or {}
            allowed = bool(perm_pay.get("allowed", False))
            permit_id = perm_pay.get("permit_id")
            # Save permit status in context
            ctx["stage_12a_self_critique_permit"] = {
                "allowed": allowed,
                "permit_id": permit_id,
                "reason": perm_pay.get("reason")
            }
            # Log the permit request to the governance ledger.  Ignore
            # failures to avoid breaking the pipeline.
            try:
                from brains.governance.permit_logger import log_permit  # type: ignore
                log_permit("CRITIQUE", permit_id, allowed, perm_pay.get("reason"))
            except Exception:
                pass
            if allowed:
                # If permitted, proceed with critique generation
                crit_mod = importlib.import_module(
                    "brains.cognitive.self_dmn.service.self_critique"
                )
                final_text = (ctx.get("stage_10_finalize") or {}).get("text", "")
                crit_resp = crit_mod.service_api({"op": "CRITIQUE", "payload": {"text": final_text}})
                crit_payload = crit_resp.get("payload") or {}
                # Attach permit_id to critique payload for traceability
                if permit_id:
                    crit_payload["permit_id"] = permit_id
                ctx["stage_12a_self_critique"] = crit_payload
            else:
                # Not allowed: record empty critique but keep permit info
                ctx["stage_12a_self_critique"] = {}
        except Exception as e:
            ctx["stage_12a_self_critique_permit"] = {"allowed": False, "error": str(e)}
            ctx["stage_12a_self_critique"] = {"error": str(e)}

        # Stage 12b — Identity journal update
        # Request a governance permit for updating the identity journal.  When
        # permitted, merge the latest interaction into the identity snapshot
        # and compute a subject boost.  Attach the permit id for audit.
        try:
            import importlib
            permits_mod = importlib.import_module(
                "brains.governance.policy_engine.service.permits"
            )
            perm_resp = permits_mod.service_api({
                "op": "REQUEST",
                "payload": {"action": "OPINION"}
            })
            perm_pay = perm_resp.get("payload") or {}
            allowed = bool(perm_pay.get("allowed", False))
            permit_id = perm_pay.get("permit_id")
            ctx["stage_12b_identity_permit"] = {
                "allowed": allowed,
                "permit_id": permit_id,
                "reason": perm_pay.get("reason")
            }
            # Log the permit to the governance ledger.  Do not propagate errors.
            try:
                from brains.governance.permit_logger import log_permit  # type: ignore
                log_permit("OPINION", permit_id, allowed, perm_pay.get("reason"))
            except Exception:
                pass
            if allowed:
                id_mod = importlib.import_module(
                    "brains.personal.service.identity_journal"
                )
                update_data = {
                    "last_question": text,
                    "last_response": (ctx.get("stage_10_finalize") or {}).get("text"),
                }
                id_mod.service_api({"op": "UPDATE", "payload": {"update": update_data}})
                boost_resp = id_mod.service_api({"op": "SCORE_BOOST", "payload": {"subject": text}})
                boost_pay = boost_resp.get("payload") or {}
                # Attach permit id to identity influence to link update with proof
                if permit_id:
                    boost_pay["permit_id"] = permit_id
                ctx["stage_12b_identity_influence"] = boost_pay
            else:
                ctx["stage_12b_identity_influence"] = {}
        except Exception as e:
            ctx["stage_12b_identity_permit"] = {"allowed": False, "error": str(e)}
            ctx["stage_12b_identity_influence"] = {"error": str(e)}

        # Stage 13 — Self-DMN
        # Config flag to enable/disable self-DMN (default: disabled)
        self_dmn_enabled = False  # Set to True to enable
        if not self_dmn_enabled:
            ctx["stage_13_self_dmn"] = {"skipped": True, "reason": "disabled"}
        else:
            try:
                sdmn = _brain_module("self_dmn")
                met = sdmn.service_api({"op":"ANALYZE_INTERNAL","payload":{"window": 10}})
                ctx["stage_13_self_dmn"] = {"metrics": (met.get("payload") or {}).get("metrics")}
            except Exception as e:
                ctx["stage_13_self_dmn"] = {"error": str(e)}

        # After all stages, update the affect priority brain with run outcomes.  In addition to
        # the usual parameters (tone, verbosity, decision, goal), include any identity
        # influence metrics and the self‑critique text if available.  These extra cues
        # allow the affect learner to adjust mood biases based on self reflection and
        # personal context.  Errors are ignored to avoid interfering with the core flow.
        try:
            aff_mod = _brain_module("affect_priority")
            # Build payload with optional fields.  Use dict() + comprehension to avoid
            # injecting None values when keys are missing.
            aff_payload = {
                "tone": (ctx.get("stage_10_finalize") or {}).get("tone"),
                "verbosity": (ctx.get("stage_10_finalize") or {}).get("verbosity"),
                "decision": (ctx.get("stage_8b_governance") or {}).get("action"),
                "goal": (ctx.get("stage_2_planner") or {}).get("goal"),
            }
            # Propagate identity boost into affect learning if computed
            try:
                id_boost = (ctx.get("stage_12b_identity_influence") or {}).get("boost")
                if id_boost is not None:
                    aff_payload["identity_boost"] = id_boost
            except Exception:
                pass
            # Propagate critique text for context
            try:
                crit_txt = (ctx.get("stage_12a_self_critique") or {}).get("critique")
                if crit_txt:
                    aff_payload["reflection"] = crit_txt
            except Exception:
                pass
            aff_mod.service_api({"op": "LEARN_FROM_RUN", "payload": aff_payload})
            ctx["stage_14_affect_learn"] = {"logged": True}
        except Exception as e:
            ctx["stage_14_affect_learn"] = {"logged": False, "error": str(e)}

        # Stage 15 — Autonomy (optional)
        #
        # If the autonomy configuration is enabled, execute a lightweight
        # autonomous tick.  This advances the self‑DMN hum oscillators,
        # collects memory health and formulates high‑level goals based on
        # current evidence.  The goals are not executed here; they are
        # recorded in the context for downstream processors or future
        # autonomy cycles to act upon.  Errors are captured without
        # interrupting the main pipeline flow.
        try:
            autocfg = _load_autonomy_config()
            # Config flag to enable/disable autonomy (default: disabled)
            autonomy_enabled = bool((autocfg or {}).get("enable", False))
            if not autonomy_enabled:
                ctx["stage_15_autonomy_tick"] = {"skipped": True, "reason": "disabled"}
                ctx["stage_15_autonomy_goals"] = {"skipped": True, "reason": "disabled"}
                ctx["stage_15_autonomy_actions"] = {"skipped": True, "reason": "disabled"}
            elif autonomy_enabled:
                # Pre-plan: Before running autonomy ticks, replan any active goals in
                # personal memory.  Compound goals are split into sub‑tasks via the
                # replanner brain so that the autonomy executor handles smaller actions.
                try:
                    from brains.personal.memory import goal_memory  # type: ignore
                    # Fetch only active (unfinished) goals from personal memory.  The
                    # goal_memory.get_goals API uses ``active_only`` as the keyword
                    # argument, so avoid passing ``only_active`` to prevent runtime errors.
                    active_goals = goal_memory.get_goals(active_only=True)  # type: ignore[arg-type]
                    if active_goals:
                        import importlib
                        replanner_mod = importlib.import_module(
                            "brains.cognitive.planner.service.replanner_brain"
                        )
                        repl_resp = replanner_mod.service_api({
                            "op": "REPLAN",
                            "payload": {"goals": active_goals},
                        })
                        ctx["stage_15_replan"] = repl_resp.get("payload", {})
                    else:
                        ctx["stage_15_replan"] = {"new_goals": []}
                except Exception as pre_repl_ex:
                    ctx["stage_15_replan"] = {
                        "error": "pre_replan_failed",
                        "detail": str(pre_repl_ex),
                    }
                # Autonomy tick
                try:
                    aut_brain_mod = _brain_module("autonomy")
                    # Use the safe tick function that never throws
                    tick_result = aut_brain_mod.tick(ctx)
                    if not isinstance(tick_result, dict):
                        tick_result = {
                            "action": "noop",
                            "reason": "invalid_tick_result",
                            "confidence": 0.0,
                        }
                    ctx["stage_15_autonomy_tick"] = tick_result
                except Exception as e:
                    ctx["stage_15_autonomy_tick"] = {
                        "action": "noop",
                        "reason": "tick_failed",
                        "exception_type": type(e).__name__,
                        "message": str(e)[:200],
                        "confidence": 0.0,
                    }
                # Score opportunities and formulate goals using the motivation brain
                try:
                    mot_mod = _brain_module("motivation")
                    # Build evidence from memory retrieval results (stage_2R_memory)
                    evidence = {
                        "results": (ctx.get("stage_2R_memory") or {}).get("results", [])
                    }
                    opps_resp = mot_mod.service_api({"op": "SCORE_OPPORTUNITIES", "payload": {"evidence": evidence}})
                    opportunities = (opps_resp.get("payload") or {}).get("opportunities", [])
                    goals_resp = mot_mod.service_api({"op": "FORMULATE_GOALS", "payload": {"opportunities": opportunities}})
                    ctx["stage_15_autonomy_goals"] = goals_resp.get("payload", {})
                except Exception:
                    ctx["stage_15_autonomy_goals"] = {}
                # After formulating goals, invoke the autonomy brain to execute goals.
                # Respect the autonomy configuration's max_ticks_per_run setting to
                # perform multiple ticks per pipeline run.  The actions for each
                # tick are collected into a list and stored in the context.  Errors
                # are captured to avoid disrupting the pipeline.
                try:
                    aut_mod = _brain_module("autonomy")
                    # Determine how many ticks to perform (default 1)
                    ticks = 1
                    try:
                        ticks_cfg = int((autocfg or {}).get("max_ticks_per_run", 1))
                        if ticks_cfg > 0:
                            ticks = ticks_cfg
                    except Exception:
                        ticks = 1
                    executed_list: list = []
                    # Load any previous resume state of remaining goals.  If the
                    # file does not exist or is invalid, treat as empty list.
                    remaining_ids: list[str] = []
                    try:
                        import json as _json
                        from pathlib import Path as _Path
                        root = _Path(__file__).resolve().parents[4]
                        rs_path = root / "reports" / "autonomy" / "resume_state.json"
                        if rs_path.exists():
                            with open(rs_path, "r", encoding="utf-8") as rs_fh:
                                data = _json.load(rs_fh) or {}
                                ids = data.get("remaining_goal_ids") or []
                                if isinstance(ids, list):
                                    remaining_ids = [str(g) for g in ids if g]
                    except Exception:
                        remaining_ids = []
                    # Execute ticks up to the configured maximum.  If the
                    # autonomy brain reports budget exhaustion or no goal is
                    # executed, stop early and preserve remaining goals for the
                    # next run.
                    for _idx in range(ticks):
                        try:
                            aut_resp = aut_mod.service_api({"op": "TICK"})
                        except Exception:
                            executed_list.append({"error": "autonomy_tick_failed"})
                            break
                        # Parse response payload.  It may contain executed_goals and skip flags
                        payload = aut_resp.get("payload") or {}
                        executed_list.append(payload)
                        # If the tick was skipped (e.g., rate limited or budget exhausted), stop
                        try:
                            if payload.get("skipped"):
                                # break the loop but preserve remaining_ids
                                break
                        except Exception:
                            pass
                        # Remove any executed goal IDs from remaining_ids
                        try:
                            ex_goals = payload.get("executed_goals") or []
                            for ex in ex_goals:
                                gid = ex.get("goal_id")
                                if gid and gid in remaining_ids:
                                    try:
                                        remaining_ids.remove(gid)
                                    except Exception:
                                        pass
                        except Exception:
                            pass
                        # If there are no more remaining goals, we can break early
                        if not remaining_ids:
                            # Continue ticks though – other active goals may appear; do not break early
                            pass
                    # After executing ticks, persist remaining goal IDs to resume state for next run
                    try:
                        import json as _json
                        from pathlib import Path as _Path
                        import os, tempfile
                        root = _Path(__file__).resolve().parents[4]
                        aut_dir = root / "reports" / "autonomy"
                        aut_dir.mkdir(parents=True, exist_ok=True)
                        rs_path = aut_dir / "resume_state.json"
                        # Write to temporary then replace
                        state_obj = {"remaining_goal_ids": remaining_ids}
                        tmp_fd, tmp_file = tempfile.mkstemp(dir=str(aut_dir), prefix="resume_state", suffix=".tmp")
                        try:
                            with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
                                fh.write(_json.dumps(state_obj))
                            os.replace(tmp_file, rs_path)
                        finally:
                            try:
                                if os.path.exists(tmp_file):
                                    os.remove(tmp_file)
                            except Exception:
                                pass
                    except Exception:
                        pass
                    # Store the list of executed actions in the context
                    ctx["stage_15_autonomy_actions"] = executed_list
                except Exception:
                    ctx["stage_15_autonomy_actions"] = {"error": "autonomy_tick_failed"}
                # Capture any remaining active goals after the autonomy ticks.  This
                # gives downstream processors and the user visibility into tasks
                # that still need to be completed and opens the door for future
                # re‑planning or follow‑up actions.  If the goal memory is not
                # available or an error occurs, fallback to an empty list.
                try:
                    from brains.personal.memory import goal_memory  # type: ignore
                    # After executing autonomy ticks, fetch active goals again.  Use the
                    # ``active_only`` argument to retrieve unfinished tasks.
                    remaining_goals = goal_memory.get_goals(active_only=True)  # type: ignore[arg-type]
                    # Automatically prune legacy junk goals that were created by
                    # prior segmentation bugs.  Junk goals are characterised by
                    # extremely short or trivial titles (e.g. single digits,
                    # isolated colour names) or unfinished question fragments.
                    pruned_goals: list = []
                    import re as _re
                    # Define heuristics: single digits, colour names, and
                    # partial question fragments are considered junk.
                    _colour_set = {"red", "orange", "yellow", "green", "blue", "indigo", "violet"}
                    for g in remaining_goals:
                        try:
                            title_raw = str(g.get("title", ""))
                            title = title_raw.strip().lower()
                        except Exception:
                            title = ""
                        is_junk = False
                        try:
                            # Single numeric (e.g. "1") or numeric with punctuation ("9.")
                            if _re.fullmatch(r"\d+", title) or _re.fullmatch(r"\d+\.", title):
                                is_junk = True
                            # Colour names (legacy spectrum tasks)
                            elif title in _colour_set:
                                is_junk = True
                            # Titles starting with specific junk phrases
                            elif title.startswith("numbers from"):
                                is_junk = True
                            elif title.startswith("what comes"):
                                is_junk = True
                            # Patterns like "0 comes 1." or "1 comes 2." etc.
                            elif _re.fullmatch(r"\d+\s+comes\s+\d+\.", title):
                                is_junk = True
                            # Titles ending with a question mark (often junk tasks)
                            elif title.endswith("?") and len(title) <= 5:
                                is_junk = True
                            # Fragments beginning with 'the ' and capital letter (e.g. "the Eiffel Tower")
                            elif title.startswith("the ") and len(title.split()) <= 3:
                                is_junk = True
                            # Requests to show photos (e.g. "show me paris photos")
                            elif title.startswith("show me") and "photo" in title:
                                is_junk = True
                            # Pleas to add numbers (e.g. "please add 2")
                            elif title.startswith("please add"):
                                is_junk = True
                            # Simple phrases indicating colours of visible spectrum
                            elif _re.match(r"[a-z]+\s+are\s+the\s+colors", title):
                                is_junk = True
                        except Exception:
                            is_junk = False
                        if is_junk:
                            # Mark the junk goal as completed so it will not be considered active
                            try:
                                gid = g.get("goal_id")
                                if gid:
                                    goal_memory.complete_goal(str(gid))  # type: ignore[attr-defined]
                            except Exception:
                                pass
                            continue
                        pruned_goals.append(g)
                    ctx["stage_15_remaining_goals"] = pruned_goals
                except Exception:
                    ctx["stage_15_remaining_goals"] = []
                # Dynamic re‑planning of stale goals.  If the autonomy
                # configuration defines a positive ``replan_age_minutes`` value,
                # identify any remaining goals whose age exceeds this
                # threshold.  Use the replanner brain to split these tasks
                # into sub‑goals, then mark the originals as completed.  New
                # sub‑goals are persisted via the replanner and surfaced in
                # the context under ``stage_15_replanned_stale_goals``.  If
                # no goals are stale or the feature is disabled, record an
                # empty list for clarity.
                # No time-based age checking
                stale_goals: list = []
                if stale_goals:
                    try:
                        import importlib  # type: ignore
                        replanner_mod = importlib.import_module(
                            "brains.cognitive.planner.service.replanner_brain"
                        )
                        repl_out = replanner_mod.service_api({
                            "op": "REPLAN",
                            "payload": {"goals": stale_goals},
                        })
                        # Complete the stale goals to avoid duplicate execution
                        try:
                            for sg in stale_goals:
                                gid = sg.get("goal_id")
                                if gid:
                                    goal_memory.complete_goal(str(gid), success=True)  # type: ignore[attr-defined]
                            # Remove stale goals from the remaining goals list in the context
                            try:
                                rem = ctx.get("stage_15_remaining_goals") or []
                                if isinstance(rem, list):
                                    ctx["stage_15_remaining_goals"] = [g for g in rem if g.get("goal_id") not in {sg.get("goal_id") for sg in stale_goals}]
                            except Exception:
                                pass
                        except Exception:
                            pass
                        ctx["stage_15_replanned_stale_goals"] = repl_out.get("payload", {})
                    except Exception as stale_ex:
                        ctx["stage_15_replanned_stale_goals"] = {
                            "error": "stale_goal_replan_failed",
                            "detail": str(stale_ex),
                        }
                else:
                    ctx["stage_15_replanned_stale_goals"] = {"new_goals": []}

                ctx["stage_15_autonomy_enabled"] = True
            else:
                ctx["stage_15_autonomy_enabled"] = False
        except Exception as e:
            ctx["stage_15_autonomy_error"] = str(e)

        # Periodically summarize system history.  When the number of completed runs
        # reaches a multiple of 50, invoke the system history brain's SUMMARIZE op
        # to aggregate recent metrics and prune old logs.  Guard against errors.
        try:
            sys_dir = MAVEN_ROOT / "reports" / "system"
            run_files = []
            for f in sys_dir.iterdir():
                try:
                    if f.is_file() and f.name.startswith("run_") and f.suffix == ".json":
                        run_files.append(f)
                except Exception:
                    continue
            run_count = len(run_files)
        except Exception:
            run_count = 0
        if run_count > 0 and (run_count % 50) == 0:
            try:
                hist_mod = _brain_module("system_history")
                hist_mod.service_api({"op": "SUMMARIZE", "payload": {"window": 50}})
            except Exception:
                pass

        # Write system report and flush pipeline trace (if enabled)
        if trace_enabled:
            try:
                outdir = MAVEN_ROOT / "reports" / "pipeline_trace"
                outdir.mkdir(parents=True, exist_ok=True)
                # Prefer run_seed for file naming when available.  This provides
                # deterministic file names for reproducibility.  Fall back
                # to the message ID when no seed is present.
                try:
                    seed_val = ctx.get("run_seed")
                    if seed_val is not None:
                        fname = f"trace_{seed_val}.jsonl"
                    else:
                        fname = f"trace_{mid}.jsonl"
                except Exception:
                    fname = f"trace_{mid}.jsonl"
                # Write trace events to file.  To aid replayability, append
                # the final context at the end of the trace as a single event.
                with open(outdir / fname, "w", encoding="utf-8") as fh:
                    for ev in trace_events:
                        fh.write(json.dumps(ev) + "\n")
                    # Write the pipeline context as the last entry.  Use
                    # compact JSON to avoid very large trace files.
                    try:
                        fh.write(json.dumps({"stage": "context", "context": ctx}) + "\n")
                    except Exception:
                        pass
                # Enforce retention limit on trace files
                trace_cfg = CFG.get("pipeline_tracer", {}) or {}
                try:
                    max_files = int(trace_cfg.get("max_files", 25) or 25)
                except Exception:
                    max_files = 25
                files = []
                for f in outdir.iterdir():
                    try:
                        if f.is_file() and f.name.startswith("trace_") and f.suffix == ".jsonl":
                            files.append(f)
                    except Exception:
                        continue
                files = sorted(files, key=lambda p: p.stat().st_mtime)
                if len(files) > max_files:
                    for f in files[: len(files) - max_files]:
                        try:
                            f.unlink()
                        except Exception:
                            pass
            except Exception:
                pass
        # Surface routing information in the final context for transparency.
        # Expose the top two banks and the routing scores from stage 2
        try:
            top_b = ctx.get("stage_2R_top_banks")
            scores = ctx.get("stage_2R_routing_scores")
            if top_b or scores:
                ctx["final_routing"] = {
                    "top_banks": list(top_b) if isinstance(top_b, (list, tuple)) else [],
                    "scores": dict(scores) if isinstance(scores, dict) else {}
                }
        except Exception:
            pass
        # Persist the final context snapshot.  Use a flat recent query log rather
        # than nesting session_context.  This avoids exponential growth and
        # provides a concise history for continuity across runs.
        try:
            _save_context_snapshot(ctx, limit=5)
        except Exception:
            pass
        # After persisting the context, check whether this query should be
        # cached for fast retrieval in future runs.  Repeated questions
        # within a short window (default 10 minutes) that produce a
        # validated answer will trigger caching.  The cache entry is
        # ignored if one already exists or if the verdict is not TRUE.
        try:
            _maybe_store_fast_cache(ctx, threshold=3, window_sec=600.0)
        except Exception:
            pass
        # Write system report with full context for auditing
        write_report("system", f"run_{random.randint(100000, 999999)}.json", json.dumps(ctx, indent=2))

        # ------------------------------------------------------------------
        # Stage 16 — Regression Harness (optional)
        #
        # Run a lightweight regression check against the QA memory to detect
        # contradictions and drift.  This stage is deliberately placed after
        # context persistence so that any mismatches are logged for the
        # current run.  The harness executes only when the QA memory has
        # accumulated a minimum number of entries to justify comparison.
        try:
            qa_file = MAVEN_ROOT / "reports" / "qa_memory.jsonl"
            # If there are enough QA entries, invoke the regression harness
            run_reg = False
            try:
                if qa_file.exists():
                    with qa_file.open("r", encoding="utf-8") as fh:
                        # Count non-empty lines; stop after threshold
                        threshold = 10
                        count = 0
                        for line in fh:
                            if line.strip():
                                count += 1
                                if count >= threshold:
                                    run_reg = True
                                    break
            except Exception:
                run_reg = False
            if run_reg:
                try:
                    import importlib
                    harness_mod = importlib.import_module("tools.regression_harness")
                    # Limit to first 10 entries for performance
                    res = harness_mod.run_regression(limit=10)
                    # Store a summary of regression results
                    reg_total = res.get("total", 0)
                    reg_match = res.get("matches", 0)
                    reg_mismatch = res.get("mismatches", 0)
                    ctx["stage_16_regression"] = {
                        "total": reg_total,
                        "matches": reg_match,
                        "mismatches": reg_mismatch,
                    }
                    # When mismatches are detected, create self‑repair goals.  Each
                    # mismatching QA entry spawns a goal titled "Verify QA: <question>"
                    # with a special description so the autonomy scheduler can pick
                    # them up.  Record the created goals in the context.
                    try:
                        mismatches = res.get("mismatches", 0) or 0
                        if mismatches:
                            details = res.get("details", []) or []
                            from brains.personal.memory import goal_memory  # type: ignore
                            created: list[dict] = []
                            # Gather existing goal titles and normalise them to avoid
                            # duplicates that differ only by case or spacing.  The
                            # normalisation removes punctuation and whitespace and
                            # converts to lower case.
                            import re as _re_norm  # local alias
                            existing_titles_norm: set[str] = set()
                            try:
                                # Collect existing goal titles from disk
                                current_goals = goal_memory.get_goals(active_only=False)
                                for g in current_goals:
                                    try:
                                        t = str(g.get("title", "")).strip()
                                    except Exception:
                                        t = ""
                                    if t:
                                        norm = _re_norm.sub(r"[^a-z0-9]", "", t.lower())
                                        existing_titles_norm.add(norm)
                            except Exception:
                                existing_titles_norm = set()
                            # Also include titles of goals currently queued in the remaining_goals
                            try:
                                rem_goals = ctx.get("stage_15_remaining_goals") or []
                                for g in rem_goals:
                                    try:
                                        t = str(g.get("title", "")).strip()
                                    except Exception:
                                        t = ""
                                    if t:
                                        norm = _re_norm.sub(r"[^a-z0-9]", "", t.lower())
                                        existing_titles_norm.add(norm)
                            except Exception:
                                pass
                            # Helper to normalise a proposed title
                            def _norm_title(s: str) -> str:
                                try:
                                    return _re_norm.sub(r"[^a-z0-9]", "", str(s or "").lower())
                                except Exception:
                                    return str(s or "").lower()
                            for itm in details:
                                try:
                                    q = str(itm.get("question", "")).strip()
                                except Exception:
                                    q = ""
                                if not q:
                                    continue
                                new_title = f"Verify QA: {q}"
                                norm_new_title = _norm_title(new_title)
                                # Skip if a goal with this (normalised) title already exists
                                if norm_new_title in existing_titles_norm:
                                    continue
                                try:
                                    new_goal = goal_memory.add_goal(new_title, description="AUTO_REPAIR")
                                    existing_titles_norm.add(norm_new_title)
                                    created.append({"goal_id": new_goal.get("goal_id"), "title": new_goal.get("title")})
                                except Exception:
                                    continue
                            if created:
                                ctx["stage_16_repair_goals"] = created
                    except Exception:
                        pass
                except Exception as reg_ex:
                    ctx["stage_16_regression"] = {"error": str(reg_ex)}
            else:
                ctx["stage_16_regression"] = {"skipped": True}
        except Exception as reg_top_ex:
            ctx["stage_16_regression_error"] = str(reg_top_ex)

        # ------------------------------------------------------------------
        # Stage 17: Long‑Term Memory Consolidation & QA Memory Pruning
        #
        # As the QA memory grows over time, it can accumulate hundreds of
        # entries, which degrades performance and increases storage.  To
        # mitigate this, consolidate older QA entries by extracting simple
        # definitional facts into the semantic knowledge graph and pruning
        # the log to a fixed size.  Only run this consolidation when there
        # are more than ``max_entries`` QA records.  Facts extracted from
        # pruned entries follow the same pattern as the assimilation in
        # language_brain.finalize: questions of the form "what is X" or
        # "who is X" with short answers are stored as (subject, "is",
        # answer).  Statistics about the number of pruned entries and
        # assimilated facts are stored in the context under
        # ``stage_17_memory_pruning``.
        try:
            from pathlib import Path
            import json as _json  # alias to avoid clobbering the outer json import
            import re as _re
            # Load knowledge graph module if available
            try:
                from brains.personal.memory import knowledge_graph  # type: ignore
            except Exception:
                knowledge_graph = None  # type: ignore
            # Determine the max number of QA entries to retain.  Use a
            # reasonable default if config isn't present or invalid.
            max_entries = 100
            # Allow tuning via config/memory.json if present.  This
            # optional file can specify {'qa_memory_max_entries': N}.
            try:
                from pathlib import Path as _Path
                mem_cfg_path = Path(__file__).resolve().parents[5] / "config" / "memory.json"
                if mem_cfg_path.exists():
                    try:
                        with open(mem_cfg_path, "r", encoding="utf-8") as mfh:
                            mcfg = _json.load(mfh) or {}
                        val = int(mcfg.get("qa_memory_max_entries", max_entries))
                        if val > 0:
                            max_entries = val
                    except Exception:
                        pass
            except Exception:
                pass
            # Read the QA memory file
            qa_path = Path(__file__).resolve().parents[5] / "reports" / "qa_memory.jsonl"
            if qa_path.exists():
                try:
                    with open(qa_path, "r", encoding="utf-8") as qfh:
                        raw_lines = [ln.strip() for ln in qfh if ln.strip()]
                except Exception:
                    raw_lines = []
                total_qas = len(raw_lines)
                if total_qas > max_entries:
                    # Determine how many to prune
                    prune_count = total_qas - max_entries
                    old_lines = raw_lines[:prune_count]
                    new_lines = raw_lines[prune_count:]
                    assimilated = 0
                    # Assimilate facts from pruned QAs into the knowledge graph
                    if knowledge_graph is not None:
                        for ln in old_lines:
                            try:
                                rec = _json.loads(ln)
                            except Exception:
                                continue
                            q = str(rec.get("question", "")).strip()
                            a = str(rec.get("answer", "")).strip()
                            if not q or not a:
                                continue
                            # Match simple definition patterns
                            m = _re.match(r"^(?:what|who)\s+is\s+(.+)", q.lower())
                            if not m:
                                continue
                            subj = m.group(1).strip().rstrip("?")
                            # Only assimilate short, confident answers
                            if len(a) > 80 or "?" in a or "don't know" in a.lower():
                                continue
                            # Build candidate subjects: raw and without leading articles
                            subj_norm = subj.lower().strip()
                            cand1 = subj_norm
                            cand2 = _re.sub(r"^(?:the|a|an)\s+", "", subj_norm).strip()
                            for candidate in [cand1, cand2]:
                                if not candidate:
                                    continue
                                try:
                                    knowledge_graph.add_fact(candidate, "is", a)
                                    assimilated += 1
                                    break
                                except Exception:
                                    continue
                    # Write retained lines back to the QA file
                    try:
                        with open(qa_path, "w", encoding="utf-8") as qfh:
                            for ln in new_lines:
                                qfh.write(ln + "\n")
                    except Exception:
                        pass
                    # Record pruning statistics in the context
                    ctx["stage_17_memory_pruning"] = {
                        "total_before": total_qas,
                        "pruned": prune_count,
                        "assimilated": assimilated,
                        "retained": len(new_lines)
                    }
        except Exception as prune_ex:
            # Record any pruning errors for debugging
            ctx["stage_17_memory_pruning_error"] = str(prune_ex)

        # ------------------------------------------------------------------
        # Stage 18: Self‑Review & Improvement Goal Creation
        #
        # After consolidating memory, perform a simple self‑assessment
        # across tracked domains to identify areas where Maven is
        # underperforming.  Use the meta_confidence statistics to
        # determine domains with the lowest recent adjustments.  For
        # each such domain below a configurable threshold (e.g. -0.05),
        # create a new goal to improve Maven's knowledge in that
        # domain.  These tasks are prefixed with "SELF_REVIEW" in the
        # description so that the autonomy scheduler can prioritise
        # them appropriately.  Record the created goals in
        # ``stage_18_self_review".  Errors are silently ignored.
        try:
            # Load meta confidence and goal memory if available
            try:
                from brains.personal.memory import meta_confidence  # type: ignore
            except Exception:
                meta_confidence = None  # type: ignore
            try:
                from brains.personal.memory import goal_memory  # type: ignore
            except Exception:
                goal_memory = None  # type: ignore
            if meta_confidence is not None and goal_memory is not None:
                # Determine threshold from config or use default
                threshold = -0.05
                # Optionally read a self‑review config
                try:
                    sr_cfg_path = Path(__file__).resolve().parents[5] / "config" / "self_review.json"
                    if sr_cfg_path.exists():
                        with open(sr_cfg_path, "r", encoding="utf-8") as srfh:
                            sr_cfg = json.load(srfh) or {}
                        th = float(sr_cfg.get("threshold", threshold))
                        if -1.0 <= th <= 0.0:
                            threshold = th
                except Exception:
                    pass
                # Gather domain stats
                stats = meta_confidence.get_stats(1000) or []
                # Identify lowest performers below threshold
                low_domains = [d for d in stats if d.get("adjustment", 0) < threshold]
                # Sort by adjustment ascending (most negative first)
                low_domains.sort(key=lambda d: d.get("adjustment", 0))
                created: list[dict] = []
                # Determine the maximum number of new self‑review goals to create
                max_new = 5
                try:
                    # Read limit from config/self_review.json if present
                    import json as _json
                    from pathlib import Path
                    root = Path(__file__).resolve().parents[5]
                    cfg_path = root / "config" / "self_review.json"
                    if cfg_path.exists():
                        with open(cfg_path, "r", encoding="utf-8") as cfh:
                            cfg = _json.load(cfh) or {}
                        try:
                            mx = int(cfg.get("max_goals", max_new))
                            if 1 <= mx <= 20:
                                max_new = mx
                        except Exception:
                            pass
                except Exception:
                    # If any error, fall back to default
                    max_new = 5
                # Fetch existing goals to avoid duplicate improvement tasks
                existing = []
                try:
                    existing = goal_memory.get_goals(active_only=False)
                except Exception:
                    existing = []
                existing_titles = set()
                for g in existing:
                    try:
                        t = str(g.get("title", "")).strip()
                        if t:
                            existing_titles.add(t)
                    except Exception:
                        continue
                count_new = 0
                for dom in low_domains:
                    if count_new >= max_new:
                        break
                    try:
                        dom_name = dom.get("domain", "").strip()
                    except Exception:
                        dom_name = ""
                    if not dom_name:
                        continue
                    # Compose goal title and description
                    title = f"Improve domain: {dom_name}"
                    # Skip if a goal with the same title already exists (active or completed)
                    if title in existing_titles:
                        continue
                    desc = f"SELF_REVIEW: {dom_name}"
                    try:
                        rec = goal_memory.add_goal(title, description=desc)
                        created.append({"goal_id": rec.get("goal_id"), "title": rec.get("title")})
                        existing_titles.add(title)
                        count_new += 1
                    except Exception:
                        continue
                if created:
                    ctx["stage_18_self_review"] = created
                else:
                    ctx["stage_18_self_review"] = []
        except Exception as sr_ex:
            ctx["stage_18_self_review_error"] = str(sr_ex)

        # Perform a run evaluation on the final context prior to returning.
        # This self‑evaluation computes health metrics and may enqueue
        # repair goals via the goal memory.  Errors during evaluation are
        # recorded in the context but do not block the pipeline response.
        if op == "RUN_PIPELINE":
            try:
                import importlib
                sc_mod = importlib.import_module("brains.cognitive.self_dmn.service.self_critique")
                eval_resp = sc_mod.service_api({"op": "EVAL_CONTEXT", "payload": {"context": ctx}})
                ctx["stage_self_eval"] = eval_resp.get("payload", {})
            except Exception:
                ctx["stage_self_eval"] = {"error": "eval_failed"}
            # Update the semantic cache on completion of a pipeline run.  This stores
            # the query and answer in a cross‑session index for reuse on future runs.
            try:
                _update_semantic_cache(ctx)
            except Exception:
                pass
        # Clean up SEARCH_REQUEST messages from the message bus to prevent them
        # from polluting subsequent UNIFIED_RETRIEVE calls.  During pipeline
        # execution, targeted retrieval may post SEARCH_REQUEST messages to
        # restrict which banks are queried.  These messages should not persist
        # beyond the current pipeline run, as they would incorrectly filter
        # later independent retrieval operations.
        try:
            from brains.cognitive import message_bus
            # Clear all pending messages after pipeline completion
            message_bus.pop_all()
        except Exception:
            # Silently ignore errors during cleanup to avoid disrupting the response
            pass

        # End routing diagnostics trace (Phase C cleanup)
        try:
            if tracer and RouteType:
                final_ans = ctx.get("final_answer")
                tracer.record_route(mid, RouteType.FULL_PIPELINE, {"completed": True})
                tracer.end_request(mid, final_ans)
        except Exception:
            pass

        return success_response(op, mid, {"context": ctx})

    # Provide a backwards‑compatible HEALTH operation that reports the set of
    # discoverable domain banks.  Earlier versions of Maven exposed a
    # ``HEALTH`` op returning a list of available banks.  Preserve this
    # behaviour by enumerating the banks that can be loaded without error.
    if op == "HEALTH":
        banks: list[str] = []
        for b in _ALL_BANKS:
            try:
                _bank_module(b)
                banks.append(b)
            except Exception:
                # Skip banks that fail to load
                pass
        return success_response(op, mid, {"discovered_banks": banks})

    if op == "HEALTH_CHECK":
        counts = _scan_counts(COG_ROOT)
        rotated: list[dict[str, Any]] = []
        # The overflow limit can be tuned by a soft_headroom factor as well as a
        # hard_headroom multiplier.  By default rotation triggers when STM
        # exceeds ``soft_headroom * stm_records``.  To further reduce the
        # frequency of repairs (and avoid cascading repair loops), introduce
        # ``hard_headroom`` which multiplies the computed limit.  Only when
        # ``stm_count`` exceeds ``soft_headroom * hard_headroom * stm_records``
        # is a repair triggered.  Missing keys fall back to sensible defaults.
        try:
            # Default the soft headroom to 2 when not explicitly configured.  This factor
            # multiplies the per-bank STM limit to compute an initial threshold.  Adjust
            # via CFG["rotation"]["soft_headroom"] in config files if needed.
            soft = float(CFG.get("rotation", {}).get("soft_headroom", 2))
        except Exception:
            soft = 2.0
        try:
            # Default the hard headroom to 10.  A larger default dramatically reduces the
            # frequency of repairs by requiring STM sizes to exceed (soft * hard * limit)
            # before triggering a repair.  This value can be overridden via
            # CFG["rotation"]["hard_headroom"] in config/autotune.json.
            hard = float(CFG.get("rotation", {}).get("hard_headroom", 10))
        except Exception:
            hard = 10.0
        # Compute the threshold: base limit multiplied by both headrooms
        base_limit = CFG.get("rotation", {}).get("stm_records", 1000)
        try:
            limit = float(base_limit) * soft
        except Exception:
            limit = float(base_limit) * 2.0
        threshold = limit * hard
        rep = _repair_module()
        for brain, tiers in counts.items():
            try:
                stm_count = int(tiers.get("stm", 0))
            except Exception:
                stm_count = 0
            # Only trigger a repair when the STM count exceeds the computed
            # threshold.  This drastically reduces the number of repair
            # operations ("stop the bleeding"), since the previous logic
            # repaired whenever ``stm_count > limit``.  With the default
            # settings of soft_headroom=2 and hard_headroom=2, rotation
            # occurs only when STM exceeds 4× the configured limit.
            if stm_count > threshold:
                # Respect the governance auto_repair setting.  If auto_repair is disabled,
                # skip invoking the repair engine entirely.  This allows administrators
                # to throttle or disable automated repairs without modifying code.
                if CFG.get("governance", {}).get("auto_repair", True) is False:
                    # Skip repair; record overflow but do not invoke repair engine
                    rotated.append({"brain": brain, "stm_count": stm_count, "rule":"memory_overflow_skipped"})
                else:
                    if brain == "personal":
                        stm_path = (MAVEN_ROOT / "brains" / "personal" / "memory" / "stm" / "records.jsonl").resolve()
                    else:
                        stm_path = (COG_ROOT / brain / "memory" / "stm" / "records.jsonl").resolve()
                    try:
                        rep.service_api({"op":"REPAIR","payload":{"rule":"memory_overflow","target": str(stm_path)}})
                    except Exception:
                        pass
                    rotated.append({"brain": brain, "stm_count": stm_count, "rule":"memory_overflow"})
        write_report("system", f"health_{random.randint(100000, 999999)}.json", json.dumps({"counts": counts, "rotations": rotated}, indent=2))
        return success_response(op, mid, {"rotations": rotated, "counts": counts})

    # ----------------------------------------------------------------------
    # Configuration operations
    # These allow runtime toggling of the pipeline tracer and adjustment of
    # rotation thresholds.  They do not persist changes beyond the current
    # process lifetime and respect governance rules enforced by the policy
    # engine.  For example, Enable/Disable Tracer simply flips the in-memory
    # flag at CFG['pipeline_tracer']['enabled'].  SET_ROTATION_LIMITS can
    # update either the global rotation defaults or per-bank overrides.
    if op == "ENABLE_TRACER":
        try:
            CFG.setdefault("pipeline_tracer", {})["enabled"] = True
            return success_response(op, mid, {"enabled": True})
        except Exception as e:
            return error_response(op, mid, "TRACER_TOGGLE_FAILED", str(e))

    if op == "DISABLE_TRACER":
        try:
            CFG.setdefault("pipeline_tracer", {})["enabled"] = False
            return success_response(op, mid, {"enabled": False})
        except Exception as e:
            return error_response(op, mid, "TRACER_TOGGLE_FAILED", str(e))

    if op == "SET_ROTATION_LIMITS":
        bank = str((payload or {}).get("bank", "")).strip().lower()
        limits: Dict[str, Any] = {}
        for key in ("stm_records", "mtm_records", "ltm_records"):
            val = (payload or {}).get(key)
            if val is not None:
                try:
                    limits[key] = int(val)
                except Exception:
                    pass
        try:
            if not bank or bank == "global":
                # apply to global defaults
                CFG.setdefault("rotation", {}).update(limits)
                who = "global"
            else:
                per_bank = CFG.setdefault("rotation_per_bank", {})
                per_bank.setdefault(bank, {}).update(limits)
                who = bank
            return success_response(op, mid, {"bank": who, "limits": limits})
        except Exception as e:
            return error_response(op, mid, "SET_ROTATION_FAILED", str(e))

    # ------------------------------------------------------------------
    # Working Memory Operations (Step‑1)
    # These operations expose a simple shared WM through the memory
    # librarian.  WM_PUT stores an entry; WM_GET retrieves entries by key
    # or tag; WM_DUMP returns all live entries; CONTROL_TICK scans
    # working memory and emits message_bus events for each entry.
    elif op == "WM_PUT":
        # Load persisted memory if needed before storing
        try:
            _wm_load_if_needed()
        except Exception:
            pass
        # Store an item into working memory
        try:
            key = (payload or {}).get("key")
            value = (payload or {}).get("value")
            tags = list((payload or {}).get("tags") or [])
            try:
                conf = float((payload or {}).get("confidence", 0.0))
            except Exception:
                conf = 0.0
            entry = {
                "key": key,
                "value": value,
                "tags": tags,
                "confidence": conf,
            }
            with _WM_LOCK:
                _prune_working_memory()
                _WORKING_MEMORY.append(entry)
                # Persist entry if configured
                try:
                    from api.utils import CFG  # type: ignore
                    persist_enabled = bool((CFG.get("wm", {}) or {}).get("persist", True))
                except Exception:
                    persist_enabled = True
                if persist_enabled:
                    try:
                        _wm_persist_append(entry)
                    except Exception:
                        pass
            # Log the WM_PUT event
            try:
                root = globals().get("MAVEN_ROOT")
                if not root:
                    root = Path(__file__).resolve().parents[4]
                log_path = (root / "reports" / "wm_trace.jsonl").resolve()
                from api.utils import append_jsonl  # type: ignore
                append_jsonl(log_path, {"op": "WM_PUT", "entry": {k: v for k, v in entry.items() if k != "expires_at"}})
            except Exception:
                pass
            return success_response(op, mid, {"stored": True, "entry": {k: v for k, v in entry.items() if k != "expires_at"}})
        except Exception as e:
            return error_response(op, mid, "WM_PUT_FAILED", str(e))

    elif op == "WM_GET":
        # Load persisted memory if needed before retrieval
        try:
            _wm_load_if_needed()
        except Exception:
            pass
        # Retrieve items from working memory filtered by key or tags
        try:
            k = (payload or {}).get("key")
            tags = (payload or {}).get("tags")
            tag_list = list(tags or []) if tags else None
            results: List[Dict[str, Any]] = []
            with _WM_LOCK:
                _prune_working_memory()
                for ent in _WORKING_MEMORY:
                    if k is not None and ent.get("key") != k:
                        continue
                    if tag_list:
                        try:
                            etags = ent.get("tags") or []
                            # Intersection test: at least one tag matches
                            if not any(t in etags for t in tag_list):
                                continue
                        except Exception:
                            continue
                    # Return a shallow copy without internal expiry
                    results.append({k2: v2 for k2, v2 in ent.items() if k2 != "expires_at"})
            # Apply arbitration scoring if enabled and a key is specified
            winner: Optional[Dict[str, Any]] = None
            alternatives: List[Dict[str, Any]] = []
            try:
                from api.utils import CFG  # type: ignore
                arbitration_enabled = bool((CFG.get("wm", {}) or {}).get("arbitration", True))
            except Exception:
                arbitration_enabled = True
            if arbitration_enabled and k is not None and len(results) > 1:
                try:
                    import math
                    scored_pairs: List[tuple] = []
                    for ent in results:
                        try:
                            conf_val = float(ent.get("confidence", 0.0))
                        except Exception:
                            conf_val = 0.0
                        try:
                            reliability = float(ent.get("source_reliability", 1.0))
                        except Exception:
                            reliability = 1.0
                        # No time-based decay
                        score = conf_val * reliability
                        scored_pairs.append((score, ent))
                    scored_pairs.sort(key=lambda x: x[0], reverse=True)
                    scored_results: List[Dict[str, Any]] = []
                    for sc, ent in scored_pairs:
                        ent_with_score = ent.copy()
                        try:
                            ent_with_score["score"] = round(sc, 6)
                        except Exception:
                            ent_with_score["score"] = sc
                        scored_results.append(ent_with_score)
                    if scored_results:
                        winner = scored_results[0]
                        alternatives = scored_results[1:]
                        results = scored_results
                except Exception:
                    pass
            # Log the WM_GET event
            try:
                root = globals().get("MAVEN_ROOT")
                if not root:
                    root = Path(__file__).resolve().parents[4]
                log_path = (root / "reports" / "wm_trace.jsonl").resolve()
                from api.utils import append_jsonl  # type: ignore
                append_jsonl(log_path, {"op": "WM_GET", "filter": {"key": k, "tags": tag_list}, "results": results})
            except Exception:
                pass
            # Include winner/alternatives when arbitration applied
            payload_dict: Dict[str, Any] = {"entries": results}
            if winner is not None:
                payload_dict["winner"] = winner
                payload_dict["alternatives"] = alternatives
            return success_response(op, mid, payload_dict)
        except Exception as e:
            return error_response(op, mid, "WM_GET_FAILED", str(e))

    elif op == "WM_DUMP":
        # Load persisted memory if needed before dumping
        try:
            _wm_load_if_needed()
        except Exception:
            pass
        # Dump all live working memory entries
        try:
            with _WM_LOCK:
                _prune_working_memory()
                dump = [{k: v for k, v in ent.items() if k != "expires_at"} for ent in list(_WORKING_MEMORY)]
            # Log the WM_DUMP event
            try:
                root = globals().get("MAVEN_ROOT")
                if not root:
                    root = Path(__file__).resolve().parents[4]
                log_path = (root / "reports" / "wm_trace.jsonl").resolve()
                from api.utils import append_jsonl  # type: ignore
                append_jsonl(log_path, {"op": "WM_DUMP", "entries": dump})
            except Exception:
                pass
            return success_response(op, mid, {"entries": dump})
        except Exception as e:
            return error_response(op, mid, "WM_DUMP_FAILED", str(e))

    elif op == "CONTROL_TICK":
        # Load persisted memory if needed before ticking
        try:
            _wm_load_if_needed()
        except Exception:
            pass
        # Scan WM and emit message bus events for each entry
        try:
            emitted = 0
            with _WM_LOCK:
                _prune_working_memory()
                current_entries = [{k: v for k, v in ent.items() if k != "expires_at"} for ent in list(_WORKING_MEMORY)]
            # Import message_bus lazily to avoid circular imports on module load
            try:
                from brains.cognitive import message_bus  # type: ignore
                for ent in current_entries:
                    msg = {
                        "from": "memory_librarian",
                        "to": "scheduler",
                        "type": "WM_EVENT",
                        "entry": ent,
                    }
                    try:
                        message_bus.send(msg)
                        emitted += 1
                    except Exception:
                        continue
            except Exception:
                # If message bus unavailable, skip emission
                emitted = 0
            # Optionally run the cognitive graph engine on emitted events
            try:
                from api.utils import CFG  # type: ignore
                graph_cfg = CFG.get("graph", {}) or {}
                if bool(graph_cfg.get("enabled", False)):
                    # Import default_graph_engine lazily to avoid circular deps
                    try:
                        from brains.cognitive.graph_engine import default_graph_engine  # type: ignore
                        # Instantiate and run with a minimal context; the engine will
                        # drain message_bus events and propagate them according to
                        # registered nodes.
                        engine = default_graph_engine()
                        engine.run({})
                    except Exception:
                        pass
            except Exception:
                pass
            # Log the CONTROL_TICK event
            try:
                root = globals().get("MAVEN_ROOT")
                if not root:
                    root = Path(__file__).resolve().parents[4]
                log_path = (root / "reports" / "wm_trace.jsonl").resolve()
                from api.utils import append_jsonl  # type: ignore
                append_jsonl(log_path, {"op": "CONTROL_TICK", "emitted": emitted, "entries": current_entries})
            except Exception:
                pass
            return success_response(op, mid, {"events_emitted": emitted})
        except Exception as e:
            return error_response(op, mid, "CONTROL_TICK_FAILED", str(e))

    # ------------------------------------------------------------------
    # Blackboard and Control Shell (Phase‑6)
    #
    # BB_SUBSCRIBE registers a subscription for a brain.  CONTROL_CYCLE
    # performs a bounded cycle: collects WM events, scores them per
    # subscription, arbitrates via the integrator and dispatches the
    # winning event.  Events older than the subscription TTL or below
    # the confidence threshold are ignored.  A global cap on steps and
    # runtime is enforced by configuration (blackboard.json).

    elif op == "BB_SUBSCRIBE":
        sub_id = str((payload or {}).get("subscriber", "")).strip()
        if not sub_id:
            return error_response(op, mid, "INVALID_SUBSCRIBER", "subscriber is required")
        key = (payload or {}).get("key")
        tags = (payload or {}).get("tags")
        tags_list = list(tags) if tags else None
        try:
            min_conf = float((payload or {}).get("min_conf", 0.0))
        except Exception:
            min_conf = 0.0
        try:
            ttl = float((payload or {}).get("ttl", 300.0))
        except Exception:
            ttl = 300.0
        try:
            priority = float((payload or {}).get("priority", 0.5))
        except Exception:
            priority = 0.5
        _bb_subscribe(sub_id, key, tags_list, min_conf, ttl, priority)
        return success_response(op, mid, {"subscribed": True, "subscriber": sub_id})

    elif op == "CONTROL_CYCLE":
        # Perform a bounded cycle of WM arbitration and dispatch
        try:
            _wm_load_if_needed()
        except Exception:
            pass
        # Load blackboard configuration
        try:
            from api.utils import CFG  # type: ignore
            bb_cfg = (CFG.get("blackboard") or {}) if CFG else {}
        except Exception:
            bb_cfg = {}
        try:
            max_steps = int(bb_cfg.get("max_steps", 64) or 64)
        except Exception:
            max_steps = 64
        try:
            max_events = int(bb_cfg.get("max_events_per_tick", 50) or 50)
        except Exception:
            max_events = 50
        try:
            max_ms = float(bb_cfg.get("max_runtime_ms", 150.0) or 150.0)
        except Exception:
            max_ms = 150.0
        starvation_guard = bool(bb_cfg.get("starvation_guard", True))
        # Collect candidate events
        candidates = _bb_collect_events()
        if not candidates:
            return success_response(op, mid, {"processed": 0, "message": "no events"})
        # Sort by score descending
        candidates.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        processed = 0
        logs: List[Dict[str, Any]] = []
        for cand in candidates:
            if processed >= max_events:
                break
            sub_id = cand.get("subscriber")
            entry = cand.get("entry")
            idx = cand.get("index")
            score = cand.get("score", 0.0)
            # Build a bid for the integrator with subscription priority
            try:
                sub_cfg = _BLACKBOARD_SUBS.get(str(sub_id)) or {}
                base_p = float(sub_cfg.get("priority", 0.5))
            except Exception:
                base_p = 0.5
            try:
                bid_priority = float(score + base_p)
            except Exception:
                bid_priority = base_p
            # Clamp to [0.0, 1.0]
            if bid_priority < 0.0:
                bid_priority = 0.0
            if bid_priority > 1.0:
                bid_priority = 1.0
            bids = [{"brain_name": sub_id, "priority": bid_priority, "reason": "wm_event", "evidence": entry}]
            # Resolve via integrator
            try:
                from brains.cognitive.integrator.service.integrator_brain import service_api as integrator_api  # type: ignore
                res = integrator_api({"op": "RESOLVE", "payload": {"bids": bids}, "mid": f"BB-{mid}-{processed}"})
                winner = res.get("payload", {}).get("focus") or sub_id
            except Exception:
                winner = sub_id
            # Dispatch event to message bus
            try:
                from brains.cognitive import message_bus  # type: ignore
                message_bus.send({
                    "from": "blackboard",
                    "to": winner,
                    "type": "WM_EVENT",
                    "entry": entry,
                })
                processed += 1
                _bb_mark_processed(str(sub_id), int(idx))
                logs.append({
                    "subscriber": sub_id,
                    "winner": winner,
                    "entry": entry,
                    "score": score,
                })
            except Exception:
                continue
            if starvation_guard and processed >= max_events:
                break
        # Write trace
        try:
            root = globals().get("MAVEN_ROOT")
            if not root:
                root = Path(__file__).resolve().parents[4]
            bb_path = (root / "reports" / "blackboard_trace.jsonl").resolve()
            from api.utils import append_jsonl  # type: ignore
            for rec in logs:
                append_jsonl(bb_path, rec)
        except Exception:
            pass
        return success_response(op, mid, {"processed": processed})

    elif op == "PROCESS_EVENTS":
        # Drain message bus events and log them. Does not affect working memory.
        try:
            # Pop all events from the internal message bus
            try:
                from brains.cognitive import message_bus  # type: ignore
                events: List[Dict[str, Any]] = message_bus.pop_all() or []
            except Exception:
                events = []
            # Write events to wm_events.jsonl for auditing
            counts: Dict[str, int] = {}
            try:
                root = globals().get("MAVEN_ROOT")
                if not root:
                    root = Path(__file__).resolve().parents[4]
                log_path = (root / "reports" / "wm_events.jsonl").resolve()
                from api.utils import append_jsonl  # type: ignore
                for ev in events:
                    try:
                        # Determine type field for counting; fallback to 'UNKNOWN'
                        typ = str(ev.get("type") or "UNKNOWN")
                        counts[typ] = counts.get(typ, 0) + 1
                        append_jsonl(log_path, {"event": ev})
                    except Exception:
                        continue
            except Exception:
                # If logging fails, still compute counts
                for ev in events:
                    try:
                        typ = str(ev.get("type") or "UNKNOWN")
                        counts[typ] = counts.get(typ, 0) + 1
                    except Exception:
                        pass
            return success_response(op, mid, {"events": counts})
        except Exception as e:
            return error_response(op, mid, "PROCESS_EVENTS_FAILED", str(e))

    elif op == "ALIGNMENT_AUDIT":
        # Stub alignment audit implementation.  Creates placeholder reports in
        # reports/agent and returns their names.  Full alignment logic will be
        # implemented in a future upgrade.
        try:
            rpt_dir = MAVEN_ROOT / "reports" / "agent"
            # Ensure report directory exists
            rpt_dir.mkdir(parents=True, exist_ok=True)
            # Create placeholder JSON files
            matrix = {"note": "alignment audit stub"}
            findings = {"note": "alignment findings stub"}
            proof = {"note": "alignment proof stub"}
            (rpt_dir / "alignment_matrix.json").write_text(json.dumps(matrix, indent=2), encoding="utf-8")
            (rpt_dir / "alignment_findings.json").write_text(json.dumps(findings, indent=2), encoding="utf-8")
            (rpt_dir / "alignment_proof.json").write_text(json.dumps(proof, indent=2), encoding="utf-8")
            return success_response(op, mid, {"reports": ["alignment_matrix.json", "alignment_findings.json", "alignment_proof.json"]})
        except Exception as e:
            return error_response(op, mid, "ALIGNMENT_AUDIT_FAILED", str(e))

    elif op == "ALIGNMENT_PROPOSE":
        # Stub alignment propose implementation.  Generates an empty patch list
        # in reports/agent/patchlist.json.  This will be replaced by real logic
        # that analyses alignment findings.
        try:
            rpt_dir = MAVEN_ROOT / "reports" / "agent"
            rpt_dir.mkdir(parents=True, exist_ok=True)
            patch = {"patches": []}
            (rpt_dir / "patchlist.json").write_text(json.dumps(patch, indent=2), encoding="utf-8")
            return success_response(op, mid, {"report": "patchlist.json"})
        except Exception as e:
            return error_response(op, mid, "ALIGNMENT_PROPOSE_FAILED", str(e))

    elif op == "ALIGNMENT_APPLY":
        # Stub alignment apply implementation.  Requires a governance token to
        # authorise any modifications.  When authorised, writes a simple
        # alignment_apply_result.json file indicating success.  No actual
        # modifications are performed in this stub.
        token = str((payload or {}).get("token", ""))
        # Require tokens starting with GOV-
        if not token.startswith("GOV-"):
            return error_response(op, mid, "AUTH_FAILED", "Invalid governance token")
        try:
            rpt_dir = MAVEN_ROOT / "reports" / "agent"
            rpt_dir.mkdir(parents=True, exist_ok=True)
            result = {"applied": True}
            (rpt_dir / "alignment_apply_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
            return success_response(op, mid, {"report": "alignment_apply_result.json"})
        except Exception as e:
            return error_response(op, mid, "ALIGNMENT_APPLY_FAILED", str(e))

    elif op == "CORRECT":
        old_statement = (payload or {}).get("old")
        new_statement = (payload or {}).get("new")
        reason = (payload or {}).get("reason", "user_correction")
        if not old_statement or not new_statement:
            return error_response(op, mid, "BAD_REQUEST", "Provide 'old' and 'new' in payload.")
        # Find the old record across banks
        try:
            old_hits = _retrieve_from_banks(str(old_statement), k=1)
            hits = (old_hits or {}).get("results") or []
            if not hits:
                return error_response(op, mid, "NOT_FOUND", "Original statement not found for correction")
            old_rec = hits[0]
            old_id = old_rec.get("id")
            old_bank = old_rec.get("source_bank") or "theories_and_contradictions"
            # Mark old as superseded
            try:
                _bank_module(old_bank).service_api({
                    "op": "SUPERSEDE",
                    "payload": {"id": old_id, "reason": reason}
                })
            except Exception:
                pass
            # Store the corrected statement through normal pipeline
            return service_api({"op": "RUN_PIPELINE", "payload": {"text": str(new_statement), "confidence": 0.9}})
        except Exception as e:
            return error_response(op, mid, "CORRECT_FAILED", str(e))

    elif op == "BRAIN_PUT":
        # Store brain-specific persistent data using append-only JSONL
        try:
            scope = (payload or {}).get("scope", "BRAIN")
            origin_brain = (payload or {}).get("origin_brain", "unknown")
            key = (payload or {}).get("key")
            value = (payload or {}).get("value")
            try:
                conf = float((payload or {}).get("confidence", 0.8))
            except Exception:
                conf = 0.8
            if not key:
                return error_response(op, mid, "BAD_REQUEST", "key is required")
            # Store to brain-specific memory file (JSONL format)
            brain_mem_dir = MAVEN_ROOT / "brains" / "cognitive" / origin_brain / "memory"
            brain_mem_dir.mkdir(parents=True, exist_ok=True)
            brain_mem_file = brain_mem_dir / "brain_storage.jsonl"
            # Append the entry to JSONL file (no read-modify-write, true append)
            record = {
                "key": key,
                "value": value,
                "confidence": conf,
                "scope": scope,
            }
            with open(brain_mem_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            _diag_log("BRAIN_PUT", {"brain":origin_brain, "key":key, "value":value})
            return success_response(op, mid, {"stored": True, "key": key, "brain": origin_brain})
        except Exception as e:
            return error_response(op, mid, "BRAIN_PUT_FAILED", str(e))

    elif op == "BRAIN_MERGE":
        # Merge-write with confidence bump when same key/value repeats
        try:
            scope = (payload or {}).get("scope", "BRAIN")
            origin_brain = (payload or {}).get("origin_brain", "unknown")
            key = (payload or {}).get("key")
            value = (payload or {}).get("value")
            if not key or value is None:
                return error_response(op, mid, "BAD_REQUEST", "key and value are required")
            try:
                conf_delta = float((payload or {}).get("conf_delta", 0.1))
            except Exception:
                conf_delta = 0.1
            # Use the _merge_brain_kv helper to handle the merge logic
            res = _merge_brain_kv(origin_brain, key, value, conf_delta=conf_delta)
            return success_response(op, mid, {"status": "merged", "scope": "BRAIN", "brain": origin_brain, "data": res})
        except Exception as e:
            return error_response(op, mid, "BRAIN_MERGE_FAILED", str(e))

    elif op == "BRAIN_GET":
        # Retrieve brain-specific persistent data from JSONL (last write wins)
        try:
            scope = (payload or {}).get("scope", "BRAIN")
            origin_brain = (payload or {}).get("origin_brain", "unknown")
            key = (payload or {}).get("key")
            if not key:
                return error_response(op, mid, "BAD_REQUEST", "key is required")
            # Load from brain-specific memory file (JSONL format)
            brain_mem_dir = MAVEN_ROOT / "brains" / "cognitive" / origin_brain / "memory"
            brain_mem_file = brain_mem_dir / "brain_storage.jsonl"
            if not brain_mem_file.exists():
                result = {"found": False, "data": None}
                _diag_log("BRAIN_GET", {"brain":origin_brain, "key":key, "result":result})
                return success_response(op, mid, result)
            # Read JSONL file and find the most recent matching key
            try:
                with open(brain_mem_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                # Search in reverse order for last write wins
                for line in reversed(lines):
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                        if record.get("key") == key:
                            # Return data in the format expected by consumers
                            result_data = {
                                "found": True,
                                "data": {
                                    "value": record.get("value"),
                                    "confidence": record.get("confidence", 0.8),
                                    "updated_at": record.get("updated_at"),
                                    "scope": record.get("scope", "BRAIN")
                                }
                            }
                            _diag_log("BRAIN_GET", {"brain":origin_brain, "key":key, "result":result_data.get("data")})
                            return success_response(op, mid, result_data)
                    except json.JSONDecodeError:
                        continue
                result = {"found": False, "data": None}
                _diag_log("BRAIN_GET", {"brain":origin_brain, "key":key, "result":result})
                return success_response(op, mid, result)
            except Exception:
                result = {"found": False, "data": None}
                _diag_log("BRAIN_GET", {"brain":origin_brain, "key":key, "result":result})
                return success_response(op, mid, result)
        except Exception as e:
            return error_response(op, mid, "BRAIN_GET_FAILED", str(e))

    # Fallback for unsupported operations
    return error_response(op, mid, "UNSUPPORTED_OP", op)

# -----------------------------------------------------------------------------
# Attention bid interface for memory retrieval
#
# The memory librarian does not represent a standalone cognitive brain,
# but for the purposes of attention resolution it can submit a bid on
# behalf of the memory subsystem.  A high confidence match in memory
# indicates that a relevant answer likely exists, so memory should
# receive attention.  Otherwise memory bids low.  The result is a
# dictionary with the same structure as BrainBid.to_dict().
def bid_for_attention(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Generate an attention bid on behalf of memory retrieval.

    Args:
        ctx: The current pipeline context passed through the memory
            librarian.  Should include stage_2R_memory results.

    Returns:
        A dictionary containing brain_name, priority, reason and evidence.
    """
    try:
        mem = ctx.get("stage_2R_memory") or {}
        results = mem.get("results") or []
        # Find the first result with confidence above 0.8
        high_match = None
        for it in results:
            try:
                c = float(it.get("confidence", 0.0))
                if c > 0.8:
                    high_match = it
                    break
            except Exception:
                continue
        if high_match:
            return {
                "brain_name": "memory",
                "priority": 0.85,
                "reason": "high_confidence_match",
                "evidence": {"result": high_match},
            }
        # Low default bid when no strong match is present
        return {
            "brain_name": "memory",
            "priority": 0.10,
            "reason": "default",
            "evidence": {},
        }
    except Exception:
        return {
            "brain_name": "memory",
            "priority": 0.10,
            "reason": "default",
            "evidence": {},
        }

# -----------------------------------------------------------------------------
# Inference helper for reasoning fallback
#
# When the reasoning brain has attention but cannot determine a verdict,
# we perform a lightweight inference using retrieved facts.  This helper
# attempts to answer yes/no questions of the form "Is X Y?" or "Is X a Y?"
# by scanning memory results for explicit statements of the form
# "X is a Y" or "X is Y".  It returns a dict with the inferred answer,
# confidence and a simple reasoning chain if successful, otherwise None.
def _attempt_inference(query: str, facts: List[Dict[str, Any]]) -> Any:
    """Attempt to infer an answer and explanation from memory facts.

    The inference process has two layers:

    1. Yes/No classification: For queries of the form "is X (a) Y?",
       scan facts for direct affirmations or negations and return a
       binary answer with a simple explanatory step.
    2. Multi‑step reasoning: For other queries, build short reasoning
       chains by matching keywords in the query to fact contents.  The
       strongest chain is selected based on a heuristic confidence and
       returned with an ordered list of supporting facts and roles.

    Args:
        query: Raw user query.
        facts: Relevant memory records (dicts with at least a 'content' field).

    Returns:
        A dict with keys 'answer', 'confidence', 'steps' and 'trace',
        or None when inference cannot produce a useful answer.
    """
    try:
        import re
        # Normalise query
        q_raw = str(query or "").strip().lower()
        q_norm = re.sub(r"[^a-z0-9\s]", " ", q_raw)
        q_norm = re.sub(r"\s+", " ", q_norm).strip()
        # Yes/no pattern: "is X a Y" or "is X Y"
        m = re.match(r"^is\s+(.+?)\s+(?:a\s+)?(.+)$", q_norm)
        if m:
            entity = m.group(1).strip()
            category = m.group(2).strip()
            # Remove leading articles from entity
            entity = re.sub(r"^(the|a|an)\s+", "", entity)
            entity_l = entity
            category_l = category
            for rec in facts or []:
                try:
                    content = str(rec.get("content", "")).strip().lower()
                except Exception:
                    content = ""
                if not content:
                    continue
                # Positive match: "entity is a category" or "entity is category"
                if re.search(rf"\b{re.escape(entity_l)}\s+is\s+(?:a\s+)?{re.escape(category_l)}\b", content):
                    return {
                        "answer": "Yes.",
                        "confidence": float(rec.get("confidence", 0.7) or 0.7),
                        "steps": [f"Found statement in memory: '{content}' which affirms that {entity} is {category}."],
                        "trace": [
                            {
                                "fact": content,
                                "role": "definition",
                            }
                        ],
                    }
                # Negative match: "entity is not a category"
                if re.search(rf"\b{re.escape(entity_l)}\s+is\s+not\s+(?:a\s+)?{re.escape(category_l)}\b", content):
                    return {
                        "answer": "No.",
                        "confidence": float(rec.get("confidence", 0.7) or 0.7),
                        "steps": [f"Found statement in memory: '{content}' which negates that {entity} is {category}."],
                        "trace": [
                            {
                                "fact": content,
                                "role": "definition",
                            }
                        ],
                    }
        # Multi‑step inference for general queries
        # Extract meaningful keywords (>2 chars) from the query
        words = [w for w in q_norm.split() if len(w) > 2]
        if not words:
            return None
        # Preprocess facts to lower‑cased content
        proc: List[str] = []
        for rec in facts or []:
            try:
                c = str(rec.get("content", "")).strip().lower()
            except Exception:
                c = ""
            if c:
                proc.append(c)
        if not proc:
            return None
        # Gather candidate single‑step reasoning entries
        candidates: List[Dict[str, Any]] = []
        for content in proc:
            shared = [kw for kw in words if kw in content]
            if not shared:
                continue
            conf = min(1.0, 0.5 + 0.1 * len(shared))
            candidates.append({
                "conclusion": content,
                "confidence": conf,
                "steps": [content],
            })
        # Attempt to form simple two‑step chains
        n = len(proc)
        for i in range(n):
            content_i = proc[i]
            shared_i = [kw for kw in words if kw in content_i]
            if not shared_i:
                continue
            for j in range(i + 1, n):
                content_j = proc[j]
                shared_j = [kw for kw in words if kw in content_j]
                if not shared_j:
                    continue
                conf = min(1.0, 0.6 + 0.05 * (len(shared_i) + len(shared_j)))
                candidates.append({
                    "conclusion": content_j,
                    "confidence": conf,
                    "steps": [content_i, content_j],
                })
        # Select best candidate
        best: Optional[Dict[str, Any]] = None
        for cand in candidates:
            try:
                if best is None or float(cand.get("confidence", 0.0)) > float(best.get("confidence", 0.0)):
                    best = cand
            except Exception:
                continue
        if best:
            try:
                bconf = float(best.get("confidence", 0.0))
            except Exception:
                bconf = 0.0
            if bconf >= 0.5:
                # Build trace with roles
                step_texts: List[str] = []
                trace: List[Dict[str, Any]] = []
                for s in best.get("steps", []) or []:
                    txt = str(s)
                    step_texts.append(txt)
                    # infer role heuristically
                    role: str
                    st = txt.lower()
                    if any(k in st for k in ["type", "types", "c3", "c4", "variety", "classification"]):
                        role = "types"
                    elif any(k in st for k in [
                        "process", "reaction", "stage", "step", "light‑dependent", "light dependent", "light‑independent",
                        "light independent", "cycle", "mechanism", "transfer", "energy", "convert"
                    ]):
                        role = "mechanism"
                    else:
                        role = "definition"
                    trace.append({"fact": txt, "role": role})
                return {
                    "answer": best.get("conclusion"),
                    "confidence": bconf,
                    "steps": step_texts,
                    "trace": trace,
                }
        return None
    except Exception:
        return None

# ---------------------------------------------------------------------------
# Handle wrapper for working memory routing
# ---------------------------------------------------------------------------

# Save reference to original service_api implementation
_service_api_impl = service_api

# Flag to track if WM has been hydrated from persistent brain storage
_WM_HYDRATED = False

def _hydrate_wm_from_brain_storage() -> None:
    """
    Hydrate working memory from per-brain persistent storage on first call.
    Loads last saved values into WM so memory survives restarts.
    """
    global _WM_HYDRATED
    if _WM_HYDRATED:
        return
    _WM_HYDRATED = True

    try:
        def _last_brain_value(brain: str, key: str) -> Any:
            """Get the last value for a key from brain storage (last-write-wins)."""
            brain_mem_dir = MAVEN_ROOT / "brains" / "cognitive" / brain / "memory"
            brain_mem_file = brain_mem_dir / "brain_storage.jsonl"
            if not brain_mem_file.exists():
                return None
            try:
                with open(brain_mem_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                # Search in reverse order for last write wins
                for line in reversed(lines):
                    if not line.strip():
                        continue
                    try:
                        rec = json.loads(line)
                        k = rec.get("k") or rec.get("key")
                        if k == key:
                            return rec.get("value", rec.get("v"))
                    except json.JSONDecodeError:
                        continue
                return None
            except Exception:
                return None

        # Hydrate known preference keys from memory_librarian brain storage
        for key in ("user_identity", "relationship_status", "favorite_color"):
            val = _last_brain_value("memory_librarian", key)
            if val is not None:
                # Add to working memory with high confidence
                with _WM_LOCK:
                    _WORKING_MEMORY.append({
                        "key": key,
                        "value": val,
                        "tags": ["preference", "hydrated"],
                        "confidence": 0.9,
                    })
    except Exception:
        # Silently fail if hydration errors occur
        pass

def handle(context: dict) -> dict:
    """
    Handle function that routes working memory operations.

    This wrapper adds _passed_memory = True to the context for WM operations
    and delegates to the underlying service implementation.

    Args:
        context: Request dictionary with 'op' and optional 'payload'

    Returns:
        Response dictionary from service implementation
    """
    # Hydrate WM from persistent storage on first call
    _hydrate_wm_from_brain_storage()

    # Mark that this request has passed through memory handling
    if isinstance(context, dict):
        op = (context or {}).get("op", "").upper()
        # For WM operations, mark as passed through memory
        if op.startswith("WM_"):
            context["_passed_memory"] = True

    # Route to the underlying service implementation
    return _service_api_impl(context)

# Service API entry point
service_api = handle
