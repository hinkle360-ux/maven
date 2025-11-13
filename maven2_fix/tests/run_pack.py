import os, sys, json, importlib.util
from pathlib import Path

# Always run from repo root: this script resides in tests/ but we use CWD.
REPO = Path(os.getcwd())
LIB = REPO / "brains" / "cognitive" / "memory_librarian" / "service" / "memory_librarian.py"

def _load_lib():
    spec = importlib.util.spec_from_file_location("lib", str(LIB))
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod

def main():
    if len(sys.argv) != 2:
        print("Usage: python tests\\run_pack.py tests\\packs\\<pack>\\<file>.jsonl", file=sys.stderr)
        sys.exit(2)
    pack_path = Path(sys.argv[1])
    if not pack_path.exists():
        print(f"Not found: {pack_path}", file=sys.stderr)
        sys.exit(1)
    lib = _load_lib()
    with open(pack_path, encoding="utf-8") as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    out = []
    for ln in lines:
        res = lib.service_api({"op":"RUN_PIPELINE","payload":{"text": ln}})
        out.append({"input": ln, "result": res})
    print(json.dumps(out, indent=2))

if __name__ == "__main__":
    main()
