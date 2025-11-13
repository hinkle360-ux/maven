# Pre‑Upgrade Checklist

Before applying any upgrade to Maven, complete the following
checklist to ensure the system is in a healthy state and backups are
available.  Upgrades should never be applied when the system is
degraded or when integrity checks are failing.

1. **Health Sweep**: Run the Phase 1 read‑only job from
   `RUNBOOK_agent.yaml`.  Confirm that all brains report `OK` and
   that there are no issues in the `reports/agent/phase1_health.json`
   output.

2. **Integrity Verification**: Execute `tools/integrity_verifier.py`
   without the `--update` flag, or run the `integrity_verify` step
   through the agent runbook.  Ensure that the status is `OK` and
   that the computed root hash matches the manifest.  If there are
   mismatches, investigate and resolve them before continuing.

3. **Backup**: Use the `BACKUP` operation via the Repair Engine or
   run the Phase 2 repair job with only the `backup` step enabled.
   Verify that a new backup archive appears under
   `reports/governance/repairs/backups/` and that its size is
   reasonable.  Keep the backup file handy in case a rollback is
   needed.

4. **Token Acquisition**: Request an upgrade authorisation token
   from the Policy Engine by sending an `AUTHORIZE_REPAIR` message
   with a scope appropriate for the upgrade (e.g., `"templates"
   or `"templates:reasoning"`).  Ensure that the returned token
   contains a `signature`, `scope`, and `ttl_ms`.  Do not share
   the token outside of the upgrade process.

5. **Prepare Upgrade Bundle**: Inspect the upgrade package and
   verify that it contains a `upgrade.json` manifest, a
   `MANIFEST.sha256` file, and a `payload` directory with the
   replacement files.  Compute the SHA256 of the manifest and
   compare it against the `MANIFEST.sha256` value.

6. **Dry Run**: Execute the `verify_signature` and `dry_run` steps
   from `RUNBOOK_upgrade.yaml` to confirm that the bundle can be
   applied cleanly.  Review the list of files that will be modified
   and ensure they match your expectations.

7. **Schedule Downtime (optional)**: If the upgrade will modify
   critical brains or banks, plan a maintenance window to minimise
   user impact.  Notify any users that the system may briefly
   operate in a degraded state during the upgrade.

8. **Proceed with Caution**: Only after all of the above checks
   have succeeded should you proceed to the `apply` step in
   `RUNBOOK_upgrade.yaml`.  Keep a close eye on the post‑apply
   reports and be prepared to rollback if necessary.

## Repository shape lock

Maven's repository layout is intentionally fixed to simplify upgrade
procedures and avoid unexpected side effects.  **Do not create new
top‑level directories** when preparing upgrades.  The only allowed
folders at the root of the project are:

```
api/
brains/
config/
docs/
reports/
runbooks/
templates/
tests/
tools/
ui/
```

Any upgrade package which introduces additional top‑level directories
should be rejected.  Note this list in your upgrade notes and verify
against the bundle contents during the dry run phase.