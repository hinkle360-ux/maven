# Phase B & C Mini Plan

## Goals

- **Configuration centralization**:  Enhance the global configuration system to read JSON files from
  the `maven/config` directory at import time.  Any file that does not
  end with `_thresholds.json` overrides the default values in `api/utils.CFG`
  recursively.  This enables per‑deployment tuning without modifying code.
- **Local control shim**:  Provide an easy way to invoke Self‑DMN operations from the
  command line.  A new script, `run_self_dmn_control.py`, loads the Self‑DMN
  brain dynamically and exposes TICK, REFLECT, DISSENT_SCAN and
  ANALYZE_INTERNAL via CLI flags.  The script returns formatted JSON.
- **Packaging & persistence tooling**:  Introduce a utility for log
  compaction.  The script `tools/compact_self_dmn_logs.py` trims large
  JSONL logs in `reports/self_dmn` to the last N entries, helping manage
  disk usage over time.
- **Ship bundle**:  Deliver the Maven project as a clean zip archive with all
  updates applied.

## Acceptance Criteria

- Importing `api/utils` applies overrides from any JSON files in
  `maven/config` (except brain‑specific threshold files).  Default
  behaviour remains unchanged when no override files are present.
- Running `python maven/run_self_dmn_control.py --op <OP>` produces a valid
  JSON response.  The optional `--window` argument correctly influences
  REFLECT, DISSENT_SCAN and ANALYZE_INTERNAL operations.
- Executing `python maven/tools/compact_self_dmn_logs.py` trims log files
  under `reports/self_dmn` without corruption and honours the
  `--max-records` parameter.
- The pipeline continues to operate via `run_maven.py` and all existing
  unit and integration tests pass.
- A final archive contains the updated
  project for distribution.

## Files to Touch

- `maven/api/utils.py` – add override loader `_load_cfg_overrides` and a
  recursive update helper.
- `maven/run_self_dmn_control.py` – new CLI script for Self‑DMN control.
- `maven/tools/compact_self_dmn_logs.py` – new script for log trimming.
- `maven/phase_BC_mini_plan.md` and `maven/phase_BC_changelog.md` – documentation of
  the plan and changes.

## Rollback Plan

Should any part of this phase break the tests or pipeline, revert the
changes to `api/utils.py` and remove the added scripts (`run_self_dmn_control.py`
and `compact_self_dmn_logs.py`) along with this plan and changelog.  Ensure
that any override files in `maven/config` are removed to restore default
configuration behaviour.
