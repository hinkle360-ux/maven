"""
Factual domain bank
--------------------

This lightweight bank exists primarily for backwards compatibility with
earlier Maven test suites that expected a generic ``factual`` bank.  It
implements a minimal in‑memory store for arbitrary facts and exposes a
simple ``service_api`` compatible with the other domain banks.

The implementation intentionally avoids any external dependencies and
persists data only for the lifetime of the process.  When the process
restarts, the stored facts are cleared.  Facts are stored verbatim and
are not validated; callers are responsible for passing properly
structured fact dictionaries.

Supported operations
~~~~~~~~~~~~~~~~~~~~

* ``STORE`` – Stores a fact in memory.  The ``payload`` should contain
  a ``fact`` dictionary with at minimum a ``content`` string.

* ``RETRIEVE`` – Retrieves facts matching a case‑insensitive query.
  Returns up to ``limit`` matching facts (default: 5).

Any other operation returns ``ok=False`` with an ``UNSUPPORTED_OP`` error.

Note that this bank does **not** perform any duplicate detection,
contradiction analysis, or verification of facts.  It simply caches
and returns the facts supplied by callers.
"""

from __future__ import annotations

from typing import Dict, Any, List
from threading import Lock

# In‑memory store for facts.  Each fact is expected to be a dictionary
# containing at least a ``content`` key.  Additional metadata is
# preserved as-is.
_STORE: List[Dict[str, Any]] = []
_LOCK = Lock()


def service_api(msg: Dict[str, Any]) -> Dict[str, Any]:
    """Entry point for the factual bank.

    Parameters
    ----------
    msg : dict
        A dictionary with keys ``op`` and ``payload``.  The ``op``
        determines the operation to execute.  The ``payload`` carries
        operation‑specific arguments.

    Returns
    -------
    dict
        A response dictionary with an ``ok`` boolean and either a
        ``payload`` on success or an ``error`` on failure.
    """
    op = (msg or {}).get("op", "").upper()
    payload = msg.get("payload") or {}

    # STORE operation: append the provided fact to the in‑memory list.
    if op == "STORE":
        fact = payload.get("fact") or {}
        # Ensure the fact contains content; otherwise treat as no‑op
        if not isinstance(fact, dict) or not fact.get("content"):
            return {"ok": False, "error": {"code": "INVALID_FACT", "message": "Fact must contain content"}}
        with _LOCK:
            _STORE.append(fact)
        # Mirror the behaviour of other banks by wrapping the stored
        # fact in a result payload
        return {"ok": True, "payload": {"result": fact}}

    # RETRIEVE operation: search for facts whose ``content`` contains
    # the query substring (case‑insensitive).  Return up to ``limit`` results.
    if op == "RETRIEVE":
        query = str(payload.get("query", "")).lower()
        try:
            limit = int(payload.get("limit", 5))
        except Exception:
            limit = 5
        results: List[Dict[str, Any]] = []
        with _LOCK:
            for item in _STORE:
                try:
                    content = str(item.get("content", "")).lower()
                except Exception:
                    content = ""
                if query in content:
                    results.append(item)
                    if len(results) >= limit:
                        break
        return {"ok": True, "payload": {"results": results}}

    # Unsupported operation
    return {
        "ok": False,
        "op": op,
        "error": {"code": "UNSUPPORTED_OP", "message": op},
    }
