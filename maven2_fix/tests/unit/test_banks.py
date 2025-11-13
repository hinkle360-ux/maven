
import importlib.util, json
from pathlib import Path

def load_bank(bank):
    lib = Path(__file__).resolve().parents[2] / "brains" / "domain_banks" / bank / "service" / f"{bank}_bank.py"
    spec = importlib.util.spec_from_file_location(f"{bank}_bank", lib)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod

def test_store_retrieve_factual(tmp_path, monkeypatch):
    mod = load_bank("factual")
    # store
    res = mod.service_api({"op":"STORE","payload":{"fact":{"content":"Paris is capital of France","confidence":0.9,"verification_level":"established_fact"}}})
    assert res["ok"]
    # retrieve
    res = mod.service_api({"op":"RETRIEVE","payload":{"query":"Paris"}})
    assert res["ok"]
    assert len(res["payload"]["results"]) >= 1
