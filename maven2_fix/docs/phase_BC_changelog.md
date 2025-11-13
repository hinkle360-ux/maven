## Phase B & C Changelog

### Configuration centralization

- Added `_load_cfg_overrides` and helper `_update_dict` to
  `maven/api/utils.py`.  At import time, the loader scans the `config`
  folder in the Maven project for JSON files (excluding *_thresholds.json)
  and merges their contents into the global `CFG` dictionary.  This
  provides a unified place for runtime overrides without touching code.

### Local control shim

- Added `maven/run_self_dmn_control.py`, a small command‑line utility that
  dynamically loads the Self‑DMN brain and exposes its operations via
  arguments.  Supported operations include `TICK`, `REFLECT`,
  `DISSENT_SCAN` and `ANALYZE_INTERNAL`.  The tool returns JSON results,
  facilitating manual introspection and testing.

### Packaging & persistence

- Added `maven/tools/compact_self_dmn_logs.py`, a utility that trims
  JSONL log files in `reports/self_dmn` to a specified number of trailing
  entries (default 1000).  This helps manage log size and supports
  persistence policies in Phase C.

### Documentation

- Added `maven/phase_BC_mini_plan.md` outlining the goals, acceptance
  criteria, touched files and rollback strategy for Phases B & C.
- Added this changelog (`maven/phase_BC_changelog.md`) summarizing all
  modifications made during the combined phases.

No existing files were removed, and the Maven pipeline continues to run
as before.  The new utilities are optional and do not interfere with
the default execution flow unless explicitly invoked.

### Working memory and scheduler integration (Nov 6 2025)

- **Shared working memory:** Extended `memory_librarian.service_api` with four new operations (`WM_PUT`, `WM_GET`, `WM_DUMP`, `CONTROL_TICK`) to support a short‑lived working memory for Stage 5.  These operations store and retrieve key–value entries with tags, confidence and TTL, dump the current working memory for diagnostics, and trigger a lightweight scheduler tick that emits one `WM_EVENT` per live entry.
- **Cognitive graph groundwork:** The scheduler introduced by `CONTROL_TICK` scans the working memory and publishes events via the internal message bus.  This prepares the system for a future cognitive graph without altering the sequential broadcast pipeline.
- **Documentation:** Added `docs/step1_cognitive_graph.md` to describe the new API and removed stray `.bak` files.  The upgrade adheres to Phase B/C rules: no new package roots or `__init__.py` files and no stage order changes.

### Working memory recall & governance integration (Nov 6 2025)

- **Committee decisions stored in working memory:** Enhanced `committee_brain.service_api` to import the memory librarian and store the aggregated decision via `WM_PUT`.  Each decision is keyed by `committee:<decision>` and includes the committee’s confidence and tags (`committee`, `decision`).  A five‑minute TTL allows opportunistic recall without polluting long‑term memory.
- **Reasoning brain recall hook:** Added a preliminary `WM_GET` lookup in `reasoning_brain.service_api`.  Before performing heavy reasoning, the reasoner attempts to retrieve an answer for the original query from working memory.  On a hit, it returns a `KNOWN` verdict with mode `WM_RETRIEVED`, the stored answer and confidence, bypassing further inference.  This provides faster responses for repeated questions within a single run.
- **Governance policy update:** Updated `docs/governance_policy.md` to classify all working memory operations (`WM_PUT`, `WM_GET`, `WM_DUMP`, `CONTROL_TICK`) as **audit‑only**.  These actions are logged by governance but never blocked, ensuring transparency without impeding the pipeline.

### WM persistence, arbitration & event processing (Nov 6 2025)

- **Persistence of working memory:** Added support for TTL‑aware persistence.  `WM_PUT` now appends entries to `reports/wm_store.jsonl` when persistence is enabled.  On subsequent runs the librarian hydrates the in‑memory WM from this file (ignoring expired entries).  The feature is toggled via `CFG['wm']['persist']` and defaults to on.
- **Arbitration scoring:** `WM_GET` now computes a score for entries sharing the same key and returns the highest‑scoring entry as `winner` along with a sorted list of `alternatives`.  The score multiplies confidence, a recency decay and a source reliability factor.  Arbitration can be disabled with `CFG['wm']['arbitration']=false`.
- **Event draining operation:** Introduced `PROCESS_EVENTS` to the memory librarian API.  This op calls `message_bus.pop_all()`, writes each event to `reports/wm_events.jsonl` for auditing and returns a summary count by event type.
- **Configuration flags:** Added `persist` and `arbitration` keys under `wm` in `CFG`.  Both default to `true` and can be set in `config/wm.json` to disable persistence or arbitration.

### Full cognitive graph integration (Nov 6 2025)

The Step‑4 alpha release introduces a number of new capabilities to the
cognitive architecture.  These features are disabled by default and can be
enabled by creating a `config/graph.json` override file.

- **Bounded graph execution:** The `GraphEngine` now accepts an optional
  `max_steps` parameter.  During event propagation the engine will halt
  after the specified number of node visits, preventing infinite loops
  from poorly connected graphs.  A trace of visited nodes and their
  outputs is written to `reports/trace_graph.jsonl` for offline
  inspection.
- **Attention nudge:** When `wm.nudge` is `true` in the configuration,
  bids submitted by the reasoning and planner brains receive a +0.05
  priority boost during attention resolution.  This allows working
  memory events to steer focus towards evaluation and planning when
  relevant evidence is present.
- **Motivational drive modulation:** A new `SCORE_DRIVE` operation in the
  motivation brain computes a scalar drive signal based on recent
  success, affect and contradictions.  The integrator multiplies bid
  priorities by `(1 + 0.2 * drive)` to favour higher drive states and
  de‑emphasise contradictory situations.
- **Plan handshake:** The planner brain exposes a `PLAN_FROM_WM` API
  that constructs a single goal for each working memory entry tagged
  with `plan`.  Goals are prefixed with `WM_PLAN:` followed by the
  memory key and recorded in the system ledger.
- **Configuration defaults:** A new `config/graph.json` file introduces
  default values for graph enablement and maximum steps, working memory
  nudging and arbitration, and motivation weights.  The override loader
  automatically merges these values into `CFG` on startup.

