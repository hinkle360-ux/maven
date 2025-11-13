#!/usr/bin/env python3
"""
Offline test runner for Maven
This script exercises several operations provided by the Maven system in a local
context. It does not require network access or external services.  The goal is
to provide quick smoke tests for key features such as index rebuilding,
compaction, pipeline tracing, and health checks.  Results are printed to
stdout; this script is not intended to be exhaustive but should help
detect major regressions when iterating on the system.

To run this script, execute it from the Maven root:

    python3 maven/tools/offline_test_runner.py

"""
from __future__ import annotations
import sys
import importlib
from typing import List, Dict, Any
from pathlib import Path

# Adjust path so relative imports resolve
HERE = Path(__file__).resolve().parent
MAVEN_ROOT = HERE.parent
sys.path.insert(0, str(MAVEN_ROOT))

from api.utils import CFG

def main() -> None:
    # Import memory librarian service
    try:
        from brains.cognitive.memory_librarian.service import memory_librarian
    except Exception as e:
        print(f"Failed to import memory librarian: {e}")
        return

    results: Dict[str, Any] = {}
    # 1. Health check
    try:
        hc = memory_librarian.service_api({"op": "HEALTH_CHECK"})
        results["health_check"] = hc.get("payload")
    except Exception as e:
        results["health_check"] = {"error": str(e)}

    # 2. Index rebuild and compaction for each domain bank
    bank_names: List[str] = [
        "arts","science","history","economics","geography",
        "language_arts","law","math","philosophy","technology",
        "theories_and_contradictions"
    ]
    results["banks"] = {}
    for b in bank_names:
        bank_result: Dict[str, Any] = {}
        try:
            # Use memory librarian's internal loader to get the bank service module
            svc = memory_librarian._bank_module(b)
        except Exception:
            try:
                # Fallback to direct import
                mod_name = f"brains.domain_banks.{b}.service.{b}_bank"
                svc = importlib.import_module(mod_name)
            except Exception as e:
                bank_result["error"] = str(e)
                results["banks"][b] = bank_result
                continue
        # Rebuild index
        try:
            r = svc.service_api({"op": "REBUILD_INDEX"})
            bank_result["rebuild_index"] = r.get("payload") or r
        except Exception as e:
            bank_result["rebuild_index"] = {"error": str(e)}
        # Compact cold
        try:
            r2 = svc.service_api({"op": "COMPACT_COLD"})
            bank_result["compact_cold"] = r2.get("payload") or r2
        except Exception as e:
            bank_result["compact_cold"] = {"error": str(e)}
        results["banks"][b] = bank_result

    # 3. Run a simple pipeline with tracing disabled
    try:
        pipeline_payload = {
            "op": "RUN_PIPELINE",
            "payload": {"text": "Paris is the capital of France", "confidence": 0.9}
        }
        out = memory_librarian.service_api(pipeline_payload)
        results["pipeline_run"] = {
            "ok": out.get("ok"),
            "mid": out.get("mid"),
            "keys": list((out.get("payload") or {}).keys())
        }
    except Exception as e:
        results["pipeline_run"] = {"error": str(e)}

    # Print a condensed report
    import json
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    main()