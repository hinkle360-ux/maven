from __future__ import annotations
import hashlib, json, shutil, time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TEMPL = REPO / "brains" / "governance" / "repair_engine" / "service" / "templates" / "cognitive_full"
REPORTS = REPO / "reports" / "repair"
TEMPL.mkdir(parents=True, exist_ok=True); REPORTS.mkdir(parents=True, exist_ok=True)

BRAINS = [
    "sensorium","planner","language","pattern_recognition","reasoning",
    "affect_priority","personality","self_dmn","system_history",
    "memory_librarian","personal"
]

def svc_path(brain: str) -> Path:
    if brain == "personal":
        return REPO / "brains" / "personal" / "service" / "personal_brain.py"
    if brain == "memory_librarian":
        return REPO / "brains" / "cognitive" / "memory_librarian" / "service" / "memory_librarian.py"
    return REPO / "brains" / "cognitive" / brain / "service" / f"{brain}_brain.py"

def weights_path(brain: str) -> Path:
    if brain == "personal":
        return REPO / "brains" / "personal" / "service" / "weights.json"
    if brain == "memory_librarian":
        return REPO / "brains" / "cognitive" / "memory_librarian" / "service" / "weights.json"
    return REPO / "brains" / "cognitive" / brain / "service" / "weights.json"

def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

REQUIRED_OPS = {
    "sensorium": ["NORMALIZE"],
    "planner": ["PLAN"],
    "language": ["PARSE"],
    "pattern_recognition": ["ANALYZE"],
    "reasoning": ["EVALUATE_FACT","HEALTH"],
    "affect_priority": ["SCORE"],
    "personality": ["ADAPT_WEIGHTS_SUGGEST","LEARN_FROM_RUN"],
    "self_dmn": ["ANALYZE_INTERNAL"],
    "system_history": ["LOG_RUN_SUMMARY"],
    "memory_librarian": ["RUN_PIPELINE","HEALTH_CHECK"],
    "personal": ["SCORE_BOOST","WHY"]
}

def main():
    ts = int(time.time())
    version = f"baseline_{ts}"
    report = {"ts": ts, "version": version, "brains": [], "errors": []}
    for b in BRAINS:
        svc = svc_path(b)
        entry = {"brain": b, "service_file": str(svc), "captured": False}
        try:
            if not svc.exists():
                entry["error"] = "service_file_missing"
                report["errors"].append(entry)
                continue
            version_dir = TEMPL / b / version
            service_dir = version_dir / "service"
            mem_dir = version_dir / "memory"
            active_dir = TEMPL / b / "active"
            archive_dir = TEMPL / b / "archive"
            for d in (service_dir, mem_dir / "stm", mem_dir / "mtm", mem_dir / "ltm", mem_dir / "cold", active_dir, archive_dir):
                d.mkdir(parents=True, exist_ok=True)

            tgt = service_dir / svc.name
            shutil.copy2(svc, tgt)

            w = weights_path(b)
            if w.exists():
                shutil.copy2(w, service_dir / w.name)

            for t in ["stm","mtm","ltm","cold"]:
                keep = (mem_dir / t / ".keep")
                if not keep.exists():
                    keep.write_text("", encoding="utf-8")

            manifest = {
                "name": b,
                "version": version,
                "service": tgt.name,
                "required_ops": REQUIRED_OPS.get(b, []),
                "hash": sha256(tgt),
                "created_ts": ts
            }
            (version_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

            if any(active_dir.iterdir()):
                arch_slot = archive_dir / f"{int(time.time())}"
                arch_slot.mkdir(parents=True, exist_ok=True)
                for pth in active_dir.rglob("*"):
                    rel = pth.relative_to(active_dir)
                    dst = arch_slot / rel
                    if pth.is_dir():
                        dst.mkdir(parents=True, exist_ok=True)
                    else:
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(pth, dst)
                for pth in sorted(active_dir.rglob("*"), reverse=True):
                    if pth.is_file(): pth.unlink()
                for pth in sorted(active_dir.glob("*")):
                    if pth.is_dir(): shutil.rmtree(pth)

            for pth in version_dir.rglob("*"):
                rel = pth.relative_to(version_dir)
                dst = active_dir / rel
                if pth.is_dir():
                    dst.mkdir(parents=True, exist_ok=True)
                else:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(pth, dst)

            entry["captured"] = True
            entry["template_version"] = manifest["version"]
            entry["hash"] = manifest["hash"]
            report["brains"].append(entry)
        except Exception as e:
            entry["error"] = str(e)
            report["errors"].append(entry)

    rpt = REPORTS / f"template_capture_{ts}.json"
    rpt.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "report": str(rpt), "errors": report["errors"]}, indent=2))

if __name__ == "__main__":
    main()
