# Batch 8: Goal Cleanup, Telemetry & Regression Summary (Nov 4 2025)

This document summarises the eighth batch of improvements applied to Maven during Phase 2.  The work focused on cleaning up residual artefacts, improving membership inference with synonyms, adding telemetry for safety and ethics events, and generating concise regression summaries.

## One‑Off Goal Cleanup

Maven’s planner previously created numerous “junk” goals from conjunctions and fragmented inputs.  Although the runtime pipeline now prunes such tasks automatically, many legacy junk goals remained in the goal memory.  Batch 8 introduces a standalone script:

* **`tools/cleanup_junk_goals.py`**: Scans the goal memory for titles that are single numbers, standalone spectrum colour names, specific prefixes (`“numbers from”`, `“what comes”`) or very short question fragments.  These goals are marked as completed, and a summary of removed items is written to `reports/goal_cleanup/removed_goals_<timestamp>.json`.

This script should be run once to permanently clear the backlog of junk tasks.  Subsequent runs of the main pipeline will continue to handle pruning automatically.

## Membership Inference Using Synonyms

The membership inference logic now resolves synonyms via the `synonyms` module.  For questions of the form “Is X one of …”, Maven canonicalises the subject term using the synonym mapping, looks up all known synonyms for that canonical form, and tests whether any variant appears in the retrieved evidence.  This allows queries with nicknames or epithets (e.g. “scarlet” → “red”) to be answered affirmatively when appropriate.

## Safety and Ethics Telemetry

To provide visibility into how often safety and ethics filters intercept user queries, Batch 8 introduces:

* A **telemetry helper** in `reasoning_brain.py` that logs counts of three event types — `safety_filter`, `ethics_block`, and `ethics_warn` — in `reports/telemetry.json`.  Each time the reasoning brain returns a safety or ethics verdict, the corresponding counter is incremented.
* The **dashboard** (`ui/dashboard.py`) now reads and displays these counts.  Users can see how frequently queries are blocked or cautioned for safety or ethical reasons, alongside other statistics like active goals and QA entries.

## Regression Summary

Batch 8 streamlines regression reporting:

* **Updated nightly script**: `tools/run_nightly_regression.sh` now parses the detailed results produced by `regression_harness.py` and writes a concise summary (`total`, `matches`, `mismatches`) to `reports/regression/summary.json`.  This summary makes it easy to monitor the health of the QA memory without scanning logs.

These enhancements improve Maven’s observability and help maintain a clean, reliable knowledge base.
