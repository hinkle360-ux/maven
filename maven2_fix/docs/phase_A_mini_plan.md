# Phase A Mini Plan

## Goals

- **Self-DMN scheduler operations**: Introduce and wire up `TICK`, `REFLECT` and `DISSENT_SCAN` operations for the Self‑DMN brain. These operations allow the Self‑DMN to regularly scan, reflect and dissent on its own outputs.
- **Report path unification**: Consolidate report paths under `reports/self_dmn/`, while maintaining a fallback to legacy `reports/self_default` paths for backward compatibility.
- **Personality ↔ Self-DMN thresholds**: Add a mechanism for the personality brain to adjust Self‑DMN thresholds, enabling dynamic bias/threshold tuning based on recent personality signals.

## Acceptance Criteria

- Invoking the Self‑DMN brain with `TICK`, `REFLECT` or `DISSENT_SCAN` functions properly and uses the unified report paths.
- When `reports/self_dmn/claims.jsonl` is absent, the system falls back to `reports/self_default/claims.jsonl` without errors.
- The personality brain updates Self‑DMN thresholds via a new `_update_self_dmn_thresholds` method and demonstrates changes in the internal configuration.

## Files to Touch

- `maven/brains/cognitive/self_dmn/service/self_dmn_brain.py` – implement scheduler hooks and fallbacks.
- `maven/brains/cognitive/personality/service/personal_brain.py` – add `_update_self_dmn_thresholds` and call it from existing weight suggestion logic.
- `maven/phase_A_mini_plan.md` and `maven/phase_A_changelog.md` – documentation of the plan and changes.

## Rollback Plan

If issues are encountered during Phase A, revert modifications to the Self‑DMN and personality brains and remove these plan and changelog files. Confirm that all tests pass and the system reverts to its previous stable state.
