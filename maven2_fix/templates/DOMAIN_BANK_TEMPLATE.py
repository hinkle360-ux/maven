
from __future__ import annotations
import sys, json, time, uuid
from typing import Dict, Any, List
from pathlib import Path

HERE = Path(__file__).resolve().parent
MAVEN_ROOT = HERE.parent
sys.path.append(str(MAVEN_ROOT))

from api.utils import CFG, generate_mid, success_response, error_response, append_jsonl
import hashlib
import re
import json as _json

def _ensure_dirs(root: Path):
    for tier in (CFG["paths"]["stm"], CFG["paths"]["mtm"], CFG["paths"]["ltm"], CFG["paths"]["cold_storage"]):
        (root / tier).mkdir(parents=True, exist_ok=True)
        (root / tier / "records.jsonl").touch()


def _move_records(bank_root: Path, from_tier: str, to_tier: str, n: int) -> None:
    """
    Move the oldest n records from `from_tier` to `to_tier`.
    Records are moved in the order they appear in the source file.
    """
    if n <= 0:
        return
    from_path = bank_root / CFG["paths"][from_tier] / "records.jsonl"
    to_path = bank_root / CFG["paths"][to_tier] / "records.jsonl"
    # read all lines from source
    if not from_path.exists():
        return
    with open(from_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    # number of lines to move
    m = min(n, len(lines))
    move_lines = lines[:m]
    remain_lines = lines[m:]
    # append moved lines to destination
    with open(to_path, "a", encoding="utf-8") as f:
        for line in move_lines:
            f.write(line)
    # rewrite remaining lines to source
    with open(from_path, "w", encoding="utf-8") as f:
        for line in remain_lines:
            f.write(line)


def _rotate_if_needed(bank_root: Path) -> None:
    """
    Rotate records across STM→MTM→LTM→Cold tiers based on configured thresholds.

    The function first checks whether per-bank thresholds are defined in CFG["rotation_per_bank"] for
    this bank; if present, they override the global CFG["rotation"] thresholds.  Threshold values
    of zero or missing keys disable rotation for that tier.
    """
    # Derive bank name from its root directory (e.g. .../domain_banks/<bank_name>)
    bank_name = str(bank_root.name)
    global_thr = CFG.get("rotation", {})
    per_bank_thr = (CFG.get("rotation_per_bank", {}) or {}).get(bank_name, {})
    thresholds = {
        "stm_records": int(per_bank_thr.get("stm_records", global_thr.get("stm_records", 0) or 0)),
        "mtm_records": int(per_bank_thr.get("mtm_records", global_thr.get("mtm_records", 0) or 0)),
        "ltm_records": int(per_bank_thr.get("ltm_records", global_thr.get("ltm_records", 0) or 0))
    }
    # compute counts for STM, MTM, LTM
    stm_path = bank_root / CFG["paths"]["stm"] / "records.jsonl"
    mtm_path = bank_root / CFG["paths"]["mtm"] / "records.jsonl"
    ltm_path = bank_root / CFG["paths"]["ltm"] / "records.jsonl"
    stm_count = _count_lines(stm_path)
    mtm_count = _count_lines(mtm_path)
    ltm_count = _count_lines(ltm_path)
    # rotate from STM to MTM
    stm_limit = thresholds.get("stm_records", 0)
    if stm_limit and stm_count > stm_limit:
        _move_records(bank_root, "stm", "mtm", stm_count - stm_limit)
        mtm_count += (stm_count - stm_limit)
        stm_count = stm_limit
    # rotate from MTM to LTM
    mtm_limit = thresholds.get("mtm_records", 0)
    if mtm_limit and mtm_count > mtm_limit:
        _move_records(bank_root, "mtm", "ltm", mtm_count - mtm_limit)
        ltm_count += (mtm_count - mtm_limit)
        mtm_count = mtm_limit
    # rotate from LTM to cold storage
    ltm_limit = thresholds.get("ltm_records", 0)
    if ltm_limit and ltm_count > ltm_limit:
        _move_records(bank_root, "ltm", "cold_storage", ltm_count - ltm_limit)


def _iter_jsonl(path: Path):
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line: 
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue

def _count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with open(path, "r", encoding="utf-8") as f:
        return sum(1 for _ in f)

def _resolve_bank_root(bank_name: str) -> Path:
    return MAVEN_ROOT / "brains" / "domain_banks" / bank_name

def bank_service_factory(bank_name: str):
    BANK_NAME = bank_name

    def service_api(msg: Dict[str, Any]) -> Dict[str, Any]:
        op = (msg or {}).get("op"," ").upper()
        mid = msg.get("mid") or generate_mid()
        payload = msg.get("payload") or {}
        bank_root = _resolve_bank_root(BANK_NAME)
        bank_root.mkdir(parents=True, exist_ok=True)
        _ensure_dirs(bank_root)

        if op == "STORE":
            fact = payload.get("fact") or {}
            # Derive or compute a deterministic identifier for the fact.  When
            # an ID is provided, use it directly; otherwise compute a
            # content‑addressable hash based on the lower‑cased content.  This
            # enables deduplication across STM, MTM and LTM.  Shorten the
            # hash for readability.
            content_str = str(fact.get("content", "")).strip()
            try:
                provided_id = fact.get("id")
                if provided_id:
                    rec_id = str(provided_id)
                else:
                    # Normalize content for hashing
                    norm_content = content_str.lower().encode("utf-8")
                    rec_id = hashlib.sha256(norm_content).hexdigest()[:16]
            except Exception:
                rec_id = str(uuid.uuid4())
            # Helper to determine if a record ID already exists in any tier
            def _record_exists(bank_root: Path, rid: str) -> bool:
                try:
                    # Check index first for a quick existence test
                    service_dir = bank_root / "service"
                    idx_path = service_dir / "index.json"
                    if idx_path.exists():
                        try:
                            with open(idx_path, "r", encoding="utf-8") as fh:
                                idx = _json.load(fh) or {}
                            for ids in idx.values():
                                if rid in ids:
                                    return True
                        except Exception:
                            pass
                    # Fall back to scanning JSONL files across tiers
                    tiers = ("stm", "mtm", "ltm", "cold_storage")
                    for tier in tiers:
                        path = bank_root / CFG["paths"][tier] / "records.jsonl"
                        if not path.exists():
                            continue
                        try:
                            with open(path, "r", encoding="utf-8") as fh:
                                for line in fh:
                                    if not line.strip():
                                        continue
                                    try:
                                        rec = json.loads(line)
                                    except Exception:
                                        continue
                                    if rec.get("id") == rid:
                                        return True
                        except Exception:
                            continue
                except Exception:
                    pass
                return False
            # If a duplicate exists, skip storing and return the existing ID
            if _record_exists(bank_root, rec_id):
                return success_response(op, mid, {"stored_id": rec_id, "duplicate": True})
            # Build record with sensible defaults
            rec = {
                "id": rec_id,
                "timestamp": time.time(),
                "domain": BANK_NAME,
                "content": content_str,
                "confidence": float(fact.get("confidence", 0.0)),
                "verification_level": fact.get("verification_level", "educated_guess"),
                "source": fact.get("source", "unknown"),
                "validated_by": fact.get("validated_by", "unknown"),
                "metadata": fact.get("metadata", {"tier": "stm"})
            }
            append_jsonl(bank_root / CFG["paths"]["stm"] / "records.jsonl", rec)
            # After storing, rotate if needed
            try:
                _rotate_if_needed(bank_root)
            except Exception:
                pass
            # Update or create a simple inverted index for retrieval acceleration
            try:
                service_dir = bank_root / "service"
                idx_path = service_dir / "index.json"
                # tokenize content on non‑alphanumeric characters
                tokens = []
                for part in re.split(r"[^A-Za-z0-9]+", str(rec.get("content", "")).lower()):
                    if part:
                        tokens.append(part)
                idx = {}
                if idx_path.exists():
                    try:
                        with open(idx_path, "r", encoding="utf-8") as fh:
                            idx = _json.load(fh)
                    except Exception:
                        idx = {}
                for tok in tokens:
                    ids = idx.get(tok, [])
                    if rec["id"] not in ids:
                        ids.append(rec["id"])
                    idx[tok] = ids
                service_dir.mkdir(parents=True, exist_ok=True)
                with open(idx_path, "w", encoding="utf-8") as fh:
                    _json.dump(idx, fh)
            except Exception:
                pass
            return success_response(op, mid, {"stored_id": rec["id"], "duplicate": False})

        if op == "RETRIEVE":
            q = str(payload.get("query", "")).lower()
            results: List[Dict[str, Any]] = []
            # Tokenize query for index lookup and later matching.  We keep
            # individual tokens to allow flexible matching when the query
            # contains multiple words (e.g. "is the sky blue" vs "the sky is blue").
            tokens: List[str] = []
            if q:
                for part in re.split(r"[^A-Za-z0-9]+", q):
                    if part:
                        tokens.append(part)
            idx_candidates = None
            try:
                service_dir = bank_root / "service"
                idx_path = service_dir / "index.json"
                if idx_path.exists() and tokens:
                    with open(idx_path, "r", encoding="utf-8") as fh:
                        idx = _json.load(fh)
                    candidate_ids = set()
                    for tok in tokens:
                        candidate_ids.update(idx.get(tok, []))
                    if candidate_ids:
                        idx_candidates = candidate_ids
            except Exception:
                idx_candidates = None
            # Search records across tiers.  If we have index candidates and
            # multiple query tokens, use a more flexible matching strategy:
            # a record matches if it contains all query tokens in any order.
            for tier in ("stm", "mtm", "ltm"):
                p = bank_root / CFG["paths"][tier] / "records.jsonl"
                for item in _iter_jsonl(p):
                    cid = item.get("id")
                    content = str(item.get("content", "")).lower()
                    # When a query is provided, restrict results
                    if q:
                        if idx_candidates is not None:
                            # Only consider candidates.  Instead of strict substring
                            # matching on the entire query string (which can fail if
                            # the word order differs), require that all tokens appear
                            # somewhere in the content.
                            if cid in idx_candidates:
                                match = True
                                for tok in tokens:
                                    if tok not in content:
                                        match = False
                                        break
                                if match:
                                    results.append(item)
                        else:
                            # Without an index, fall back to substring match
                            if q in content:
                                results.append(item)
                    else:
                        # No query provided: return all items
                        results.append(item)
            return success_response(op, mid, {"results": results})

        # Rebuild the search index for this bank.  This scans all STM/MTM/LTM records
        # and creates a fresh inverted index mapping tokens to record IDs.  It does
        # not modify existing memory tiers.
        if op == "REBUILD_INDEX":
            rec_count = 0
            index: Dict[str, List[str]] = {}
            for tier in ("stm", "mtm", "ltm"):
                p = bank_root / CFG["paths"][tier] / "records.jsonl"
                for rec in _iter_jsonl(p):
                    rec_count += 1
                    rid = str(rec.get("id"))
                    content = str(rec.get("content", "")).lower()
                    tokens: List[str] = []
                    for part in re.split(r"[^A-Za-z0-9]+", content):
                        if part:
                            tokens.append(part)
                    for tok in tokens:
                        ids = index.get(tok, [])
                        if rid not in ids:
                            ids.append(rid)
                        index[tok] = ids
            # Write index to service/index.json
            service_dir = bank_root / "service"
            service_dir.mkdir(parents=True, exist_ok=True)
            idx_path = service_dir / "index.json"
            with open(idx_path, "w", encoding="utf-8") as fh:
                _json.dump(index, fh)
            return success_response(op, mid, {"rebuilt": True, "records_indexed": rec_count})

        # Compact the cold tier by rewriting it without blank lines.  This
        # operation preserves the order of records and does not drop data; it
        # simply removes empty lines, which can accumulate during rotations
        # or manual edits.  The response includes the number of non-empty
        # records processed.  If the cold file does not exist, zero is returned.
        if op == "COMPACT_COLD":
            try:
                cold_path = bank_root / CFG["paths"]["cold_storage"] / "records.jsonl"
                processed = 0
                if cold_path.exists():
                    with open(cold_path, "r", encoding="utf-8") as f:
                        lines = [ln.strip() for ln in f if ln.strip()]
                    processed = len(lines)
                    with open(cold_path, "w", encoding="utf-8") as f:
                        for ln in lines:
                            f.write(ln + "\n")
                return success_response(op, mid, {"processed": processed})
            except Exception as e:
                return error_response(op, mid, "COMPACT_FAILED", str(e))

        if op == "COUNT":
            return success_response(op, mid, {
                "stm": _count_lines(bank_root / CFG["paths"]["stm"] / "records.jsonl"),
                "mtm": _count_lines(bank_root / CFG["paths"]["mtm"] / "records.jsonl"),
                "ltm": _count_lines(bank_root / CFG["paths"]["ltm"] / "records.jsonl"),
            })

        return error_response(op, mid, "UNSUPPORTED_OP", op)

    return service_api
