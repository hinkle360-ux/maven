# ops_repair.py - run from the Maven root (folder that contains 'brains/')
# Usage examples:
#   python tests\ops_repair.py INIT_GOLDEN_FROM_BASELINE baseline_1761871530
#   python tests\ops_repair.py SCAN_TEMPLATES
import sys, json
from pathlib import Path
import importlib.util

REPO = Path(__file__).resolve().parents[1]  # .../maven
ENGINE_PATH = REPO / "brains" / "governance" / "repair_engine" / "service" / "repair_engine.py"

def load_engine():
    spec = importlib.util.spec_from_file_location("repair_engine_service", ENGINE_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod

def main():
    if not ENGINE_PATH.exists():
        print(json.dumps({"ok": False, "error": f"repair_engine.py not found at {ENGINE_PATH}"}))
        sys.exit(2)
    engine = load_engine()
    op = (sys.argv[1] if len(sys.argv) > 1 else "SCAN_TEMPLATES").upper()

    payload = {}
    if op == "INIT_GOLDEN_FROM_BASELINE":
        version = sys.argv[2] if len(sys.argv) > 2 else ""
        if not version:
            print("Usage: python tests\\ops_repair.py INIT_GOLDEN_FROM_BASELINE <version>")
            sys.exit(2)
        payload = {"version": version}
    elif op in ("LOAD_CANDIDATE","CANARY_TEST","PROMOTE_TEMPLATE","ROLLBACK_TEMPLATE","ROLLBACK_TO_GOLDEN","SCAN_TEMPLATES"):
        # additional args optional; keep simple for now
        if op == "LOAD_CANDIDATE":
            if len(sys.argv) < 4:
                print("Usage: python tests\\ops_repair.py LOAD_CANDIDATE <brain> <source_dir>")
                sys.exit(2)
            payload = {"brain": sys.argv[2], "source_dir": sys.argv[3]}
        elif op in ("CANARY_TEST","PROMOTE_TEMPLATE","ROLLBACK_TEMPLATE"):
            if len(sys.argv) < 3:
                print(f"Usage: python tests\\ops_repair.py {op} <brain>")
                sys.exit(2)
            payload = {"brain": sys.argv[2]}
        elif op == "ROLLBACK_TO_GOLDEN":
            if len(sys.argv) < 4:
                print("Usage: python tests\\ops_repair.py ROLLBACK_TO_GOLDEN <brain> <version>")
                sys.exit(2)
            payload = {"brain": sys.argv[2], "version": sys.argv[3]}
        else:
            payload = {}
    else:
        print(f"Unsupported op: {op}")
        sys.exit(2)

    res = engine.service_api({"op": op, "payload": payload})
    print(json.dumps(res.get("payload") or res, indent=2))

if __name__ == "__main__":
    main()
