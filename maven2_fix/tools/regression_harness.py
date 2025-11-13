#!/usr/bin/env python3
"""Regression harness for Maven QA memory and reasoning.

This script exercises the reasoning brain against the cross‑episode
question/answer (QA) memory.  It reads the stored QA pairs from
``reports/qa_memory.jsonl`` and for each entry invokes the reasoning
brain's ``EVALUATE_FACT`` operation with the original question.  The
current answer is compared to the stored answer.  Matches, mismatches
and errors are tallied and recorded.  A detailed summary is printed
to stdout and written to ``reports/regression/results.json`` for
inspection.

Usage (from the Maven project root):

    python3 maven/tools/regression_harness.py

An optional ``--limit`` argument can be provided to cap the number of
QA pairs tested, which is useful for quick checks on large memory files.
"""

from __future__ import annotations

import sys
import json
from pathlib import Path
from typing import Dict, Any, Optional


def run_regression(limit: Optional[int] = None) -> Dict[str, Any]:
    """Run regression checks over the QA memory entries.

    Args:
        limit: Optional maximum number of QA pairs to test.  If None,
            all entries are tested.

    Returns:
        A dictionary summarizing the results with keys ``total``,
        ``matches``, ``mismatches`` and ``details``.
    """
    # Determine the Maven root relative to this script.  This file lives
    # under maven/tools/.  The project root is one level up.
    root = Path(__file__).resolve().parents[1]
    # Ensure the root is on sys.path so that brain modules can be imported.
    sys.path.insert(0, str(root))
    # Import the reasoning brain service API.  Use a late import to
    # avoid import errors when this script is not run within Maven.
    try:
        from brains.cognitive.reasoning.service import reasoning_brain  # type: ignore
    except Exception as e:
        return {
            "total": 0,
            "matches": 0,
            "mismatches": 0,
            "details": [
                {"error": f"Failed to import reasoning brain: {e}"}
            ],
        }
    qa_file = root / "reports" / "qa_memory.jsonl"
    results: Dict[str, Any] = {
        "total": 0,
        "matches": 0,
        "mismatches": 0,
        "details": [],
    }
    if not qa_file.exists():
        # No QA memory means nothing to test
        return results
    # Read QA entries
    try:
        with qa_file.open("r", encoding="utf-8") as fh:
            lines = [line for line in fh if line.strip()]
    except Exception as e:
        return {
            "total": 0,
            "matches": 0,
            "mismatches": 0,
            "details": [
                {"error": f"Failed to read QA memory: {e}"}
            ],
        }
    if limit is not None:
        try:
            n = int(limit)
            lines = lines[: n]
        except Exception:
            pass
    for line in lines:
        try:
            rec = json.loads(line)
        except Exception:
            continue
        question = str(rec.get("question", "")).strip()
        expected = str(rec.get("answer", "")).strip()
        if not question:
            continue
        results["total"] += 1
        try:
            resp = reasoning_brain.service_api({
                "op": "EVALUATE_FACT",
                "payload": {"query": question}
            })
            payload = resp.get("payload") or {}
            # Reasoning brain may return an explicit 'answer' field when a
            # known answer is retrieved or computed.  Fall back to an empty
            # string if not present.
            ans = str(payload.get("answer", "")).strip()
            ans_norm = ans.lower()
            exp_norm = expected.lower()
            if ans_norm == exp_norm:
                results["matches"] += 1
            else:
                results["mismatches"] += 1
                results["details"].append({
                    "question": question,
                    "expected": expected,
                    "actual": ans,
                })
        except Exception as e:
            results["mismatches"] += 1
            results["details"].append({
                "question": question,
                "expected": expected,
                "actual": f"error: {e}",
            })
    # Write regression report
    try:
        report_dir = root / "reports" / "regression"
        report_dir.mkdir(parents=True, exist_ok=True)
        out_path = report_dir / "results.json"
        with out_path.open("w", encoding="utf-8") as fh:
            json.dump(results, fh, indent=2)
    except Exception:
        # Ignore write errors
        pass
    return results


def main() -> None:
    """Entry point for command‑line execution."""
    import argparse
    parser = argparse.ArgumentParser(description="Run regression tests against QA memory")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of QA pairs to test")
    args = parser.parse_args()
    res = run_regression(limit=args.limit)
    # Pretty print results
    import pprint
    pprint.pprint(res)


if __name__ == "__main__":
    main()