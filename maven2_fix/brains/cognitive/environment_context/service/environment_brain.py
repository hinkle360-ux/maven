"""
Environment Context Service
==========================

This module implements a simple environment context brain for Maven.
It provides a single operation to query Maven's current location.  In
reality, Maven is a software system that runs wherever the user's
device executes the code.  To address questions like "Where are you?"
or "Where are we?", this service returns a succinct description of
Maven's digital environment.  If more detailed telemetry becomes
available in the future (e.g. device name, operating system, network
context), that information could be surfaced here under appropriate
privacy constraints.

The ``service_api`` function accepts a message dictionary with an
``op`` field.  Recognised operations are:

``GET_LOCATION``: Returns a payload with a ``location`` field
    describing the digital environment where Maven operates.

For unsupported operations, the service responds with an error
payload.  All responses include the original ``op`` and a unique
``mid`` identifier to facilitate tracing through the pipeline.

This brain is independent of any domain bank and therefore does not
participate in memory retrieval or semantic caching.  It simply
answers environment queries directly.
"""

from __future__ import annotations

from typing import Dict, Any

import os
import random

# Helper to generate a unique message identifier.  Use random value
# to minimise collisions across threads.
def _gen_mid() -> str:
    return f"envctx-{random.randint(100000, 999999)}-{random.randint(1000, 9999)}"


def service_api(msg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Dispatch operations for the environment context brain.

    Parameters
    ----------
    msg : dict
        A message dictionary with keys ``op`` and (optionally)
        ``payload``.  ``op`` specifies the operation name (case
        insensitive).  Supported values are ``GET_LOCATION``.

    Returns
    -------
    dict
        A response containing ``ok``, ``op``, ``mid`` and ``payload`` or
        ``error`` fields.  On success, ``payload`` contains a
        ``location`` string.  On failure, ``error`` includes a code
        and message.
    """
    try:
        op = str((msg or {}).get("op", "")).upper()
    except Exception:
        op = ""
    mid = msg.get("mid") or _gen_mid()
    # Only one operation is supported: GET_LOCATION
    if op == "GET_LOCATION":
        # Return a fixed string describing the digital environment.
        # The phrasing emphasises that Maven lacks a physical body and
        # runs wherever the host system executes the code.
        location = "I exist in a digital environment on your device."
        return {
            "ok": True,
            "op": op,
            "mid": mid,
            "payload": {"location": location}
        }
    # Unsupported operation: return error response
    return {
        "ok": False,
        "op": op,
        "mid": mid,
        "error": {
            "code": "UNSUPPORTED_OP",
            "message": f"Unsupported operation: {op}"
        }
    }

# Ensure the environment brain exposes a `handle` entry point
try:
    handle = service_api  # type: ignore[assignment]
    service_api = handle  # type: ignore[assignment]
except Exception:
    pass
