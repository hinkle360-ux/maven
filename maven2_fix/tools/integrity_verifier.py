#!/usr/bin/env python3
"""
integrity_verifier.py
=====================

This utility verifies the current Maven template integrity against the
recorded manifest in ``reports/templates_integrity.json``.  It
computes SHA256 hashes of the files listed in the manifest and
reports any mismatches.  Optionally, it can generate a new
manifest with updated hashes.

Usage::

    python tools/integrity_verifier.py [--update]

When ``--update`` is provided, the script will write a new
``templates_integrity.json`` file with the computed hashes and bump
the ``version`` and ``ts`` fields.  Without ``--update``, the
script only verifies the current state and prints a summary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

def sha256_file(path: Path) -> str:
    """Compute the SHA256 hash of a file."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(8192), b""):
                h.update(chunk)
    except FileNotFoundError:
        return ""
    return h.hexdigest()

def load_manifest(root: Path) -> dict:
    manifest_path = root / "reports" / "templates_integrity.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Integrity manifest not found at {manifest_path}")
    with open(manifest_path, "r", encoding="utf-8") as fh:
        return json.load(fh)

def compute_brain_hashes(root: Path, brains: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for brain, files in brains.items():
        result[brain] = {}
        for relpath in files:
            fpath = root / relpath
            result[brain][relpath] = sha256_file(fpath)
    return result

def compute_root_hash(brain_hashes: dict[str, dict[str, str]]) -> str:
    """Compute a root hash by hashing the concatenation of all file hashes sorted."""
    h = hashlib.sha256()
    for brain in sorted(brain_hashes.keys()):
        for relpath in sorted(brain_hashes[brain].keys()):
            h.update(brain_hashes[brain][relpath].encode())
    return h.hexdigest()

def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Maven template integrity")
    parser.add_argument("--update", action="store_true", help="Update the manifest with current hashes")
    args = parser.parse_args()
    # Determine Maven root relative to this script
    root = Path(__file__).resolve().parents[2]
    try:
        manifest = load_manifest(root)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 1
    brains = manifest.get("brains", {})
    current = compute_brain_hashes(root, brains)
    mismatches = []
    for brain, files in brains.items():
        for relpath, expected in files.items():
            actual = current[brain].get(relpath, "")
            if expected != actual:
                mismatches.append({"brain": brain, "file": relpath, "expected": expected, "found": actual})
    root_hash = compute_root_hash(current)
    status = "OK" if not mismatches and root_hash == manifest.get("__overall_root_hash") else "MISMATCH"
    print(json.dumps({"status": status, "mismatches": mismatches, "computed_root_hash": root_hash}, indent=2))
    if args.update:
        # Bump version and timestamp
        import time
        manifest_version = str(int(manifest.get("version", "0")) + 1)
        manifest["version"] = manifest_version
        manifest["__overall_root_hash"] = root_hash
        manifest["ts"] = int(time.time() * 1000)
        manifest["brains"] = current
        manifest_path = root / "reports" / "templates_integrity.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(manifest_path, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=2)
        print(f"Manifest updated at {manifest_path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())