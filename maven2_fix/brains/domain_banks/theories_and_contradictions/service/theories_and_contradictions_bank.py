from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, List
import time, json, uuid
from api.utils import generate_mid, success_response, error_response
from api.memory import ensure_dirs, append_jsonl, count_lines

HERE = Path(__file__).resolve().parent
BANK_ROOT = HERE.parent

def _counts():
    t = ensure_dirs(BANK_ROOT)
    return {"stm": count_lines(t["stm"]), "mtm": count_lines(t["mtm"]), "ltm": count_lines(t["ltm"]), "cold": count_lines(t["cold"])}

def _store(kind: str, fact: Dict[str, Any]) -> Dict[str, Any]:
    t = ensure_dirs(BANK_ROOT)
    rec = {
        "id": str(uuid.uuid4()),
        "timestamp": time.time(),
        "type": kind,  # 'theory' | 'contradiction' | 'resolution'
        "content": fact.get("content", ""),
        "confidence": float(fact.get("confidence", 0.5)),
        "source_brain": fact.get("source_brain", "reasoning"),
        "linked_fact_id": fact.get("linked_fact_id"),
        "contradicts": fact.get("contradicts", []),
        "status": fact.get("status", "open"),
        "verification_level": fact.get("verification_level", "educated_guess" if kind == "theory" else ("unknown" if kind == "contradiction" else "validated")),
        "metadata": fact.get("metadata", {}),
    }
    append_jsonl(t["stm"], rec)
    return {"stored_id": rec["id"], "tier": "stm"}

def _retrieve(query: str, limit: int = 10) -> Dict[str, Any]:
    t = ensure_dirs(BANK_ROOT)
    results: List[dict] = []
    q = (query or "").lower()
    for path in [t["ltm"], t["mtm"], t["stm"]]:
        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    if len(results) >= limit: break
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    blob = json.dumps(rec).lower()
                    if q in blob:
                        results.append(rec)
        except FileNotFoundError:
            pass
    return {"results": results, "count": len(results)}

def _resolve_matches(content: str) -> Dict[str, Any]:
    t = ensure_dirs(BANK_ROOT)
    content_norm = (content or '').strip().lower()
    matched: List[str] = []
    try:
        with t["stm"].open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("type") == "theory" and isinstance(rec.get("content"), str):
                    if rec["content"].strip().lower() == content_norm:
                        matched.append(rec.get("id"))
    except FileNotFoundError:
        pass
    for rid in matched:
        append_jsonl(t["stm"], {
            "id": str(uuid.uuid4()),
            "timestamp": time.time(),
            "type": "resolution",
            "content": content,
            "status": "resolved",
            "verification_level": "validated",
            "linked_fact_id": rid,
            "source_brain": "librarian",
        })
    return {"resolved": len(matched), "matched_ids": matched}

def service_api(msg: Dict[str, Any]) -> Dict[str, Any]:
    op = (msg or {}).get("op", " ").upper()
    mid = msg.get("mid") or generate_mid()
    payload = msg.get("payload") or {}

    if op == "HEALTH": return success_response(op, mid, {"status": "operational", "fact_counts": _counts()})
    if op == "COUNT": return success_response(op, mid, _counts())
    if op == "STORE_THEORY": return success_response(op, mid, _store("theory", payload.get("fact") or {}))
    if op == "STORE_CONTRADICTION": return success_response(op, mid, _store("contradiction", payload.get("fact") or {}))
    if op == "RETRIEVE":
        q = str(payload.get("query", "")); limit = int(payload.get("limit", 10))
        return success_response(op, mid, _retrieve(q, limit))
    if op == "RESOLVE_MATCHES":
        return success_response(op, mid, _resolve_matches(str(payload.get("content",""))))

    # Provide primitive support for index rebuilding and cold compaction.  Unlike
    # other domain banks, theories_and_contradictions maintains a simple
    # append‑only log and does not use inverted indices for retrieval.  The
    # REBUILD_INDEX operation therefore returns a count of total records but
    # performs no modifications.  COMPACT_COLD is a no‑op because this bank
    # does not implement cold storage rotation yet.
    if op == "REBUILD_INDEX":
        # Count total records across all tiers as a placeholder for index size
        t = ensure_dirs(BANK_ROOT)
        total = count_lines(t["stm"]) + count_lines(t["mtm"]) + count_lines(t["ltm"]) + count_lines(t["cold"])
        return success_response(op, mid, {"rebuilt": True, "records_indexed": total})
    if op == "COMPACT_COLD":
        # No cold storage is used in this bank; return zero processed
        return success_response(op, mid, {"processed": 0})

    return error_response(op, mid, "UNSUPPORTED_OP", op)
