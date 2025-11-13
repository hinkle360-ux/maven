## Phase A Changelog

### Self‑DMN scheduler operations

- Added implementations of `TICK`, `REFLECT` and `DISSENT_SCAN` to the Self‑DMN brain. These functions enable the brain to schedule periodic scans, perform reflective analysis and scan for dissenting opinions.

### Report path fallback

- Updated `DISSENT_SCAN` logic to read from `reports/self_dmn/claims.jsonl`. When this file does not exist, the method falls back to `reports/self_default/claims.jsonl`, preserving compatibility with earlier versions of the Maven project.

### Personality threshold tuning

- Added `_update_self_dmn_thresholds` to the personality brain (`maven/brains/personal/service/personal_brain.py`). This method adjusts Self‑DMN thresholds based on personality deltas and is called from `ADAPT_WEIGHTS_SUGGEST`.

### Documentation

- Added `phase_A_mini_plan.md` to describe the goals, acceptance criteria, files touched and rollback strategy for this phase.
- Added this changelog (`phase_A_changelog.md`) summarizing all modifications made during Phase A.

These changes bring improved introspection and control to the Self‑DMN brain while maintaining backward compatibility. They introduce no external dependencies and can be reverted cleanly if needed.
