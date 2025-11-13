#!/usr/bin/env python3
"""
compact_self_dmn_logs.py
========================

This utility trims large JSONL log files under the ``reports/self_dmn``
directory.  Self‑DMN logs (e.g. claims.jsonl) can grow indefinitely over
time, consuming disk space and slowing introspection.  By default, this
script keeps only the most recent 1000 records in each target file.  If
fewer than the maximum number of lines are present, the file is left
unchanged.

Usage examples::

    # Trim all logs to the last 1000 entries
    python compact_self_dmn_logs.py

    # Keep only the last 200 entries in each file
    python compact_self_dmn_logs.py --max-records 200

    # Trim a specific file
    python compact_self_dmn_logs.py --file reports/self_dmn/claims.jsonl

If ``--file`` is provided, only that file is processed.  Otherwise,
all ``.jsonl`` files in ``reports/self_dmn`` are trimmed.
"""

from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_MAX = 1000


def _trim_file(path: Path, max_records: int) -> None:
    """Truncate a JSONL file to the last ``max_records`` lines."""
    if not path.exists() or not path.is_file():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > max_records:
            lines = lines[-max_records:]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception:
        # Ignore any I/O errors
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Trim Self‑DMN JSONL logs to a fixed length")
    parser.add_argument("--file", type=str, default=None, help="Path to a specific JSONL file to trim")
    parser.add_argument("--max-records", type=int, default=DEFAULT_MAX, help="Number of trailing records to retain")
    args = parser.parse_args(argv)
    max_records = args.max_records if args.max_records > 0 else DEFAULT_MAX
    if args.file:
        path = Path(args.file)
        _trim_file(path, max_records)
    else:
        # Determine the self_dmn logs directory relative to this script
        proj_root = Path(__file__).resolve().parents[2]
        logs_dir = proj_root / "reports" / "self_dmn"
        if logs_dir.exists():
            for f in logs_dir.glob("*.jsonl"):
                _trim_file(f, max_records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())