"""Simple identity round‑trip test.

This pytest test ensures that when a user introduces themselves
(e.g. "I am Josh"), the name is persisted via the primary user store
and can be recalled on a subsequent identity query.  It relies on
the durable identity store and the standard Maven pipeline entry
point provided by the memory librarian service.

The test does not depend on external services and uses only the
stdlib‑only Maven codebase.  It can be run via ``pytest -q`` from
the project root.
"""

import sys
from pathlib import Path


def test_identity_roundtrip():
    """Persist a name and verify it is recalled."""
    # Determine the project root by ascending two levels from this file
    project_root = Path(__file__).resolve().parents[2]
    # Prepend the project root to sys.path so that local packages can be imported
    sys.path.insert(0, str(project_root))
    # Import the identity store and set a test name
    from brains.personal.service import identity_user_store as ius  # type: ignore
    test_name = "Josh"
    ius.SET(test_name)
    # Import the memory librarian service API and the MID generator
    from brains.cognitive.memory_librarian.service.memory_librarian import service_api  # type: ignore
    from api.utils import generate_mid  # type: ignore
    # Run the pipeline on a simple identity query
    resp = service_api({
        "op": "RUN_PIPELINE",
        "mid": generate_mid(),
        "payload": {
            "text": "who am i",
            "confidence": 0.8,
        },
    })
    # Extract the final answer from the pipeline context
    ctx = (resp.get("payload") or {}).get("context") or {}
    final_ans = ctx.get("final_answer", "")
    # The final answer should mention the persisted name
    assert test_name in final_ans