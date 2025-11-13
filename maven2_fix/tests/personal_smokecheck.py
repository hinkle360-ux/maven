from __future__ import annotations
import json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MAVEN_ROOT = HERE.parent
sys.path.insert(0, str(MAVEN_ROOT))

def main():
    # Load Memory Librarian
    lib = MAVEN_ROOT / "brains" / "cognitive" / "memory_librarian" / "service" / "memory_librarian.py"
    import importlib.util
    spec = importlib.util.spec_from_file_location("memory_librarian", lib)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)

    # Basic pipeline run
    text = "Show me Paris photos and the Eiffel Tower"
    res = mod.service_api({"op":"RUN_PIPELINE","payload":{"text": text, "confidence": 0.9}})
    ok = bool(res.get("ok"))
    ctx = (res.get("payload") or {}).get("context") or {}

    # Check Stage 11
    s11 = ctx.get("stage_11_personal_influence", {})
    has_stage11 = isinstance(s11, dict) and ("boost" in s11 or "subject" in s11)

    # Minimal report
    out = {
        "ok": ok,
        "has_stage11": has_stage11,
        "boost": s11.get("boost"),
        "subject": s11.get("subject"),
        "stages_seen": [k for k in ctx.keys() if k.startswith("stage_")],
    }
    print(json.dumps(out, indent=2))

if __name__ == "__main__":
    main()
