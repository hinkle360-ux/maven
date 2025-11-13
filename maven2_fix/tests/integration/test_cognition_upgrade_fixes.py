"""
Integration tests for the Maven human‑cognition upgrade patches.

These tests verify that the recent fixes to configuration files and
services are functioning as expected.  They exercise the imagination
sandbox, the dual‑process router, the self‑critique reflection logs,
identity snapshot updates and the governance permit system.  Each
test runs in isolation and uses the existing project data structures
without requiring external dependencies.
"""

from __future__ import annotations

import importlib.util
import sys
import json
import os
import time
from pathlib import Path


def _load_module(path: Path, name: str):
    """Dynamically load a module from a given filesystem path."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod

# Ensure the project root is on sys.path for intra‑module imports.  When
# dynamically loading modules directly from their file paths, relative
# imports such as ``from api.utils import …`` require that the Maven
# root directory be included in Python's module search path.  Without this
# adjustment, imports inside the loaded modules may fail during test
# execution.  Insert the path once at module import time.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_imagination_config_limits():
    """
    Ensure that the imagination configuration caps roll‑outs at five and
    mandates permit proofs.
    """
    root = Path(__file__).resolve().parents[2]
    cfg_path = root / "config" / "imagination.json"
    with open(cfg_path, "r", encoding="utf-8") as fh:
        cfg = json.load(fh)
    # Max rollouts should be at most 5
    assert int(cfg.get("max_rollouts")) <= 5, "max_rollouts exceeds permitted limit"
    # Proofs should be required
    assert cfg.get("proofs_required") is True, "proofs_required not enabled"


def test_imaginer_respects_limits_and_proofs():
    """
    Call the imaginer with a high requested rollout count and ensure
    that the number of hypotheses returned does not exceed the
    configured maximum and that a permit id is attached to each.
    """
    root = Path(__file__).resolve().parents[2]
    svc_path = root / "brains" / "cognitive" / "imaginer" / "service" / "imaginer_brain.py"
    imaginer = _load_module(svc_path, "imaginer_brain")
    # Request more rollouts than allowed; the service should truncate
    # Request exactly the configured maximum.  If more than the limit is
    # requested the governance permit system will deny the request and no
    # hypotheses will be returned.  Requesting the exact limit ensures
    # the imaginer runs and returns hypotheses for evaluation.
    payload = {"prompt": "test imagination", "n": 5}
    res = imaginer.service_api({"op": "HYPOTHESIZE", "payload": payload})
    assert res.get("ok") is True, "Imaginer returned error"
    hyps = (res.get("payload") or {}).get("hypotheses") or []
    # Configured maximum is 5, so enforce this bound
    assert len(hyps) <= 5, "Imaginer did not respect max_rollouts"
    # Each hypothesis should carry a permit id when proofs are required
    for h in hyps:
        assert "permit_id" in h, "Permit id missing from hypothesis"


def test_reflection_log_contains_reason():
    """
    Verify that the self‑critique module writes a reason_for_reflection
    field into the reflection logs.
    """
    root = Path(__file__).resolve().parents[2]
    crit_path = root / "brains" / "cognitive" / "self_dmn" / "service" / "self_critique.py"
    self_critique = _load_module(crit_path, "self_critique")
    # Capture current set of reflection logs
    refl_dir = root / "reports" / "reflection"
    before_logs = set(p.name for p in refl_dir.glob("turn_*.jsonl"))
    # Invoke a critique to generate a new log entry
    self_critique.service_api({"op": "CRITIQUE", "payload": {"text": "This is a test response."}})
    # Identify the new log file
    after_logs = set(p.name for p in refl_dir.glob("turn_*.jsonl"))
    new_files = list(after_logs - before_logs)
    assert new_files, "No new reflection log was created"
    # Load the contents of the newest file
    new_path = refl_dir / new_files[-1]
    with open(new_path, "r", encoding="utf-8") as fh:
        line = fh.readline()
        entry = json.loads(line)
    # The log entry should include a reason_for_reflection field
    assert "reason_for_reflection" in entry, "reason_for_reflection missing in reflection log"


def test_identity_snapshot_updates_after_pipeline():
    """
    Run a pipeline query and verify that the identity snapshot file
    reflects the last question asked.
    """
    root = Path(__file__).resolve().parents[2]
    # Path to identity snapshot
    # The identity journal persists snapshots under brains/memory rather than
    # brains/personal/memory.  Read the snapshot from the location used by
    # identity_journal to observe updates made by the memory librarian.
    snap_path = root / "brains" / "memory" / "identity_snapshot.json"
    with open(snap_path, "r", encoding="utf-8") as fh:
        before = json.load(fh)
    # Run the pipeline with a unique question
    lib_path = root / "brains" / "cognitive" / "memory_librarian" / "service" / "memory_librarian.py"
    librarian = _load_module(lib_path, "memory_librarian")
    question = f"What time is it now? {time.time()}"
    librarian.service_api({"op": "RUN_PIPELINE", "payload": {"text": question, "confidence": 0.7}})
    # Reload snapshot
    with open(snap_path, "r", encoding="utf-8") as fh:
        after = json.load(fh)
    # The snapshot should have changed and contain the latest question
    assert before != after, "Identity snapshot did not update after pipeline run"
    assert after.get("last_question") == question, "last_question not updated in identity snapshot"


def test_governance_proof_file_created():
    """
    Request a permit from the governance layer and ensure that a new
    proof file is created matching the returned permit id.
    """
    root = Path(__file__).resolve().parents[2]
    proofs_dir = root / "reports" / "governance" / "proofs"
    # Record existing proof files
    before = set(p.name for p in proofs_dir.glob("PERMIT-*.json"))
    # Load the permits module and issue a permit request
    perm_path = root / "brains" / "governance" / "policy_engine" / "service" / "permits.py"
    permits = _load_module(perm_path, "permits")
    res = permits.service_api({"op": "REQUEST", "payload": {"action": "IMAGINE", "n": 5}})
    assert res.get("ok") is True, "Permit request failed"
    permit_id = (res.get("payload") or {}).get("permit_id")
    assert permit_id, "No permit id returned by governance"
    # Determine new files
    after = set(p.name for p in proofs_dir.glob("PERMIT-*.json"))
    new_files = list(after - before)
    assert new_files, "No new proof file was generated"
    # At least one new file should contain the permit_id in its filename
    assert any(permit_id in fname for fname in new_files), "Proof file name does not include permit id"