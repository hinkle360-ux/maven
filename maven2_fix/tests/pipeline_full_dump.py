\
from __future__ import annotations
import json, importlib.util
from pathlib import Path

# Assume this file is run from the maven folder
LIB = Path("brains/cognitive/memory_librarian/service/memory_librarian.py").resolve()
spec = importlib.util.spec_from_file_location("lib", LIB)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

TEXT = "Show me Paris photos and the Eiffel Tower"
res = mod.service_api({"op":"RUN_PIPELINE","payload":{"text": TEXT, "confidence": 0.85}})
ctx = (res.get("payload") or {}).get("context") or {}
print(json.dumps(ctx, indent=2))
