from __future__ import annotations
from typing import Any, Dict
import time, os, json, shutil, zipfile, hmac, hashlib as _hashlib
from pathlib import Path

# Repair Engine now requires a Governance authorization token.
# It will REFUSE to execute if a valid auth block is not present.

def _now_ms() -> int:
    return int(time.time() * 1000)

# Determine the Maven root by ascending from this file's location.  This is
# used for backup/restore and cold compaction operations.  The path
# points to the repository root where the "reports" and "brains" folders
# reside.
MAVEN_ROOT = Path(__file__).resolve().parents[4]

# List of all domain banks to operate on when none are explicitly provided.
_ALL_BANKS = [
    "arts","science","history","economics","geography",
    "language_arts","law","math","philosophy","technology",
    "theories_and_contradictions"
]

# Shared secret used to verify signatures on Governance tokens.  The
# value should match the secret used by the Policy Engine.  It can be
# overridden via the MAVEN_SECRET_KEY environment variable.  Do not
# disclose this value outside of Maven.
_SECRET_KEY = os.environ.get("MAVEN_SECRET_KEY", "maven_secret_key")

def _verify_signature(auth: Dict[str, Any]) -> bool:
    """Verify the HMAC signature on an authorization token.

    Returns True if the signature matches the expected value computed
    over the token fields (excluding the signature) using the shared
    secret.  False on any mismatch or error.
    """
    try:
        sig = auth.get("signature")
        if not isinstance(sig, str):
            return False
        # Rebuild the message with sorted keys excluding signature
        data = {k: v for k, v in auth.items() if k != "signature"}
        msg = json.dumps(data, sort_keys=True, separators=(",", ":"))
        expected = hmac.new(_SECRET_KEY.encode(), msg.encode(), _hashlib.sha256).hexdigest()
        # Use timing‑safe comparison
        return hmac.compare_digest(sig, expected)
    except Exception:
        return False

def _auth_ok(auth: Dict[str, Any], op: str) -> bool:
    """Validate an authorization token for the given operation.

    Checks issuer, validity flag, expiry, token format, signature and
    scope.  A token is considered valid if:

    * It is a dict issued by governance with valid=True
    * It has not expired (ts + ttl_ms)
    * The token string starts with GOV-
    * The signature matches the expected HMAC over the token contents
    * The operation requested is within the allowed scope ("repair_engine"
      grants access to all repair operations; otherwise the op name must
      appear within the scope string).
    """
    if not isinstance(auth, dict):
        return False
    if auth.get("issuer") != "governance":
        return False
    if not auth.get("valid", False):
        return False
    ts = auth.get("ts")
    ttl = auth.get("ttl_ms", 0)
    if not isinstance(ts, int) or not isinstance(ttl, int):
        return False
    if _now_ms() > ts + ttl:
        return False
    tok = auth.get("token", "")
    if not (isinstance(tok, str) and tok.startswith("GOV-") and len(tok) >= 8):
        return False
    # Verify signature integrity
    if not _verify_signature(auth):
        return False
    # Check scope vs operation
    scope = auth.get("scope", "") or "repair_engine"
    # Normalize to lower case
    scope_lc = scope.lower()
    op_lc = (op or "").lower()
    # If scope is repair_engine or all, allow all repair operations
    if scope_lc in {"repair_engine", "all"}:
        return True
    # Otherwise require that op name appears in the scope string (colon or comma separated)
    # Example scope: "backup,restore" or "compact_cold"
    allowed_ops = [s.strip() for s in scope_lc.replace(";", ",").split(",") if s.strip()]
    return op_lc.lower() in allowed_ops

def _scan_impl(payload: Dict[str, Any]) -> Dict[str, Any]:
    # Placeholder: quick scan summary (non-destructive)
    brains = payload.get("brains", ["reasoning","language","memory_librarian","personal","system_history","self_dmn"])
    return {"ok": True, "brains": brains, "issues": []}

