from __future__ import annotations
import json, time, uuid, math
from typing import Any, Dict, List
from pathlib import Path
import sys

# ===== Placement =====
HERE = Path(__file__).resolve().parent
BRAIN_ROOT = HERE.parent  # .../personal/
PROJECT_ROOT = BRAIN_ROOT
while PROJECT_ROOT.name not in ["personal", "maven"] and PROJECT_ROOT.parent != PROJECT_ROOT:
    PROJECT_ROOT = PROJECT_ROOT.parent
MAVEN_ROOT = PROJECT_ROOT.parent if PROJECT_ROOT.name == "personal" else PROJECT_ROOT
sys.path.append(str(MAVEN_ROOT))

# Shared utils
try:
    from api.utils import generate_mid, success_response, error_response
except Exception:
    def generate_mid() -> str: return f"MID-{int(time.time()*1000)}"
    def success_response(op, mid, payload): return {"ok": True, "op": op, "mid": mid, "payload": payload}
    def error_response(op, mid, code, message): return {"ok": False, "op": op, "mid": mid, "error": {"code": code, "message": message}}

# ===== Memory tiers (JSONL) =====
TIERS = {
    "stm": BRAIN_ROOT / "memory" / "stm" / "prefs.jsonl",
    "mtm": BRAIN_ROOT / "memory" / "mtm" / "prefs.jsonl",
    "ltm": BRAIN_ROOT / "memory" / "ltm" / "prefs.jsonl",
    "cold": BRAIN_ROOT / "memory" / "cold" / "archive.jsonl",
    "logs": BRAIN_ROOT / "memory" / "stm" / "logs.jsonl",
}
for p in TIERS.values():
    p.parent.mkdir(parents=True, exist_ok=True)

def _append_jsonl(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj) + "\n")

def _counts() -> Dict[str, int]:
    c = {}
    for k, p in TIERS.items():
        if p.exists():
            with p.open("r", encoding="utf-8") as f:
                c[k] = sum(1 for _ in f)
        else:
            c[k] = 0
    return c

# ===== Preference primitives =====
def _make_pref(subject: str, valence: float, intensity: float, source: str, note: str|None=None) -> dict:
    now = time.time()
    return {
        "id": str(uuid.uuid4()),
        "ts": now,
        "subject": subject.strip(),
        "valence": max(-1.0, min(1.0, float(valence))),
        "intensity": max(0.0, min(1.0, float(intensity))),
        "confidence": 0.6,
        "stability_half_life_days": 180,
        "origin": source or "self_report",
        "signals": [{"ts": now, "source": source, "weight": float(intensity)}],
        "hypothesis": note or "",
        "explanations": [],
        "last_updated": now,
        "privacy_tags": ["personal", "exportable:false"],
    }

def _key(s: str) -> str:
    return " ".join(s.lower().split())

def _load_all() -> List[dict]:
    out: List[dict] = []
    for path in [TIERS["ltm"], TIERS["mtm"], TIERS["stm"]]:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                try: out.append(json.loads(line))
                except Exception: continue
    return out

def _upsert(subject: str, delta_valence: float, intensity: float, source: str, note: str|None=None) -> dict:
    subj_key = _key(subject)
    allrecs = _load_all()
    latest_by_subject = {}
    for r in allrecs:
        latest_by_subject[_key(r.get("subject",""))] = r
    if subj_key in latest_by_subject:
        r = latest_by_subject[subj_key]
        days = (time.time() - r.get("last_updated", r.get("ts", 0))) / 86400.0
        decay = min(0.25, max(0.0, days / 365.0))
        new_valence = max(-1.0, min(1.0, r.get("valence", 0.0) * (1.0 - decay) + delta_valence * intensity))
        agree = (r.get("valence", 0.0) * new_valence) >= 0
        conf = r.get("confidence", 0.6)
        conf = max(0.0, min(1.0, conf + (0.05 if agree else -0.07)))
        r.update({
            "valence": new_valence,
            "intensity": max(0.0, min(1.0, (r.get("intensity", 0.5) + intensity) / 2.0)),
            "confidence": conf,
            "last_updated": time.time(),
        })
        r.setdefault("signals", []).append({"ts": time.time(), "source": source, "weight": float(intensity), "note": note or ""})
    else:
        r = _make_pref(subject, delta_valence, intensity, source, note)
    _append_jsonl(TIERS["stm"], r)
    return r

