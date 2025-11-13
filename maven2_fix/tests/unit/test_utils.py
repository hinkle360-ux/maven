
from api.utils import CFG, generate_mid

def test_config_has_domain_banks():
    assert "domain_banks" in CFG and isinstance(CFG["domain_banks"], dict)

def test_mid():
    assert generate_mid().startswith("MID-")
