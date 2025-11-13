# tests/repair_authorization_smoke.py
# Run from Maven root:
#   set PYTHONPATH=%CD%
#   python tests\repair_authorization_smoke.py

import importlib.util, os, json, sys

def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod

ROOT = os.getcwd()
POLICY = os.path.join(ROOT, "brains", "governance", "policy_engine", "service", "policy_engine.py")
REPAIR = os.path.join(ROOT, "brains", "governance", "repair_engine", "service", "repair_engine.py")

pe = _load(POLICY, "policy_engine")
re = _load(REPAIR, "repair_engine")

# 1) Try unauthorized repair (should fail)
unauth = re.service_api({"op":"REPAIR","payload":{"target":"reasoning"}})

# 2) Ask governance for auth
auth_res = pe.service_api({"op":"AUTHORIZE_REPAIR","payload":{"target":"reasoning"}})
auth = auth_res.get("payload",{}).get("auth",{})

# 3) Do authorized repair (should pass)
auth_fix = re.service_api({"op":"REPAIR","payload":{"target":"reasoning","auth":auth}})

print(json.dumps({
    "unauthorized_repair": unauth,
    "authorize_repair": auth_res,
    "authorized_repair": auth_fix
}, indent=2))
