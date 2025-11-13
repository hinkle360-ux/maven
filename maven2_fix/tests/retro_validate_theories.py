from __future__ import annotations
import importlib.util
from pathlib import Path

# Call theories_and_contradictions.RESOLVE_MATCHES for a given text (default: last user text)
TEXT = "Show me Paris photos and the Eiffel Tower"

def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); assert spec.loader is not None
    spec.loader.exec_module(mod); return mod

def main():
    root = Path.cwd()  # run from maven/
    svc = root / "brains" / "domain_banks" / "theories_and_contradictions" / "service" / "theories_and_contradictions_bank.py"
    bank = _load(svc, "tac_bank")
    res = bank.service_api({"op":"RESOLVE_MATCHES","payload":{"content": TEXT}})
    print(res)

if __name__ == "__main__":
    main()