def _boost(subject: str) -> float:
    subj_key = _key(subject)
    latest = {}
    for r in _load_all():
        latest[_key(r.get("subject",""))] = r
    r = latest.get(subj_key)
    if not r:
        return 0.0
    age_days = (time.time() - r.get("last_updated", r.get("ts", 0))) / 86400.0
    freshness = max(0.6, 1.0 - min(0.5, age_days / 365.0))
    raw = r.get("valence", 0.0) * r.get("intensity", 0.5) * r.get("confidence", 0.6) * freshness
    return max(-0.25, min(0.25, raw))

def _top_likes(limit: int = 10) -> List[dict]:
    latest = {}
    for r in _load_all():
        latest[_key(r.get("subject",""))] = r
    scored = [( _boost(r.get("subject","")), r) for r in latest.values()]
    scored.sort(key=lambda t: t[0], reverse=True)
    return [dict(r, score_boost=round(b, 4)) for b, r in scored[:max(1, int(limit))]]

def _why(subject: str) -> dict:
    subj_key = _key(subject)
    latest = {}
    for r in _load_all():
        latest[_key(r.get("subject",""))] = r
    r = latest.get(subj_key)
    if not r:
        return {"subject": subject, "found": False, "signals": []}
    return {"subject": r["subject"], "found": True, "valence": r["valence"], "intensity": r["intensity"],
            "confidence": r["confidence"], "signals": r.get("signals", []), "hypothesis": r.get("hypothesis","")}

def _export(filter_tags: List[str] | None) -> List[dict]:
    out = []
    tags = set([t.strip() for t in (filter_tags or []) if t.strip()])
    for r in _load_all():
        priv = set(r.get("privacy_tags", []))
        if "exportable:false" in priv and not tags:
            continue
        if tags and not (tags & priv):
            continue
        out.append(r)
    return out

# ===== service_api =====
def service_api(msg: Dict[str, Any]) -> Dict[str, Any]:
    op = (msg or {}).get("op"," ").upper()
    mid = msg.get("mid") or generate_mid()
    payload = msg.get("payload") or {}
    try:
        if op == "HEALTH":
            return success_response(op, mid, {"status": "operational", "type": "personal_brain", "memory_health": _counts(), "ops": [
                "RECORD_LIKE","RECORD_DISLIKE","REINFORCE","SET_PRIVACY","TOP_LIKES","WHY","SCORE_BOOST","EXPORT"
            ]})
        if op == "RECORD_LIKE":
            r = _upsert(str(payload.get("subject","")).strip(), +1.0, float(payload.get("intensity", 0.6)), payload.get("source","self_report"), payload.get("note"))
            return success_response(op, mid, {"record": r, "boost": _boost(r["subject"])})

        if op == "RECORD_DISLIKE":
            r = _upsert(str(payload.get("subject","")).strip(), -1.0, float(payload.get("intensity", 0.6)), payload.get("source","self_report"), payload.get("note"))
            return success_response(op, mid, {"record": r, "boost": _boost(r["subject"])})

        if op == "REINFORCE":
            r = _upsert(str(payload.get("subject","")).strip(), float(payload.get("delta", 0.2)), float(payload.get("weight", 0.2)), payload.get("source","behavior"))
            return success_response(op, mid, {"record": r, "boost": _boost(r["subject"])})

        if op == "SET_PRIVACY":
            subj = str(payload.get("subject","")).strip()
            tags = [t.strip() for t in (payload.get("tags") or []) if t and isinstance(t, str)]
            _append_jsonl(TIERS["stm"], {"ts": time.time(), "subject": subj, "privacy_update": tags})
            return success_response(op, mid, {"subject": subj, "tags": tags})

        if op == "TOP_LIKES":
            limit = int(payload.get("limit", 10))
            return success_response(op, mid, {"items": _top_likes(limit)})

        if op == "WHY":
            return success_response(op, mid, _why(str(payload.get("subject",""))))

        if op == "SCORE_BOOST":
            return success_response(op, mid, {"subject": payload.get("subject"), "boost": _boost(str(payload.get("subject","")))})

        if op == "EXPORT":
            filter_tags = payload.get("filter_tags")
            return success_response(op, mid, {"items": _export(filter_tags)})
        return error_response(op, mid, "UNSUPPORTED_OP", f"Unknown operation: {op}")
    except Exception as e:
        return error_response(op, mid, "EXCEPTION", str(e))
