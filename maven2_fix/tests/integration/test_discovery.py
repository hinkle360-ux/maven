
import importlib.util
from pathlib import Path

def test_discover_banks():
    lib = Path(__file__).resolve().parents[2] / "brains" / "cognitive" / "memory_librarian" / "service" / "memory_librarian.py"
    spec = importlib.util.spec_from_file_location("memory_librarian", lib)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    # health should include discovered banks
    res = mod.service_api({"op":"HEALTH","payload":{}})
    assert res["ok"]
    banks = set(res["payload"]["discovered_banks"])
    assert {"factual","procedural","personal","creative","working_theories"}.issubset(banks)