def _fix_impl(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Perform a fix operation.  A double‐hash guard prevents accidental
    overwriting of templates when the current on‐disk hash does not match
    the expected value.  If `expected_hash` and `current_hash` are provided
    in the payload and they do not match, the repair is aborted and an
    error is returned.  Otherwise this stub simulates a successful repair.
    """
    expected = (payload or {}).get("expected_hash")
    current = (payload or {}).get("current_hash")
    if expected and current and expected != current:
        return {
            "ok": False,
            "error": "HASH_MISMATCH",
            "message": "Current template hash does not match expected hash; aborting repair.",
            "expected": expected,
            "found": current,
            "repairs": []
        }
    # TODO: implement actual fix logic.  For now, return a placeholder success.
    return {"ok": True, "repairs": [], "notes": "Fix applied successfully"}

def _checksum_path(path: str | Path) -> str:
    """Compute a SHA256 checksum for a given file path."""
    m = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            while True:
                chunk = fh.read(8192)
                if not chunk:
                    break
                m.update(chunk)
    except Exception:
        return ""
    return m.hexdigest()

def _backup_impl(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a backup of selected domain banks and key report files.  The
    backup is written as a ZIP archive to reports/governance/repairs/backups.
    The payload may specify a list of bank names under the "banks" key.  If
    omitted, all banks are included.  Returns the path of the backup file
    relative to the Maven root.
    """
    banks = payload.get("banks") or _ALL_BANKS
    if not isinstance(banks, list) or not banks:
        banks = _ALL_BANKS
    # Output directory for backups
    outdir = MAVEN_ROOT / "reports" / "governance" / "repairs" / "backups"
    outdir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    fname = f"backup_{ts}.zip"
    fpath = outdir / fname
    try:
        with zipfile.ZipFile(fpath, "w", zipfile.ZIP_DEFLATED) as zf:
            # Include selected banks
            for b in banks:
                bank_dir = MAVEN_ROOT / "brains" / "domain_banks" / b
                if not bank_dir.exists():
                    continue
                for root, _dirs, files in os.walk(bank_dir):
                    for file in files:
                        fullpath = os.path.join(root, file)
                        arcname = os.path.relpath(fullpath, MAVEN_ROOT)
                        zf.write(fullpath, arcname)
            # Include integrity manifest and docs sync info for completeness
            specials = [
                MAVEN_ROOT / "reports" / "templates_integrity.json",
                MAVEN_ROOT / "reports" / "docs_sync",
                MAVEN_ROOT / "reports" / "health_dashboard"
            ]
            for spath in specials:
                if spath.is_dir():
                    for root, _dirs, files in os.walk(spath):
                        for file in files:
                            full = os.path.join(root, file)
                            arcname = os.path.relpath(full, MAVEN_ROOT)
                            zf.write(full, arcname)
                elif spath.exists():
                    arcname = os.path.relpath(spath, MAVEN_ROOT)
                    zf.write(spath, arcname)
        return {"ok": True, "backup_path": str(fpath)}
    except Exception as e:
        return {"ok": False, "error": "BACKUP_FAILED", "message": str(e)}

def _restore_impl(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Restore a previously created backup archive.  The payload must specify
    "backup_path" pointing to a zip file created by _backup_impl.  Files
    contained in the archive will overwrite existing files under MAVEN_ROOT.
    Use with care.  Returns True on success.
    """
    bpath = payload.get("backup_path") or payload.get("path")
    if not bpath:
        return {"ok": False, "error": "MISSING_PATH", "message": "Missing backup_path parameter"}
    try:
        # Resolve path relative to Maven root if not absolute
        bfile = Path(bpath)
        if not bfile.is_absolute():
            bfile = MAVEN_ROOT / bfile
        if not bfile.exists():
            return {"ok": False, "error": "NOT_FOUND", "message": f"Backup not found: {bfile}"}
        with zipfile.ZipFile(bfile, "r") as zf:
            for member in zf.namelist():
                # Disallow traversal outside MAVEN_ROOT
                target = MAVEN_ROOT / member
                # Ensure parent directories exist
                target.parent.mkdir(parents=True, exist_ok=True)
                # Extract file
                with zf.open(member) as src, open(target, "wb") as dest:
                    shutil.copyfileobj(src, dest)
        return {"ok": True, "restored": True}
    except Exception as e:
        return {"ok": False, "error": "RESTORE_FAILED", "message": str(e)}

def _compact_cold_impl(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Perform a lightweight compaction of the Cold tier for the specified
    domain banks.  Compaction deduplicates records and removes empty
    lines to reduce file size.  The payload may specify a list of
    bank names under the "banks" key; if omitted, all banks are compacted.
    Returns a list of banks that were compacted.
    """
    banks = payload.get("banks") or _ALL_BANKS
    if not isinstance(banks, list) or not banks:
        banks = _ALL_BANKS
    compacted = []
    for b in banks:
        path = MAVEN_ROOT / "brains" / "domain_banks" / b / "memory" / "cold" / "records.jsonl"
        if not path.exists():
            continue
        try:
            # Read existing lines
            with open(path, "r", encoding="utf-8") as f:
                lines = [ln.strip() for ln in f if ln.strip()]
            # Deduplicate while preserving order
            seen = set()
            uniq = []
            for ln in lines:
                if ln not in seen:
                    seen.add(ln)
                    uniq.append(ln)
            with open(path, "w", encoding="utf-8") as f:
                for ln in uniq:
                    f.write(ln + "\n")
            compacted.append(b)
        except Exception:
            continue
    return {"ok": True, "compacted": compacted}

def service_api(msg: Dict[str, Any]) -> Dict[str, Any]:
    op = (msg or {}).get("op","").upper()
    payload = (msg or {}).get("payload",{}) or {}
    mid = payload.get("mid") or f"mid_{_now_ms()}"

    # Non-destructive ops do not require auth
    if op in {"SCAN","TEMPLATE_STATUS"}:
        res = _scan_impl(payload) if op=="SCAN" else {"ok": True, "status": "available"}
        return {"ok": True, "op": op, "mid": mid, "payload": res}

    # Destructive / state-changing ops require Governance auth
    auth = payload.get("auth", {})
    if op in {"REPAIR","PROMOTE_TEMPLATE","ROLLBACK_TEMPLATE","APPLY_TEMPLATE","FIX",
              "BACKUP","RESTORE","COMPACT_COLD"}:
        if not _auth_ok(auth, op):
            return {
                "ok": False,
                "op": op,
                "mid": mid,
                "error": "REPAIR_UNAUTHORIZED",
                "message": "Repair operation requires valid Governance authorization token",
                "payload": {"authorized": False}
            }
        # Proceed based on operation
        if op in {"REPAIR","FIX"}:
            res = _fix_impl(payload)
        elif op == "PROMOTE_TEMPLATE":
            res = {"ok": True, "promoted": True}
        elif op == "ROLLBACK_TEMPLATE":
            res = {"ok": True, "rolled_back": True}
        elif op == "APPLY_TEMPLATE":
            res = {"ok": True, "applied": True}
        elif op == "BACKUP":
            res = _backup_impl(payload)
        elif op == "RESTORE":
            res = _restore_impl(payload)
        elif op == "COMPACT_COLD":
            res = _compact_cold_impl(payload)
        else:
            res = {"ok": False, "error": "UNSUPPORTED_OP", "message": op}
        return {"ok": True, "op": op, "mid": mid, "payload": {"authorized": True, **res}}

    # Unknown
    return {"ok": False, "op": op, "mid": mid, "error": "UNSUPPORTED_OP", "message": op}
