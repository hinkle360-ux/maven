# Implementation Log (Phase 2)

This log records incremental upgrades applied to Maven during Phase 2 development.  Each batch corresponds to a discrete set of code changes and enhancements.  The log complements the roadmap by documenting when features were implemented and summarising their purpose.

## Batch 1 — Multi‑Modal Stubs & Ethics Filter (Nov 4 2025)

- **Vision & Hearing stubs:** Created `vision_brain.py` and `hearing_brain.py` under `brains/cognitive/sensorium/service/`.  These modules define placeholder `ANALYZE_IMAGE` and `ANALYZE_AUDIO` operations that return empty feature sets and zero confidence, laying the groundwork for future multi‑modal perception.
- **Dynamic confidence helper:** Added `dynamic_confidence.py` in `brains/cognitive/reasoning/service/` providing a `compute_dynamic_confidence` function that computes a small adjustment based on recent success metrics.  This function currently returns the mean of provided values divided by 10.
- **Ethics rules file:** Added an empty `reports/ethics_rules.json` file to store case‑insensitive substrings that flag ethically sensitive queries.
- **Ethics filter integration:** Modified `reasoning_brain.py` to load patterns from `reports/ethics_rules.json` and return a precautionary answer with `mode` set to `ETHICS_FILTER` when a match is found.  The filter returns an `UNKNOWN` verdict and a low confidence score, similar to the safety filter.
- **Vision & hearing imports:** Ensured the stubs return structured responses via the existing `api.utils` helpers and include a descriptive `detail` field to aid debugging.

## Batch 2 — Dynamic Confidence Integration (Nov 4 2025)

- **Global confidence modulation:** Updated `reasoning_brain.py` to import `compute_dynamic_confidence` from the new helper module.  After computing domain‑specific adjustments via the meta confidence module, the system gathers all recent adjustment values and passes them to `compute_dynamic_confidence`.  The resulting bias is added to the affect valence (`aff_val`) to subtly increase or decrease overall confidence.  Errors in loading or computing the bias are silently ignored.
- **Rationale:** This change introduces a simple rolling confidence adaptation mechanism.  As Maven accumulates successes and failures across domains, the average adjustment influences the global tone of its responses, encouraging self‑tuning without hard‑coded thresholds.

## Batch 3 — Retrieval Caching (Nov 4 2025)

- **Cache for bank retrievals:** Enhanced the memory librarian’s evidence retrieval helpers (`_retrieve_from_banks` and `_retrieve_from_banks_parallel`) with an in‑memory cache keyed by query and limit.  When the same query and limit are used multiple times during a single run, the results are returned from the cache instead of querying every domain bank again.  This reduces unnecessary calls and improves performance.  The cache resets when Maven restarts, ensuring that outdated results do not persist across sessions.

## Batch 4 — Planner Intent Filtering (Nov 4 2025)

- **Command & request gating:** Updated `memory_librarian.service.RUN_PIPELINE` to parse the user input through the language brain before invoking the planner.  The planner is now called **only** when the input is classified as a command or a request (detected via the `is_command`/`is_request` flags or the intent `type`).  This prevents arbitrary statements or questions containing conjunctions (e.g. “and”, “then”) from being split into meaningless sub‑goals.
- **Fallback planning:** For non‑command inputs, the system skips the planner entirely and assigns a simple fallback plan that directs the librarian to retrieve relevant memories and compose a response.  This stops the accumulation of junk goals in `goals.jsonl` and mitigates memory pollution.
- **Stage reordering:** The language parsing stage is now executed before planning so that the decision to invoke the planner can be made based on the parsed intent.  Pattern recognition runs after planning (or fallback), preserving its original position in the pipeline.

## Batch 5 — Question Retrieval & Misc Bug Fixes (Nov 4 2025)

- **Question memory search:** Adjusted memory retrieval logic to search the knowledge base for questions, even though questions are marked as non‑storable.  Previously, questions like “Is red one of the spectrum colors?” skipped retrieval.  Now the librarian treats question inputs as eligible for retrieval while still avoiding storage of the question text itself.
- **Imagined answers filtering:** Added a check in the language brain’s imaginer hook to discard speculative answers that simply repeat the question.  Only meaningful hypotheses are considered as “imagined_answer” candidates.
- **Self‑critique improvements:** Updated the self‑critique brain to provide more contextual feedback.  It now detects when the answer is absent or expresses uncertainty and suggests improvements.  Long answers still trigger a conciseness reminder, while well‑formed responses receive positive reinforcement.
- **Goal sequencing clarity:** Simplified the planner’s sub‑goal generation by removing hierarchical `parent_id` assignments from sequential tasks.  Sub‑goals now depend solely on the previous segment via the `depends_on` field, eliminating redundant parent–child references.

## Batch 6 — Multi‑Tier Ethics & Self‑Review Refinements (Nov 4 2025)

- **Multi‑tier ethics rules:** Enhanced the ethics filter in `reasoning_brain.py` to support structured rules with `pattern`, `action` and `severity` fields in `reports/ethics_rules.json`.  Each rule may specify an `action` of `block` (default) or `warn`, and a `severity` of `low`, `medium` or `high`.  When a question matches a `block` rule, the reasoner returns an `UNKNOWN` verdict with a cautionary answer and adjusts the confidence based on severity.  When a `warn` rule matches, the system continues processing but applies a small negative affect adjustment, lowering the final confidence without blocking the response.  The code remains backwards compatible with the previous unstructured list format by treating each string as a `block` rule with medium severity.
- **Self‑review deduplication & limits:** Refined the Stage 18 self‑review loop in `memory_librarian.py`.  The loop now reads an optional `config/self_review.json` file containing a `threshold` and a `max_goals` limit.  Before adding an “Improve domain: X” goal for a poorly performing domain, the system checks if a goal with the same title already exists (active or completed) and skips duplicates.  It also respects the `max_goals` limit, only creating up to that number of new improvement goals per review pass.  A default limit of five goals is used when the configuration is absent or invalid.  This prevents the goal memory from being flooded with duplicate or excessive improvement tasks.
- **Self‑review configuration file:** Added a new configuration file `config/self_review.json` with default values:
  ```json
  {
    "threshold": -0.03,
    "max_goals": 5
  }
  ```
  Deployers may adjust the threshold for domain performance and the maximum number of improvement goals generated in a single self‑review cycle.

## Batch 7 — Goal Pruning & Yes/No Inference (Nov 4 2025)

- **Junk goal pruning:** Added automatic cleanup of legacy junk goals in Stage 15.  During the autonomy tick stage, the memory librarian now examines active goals and marks as completed any tasks that appear to be artifacts of the earlier segmentation bug.  Heuristics identify junk goals as single digits, spectrum colour names, or very short question fragments.  These goals are excluded from the `stage_15_remaining_goals` context, leaving only legitimate tasks for further processing.
- **Yes/No membership inference:** Improved the reasoning brain’s ability to answer “Is X one of the Y?” questions.  When a question matches this pattern and the retrieved evidence contains the subject, the system now returns a concise affirmative response (e.g. “Yes, Red is one of the spectrum colors”) instead of echoing unrelated facts.  This change enhances answer relevance when membership can be inferred from context.

## Batch 8 — Goal Cleanup, Telemetry & Regression Summary (Nov 4 2025)

- **One‑off goal cleanup script:** Added `tools/cleanup_junk_goals.py`, which scans the goal memory and marks as completed any legacy junk tasks (single digits, spectrum colours, short question fragments).  The script writes a summary of removed goals to `reports/goal_cleanup/removed_goals_<timestamp>.json` so that old artefacts can be archived.  This script is intended to be run manually once; the regular pipeline already prunes junk tasks during autonomy ticks.
- **Membership inference using synonyms:** Enhanced the membership inference in `reasoning_brain.py` to resolve synonyms via the `synonyms` module.  The logic now canonicalises the subject, looks up its synonym group, and matches any variant in the retrieved evidence before inferring a positive response.  This allows questions like “Is scarlet one of the spectrum colours?” to return “Yes, Scarlet is one of the spectrum colours” when “scarlet” maps to “red”.
- **Safety/Ethics telemetry:** Introduced a telemetry helper and file `reports/telemetry.json` to log counts of safety filter, ethics block and ethics warn events.  The reasoning brain updates these counters whenever it triggers a filter.  The dashboard now displays the cumulative counts, providing visibility into how often safety and ethics checks intercept queries.
- **Regression summary generation:** Updated `tools/run_nightly_regression.sh` to parse the results of `regression_harness.py` and write a concise summary (`total`, `matches`, `mismatches`) to `reports/regression/summary.json`.  This allows quick health checks of the QA memory without inspecting detailed logs.
- **Dashboard telemetry:** Modified `ui/dashboard.py` to display the new telemetry metrics alongside existing counts, giving users a clearer picture of safety/ethics activity and self‑review goals.

## Batch 9 — Working Memory Integration & Scheduler (Nov 6 2025)

- **Working memory ops:** Added support for a shared working memory in the `memory_librarian` (Stage 5).  A new global list and lock store key–value entries with tags, confidence and TTL.  Exposed four new operations via `service_api`: `WM_PUT` to store an entry, `WM_GET` to retrieve by key or tags, `WM_DUMP` to inspect all live entries, and `CONTROL_TICK` to prune expired entries and emit a `WM_EVENT` for each remaining item on the internal message bus.
- **Scheduler & events:** The lightweight scheduler introduced by `CONTROL_TICK` lays the groundwork for a cognitive graph.  It scans the working memory, publishes events to the message bus, and does not alter the sequential broadcast pipeline.
- **Documentation & cleanup:** Created `docs/step1_cognitive_graph.md` describing the new API and rationale.  Removed stray `.bak` files and ensured no new package roots or `__init__.py` files were added.

## Batch 10 — Working Memory Recall & Governance Integration (Nov 6 2025)

- **Committee decisions to working memory:** Modified `committee_brain.service_api` to import the memory librarian’s API and store the aggregated committee decision via `WM_PUT`.  When the committee aggregates its votes, it now creates a working memory entry keyed by the final decision (for example, `"committee:approve"`) with the result payload and the committee’s confidence.  The entry includes tags (`"committee"`, `"decision"`) and a five‑minute TTL.  Errors in this integration are non‑blocking.
- **Reasoning recall from working memory:** Added a pre‑heuristic recall step to `reasoning_brain.service_api`.  The reasoner imports the memory librarian and, for each `EVALUATE_FACT` request, attempts a `WM_GET` on the original query or fact content.  If a matching entry is found, the reasoner returns a `KNOWN` verdict in `WM_RETRIEVED` mode with the stored answer and associated confidence, bypassing heavy retrieval and inference.  This opportunistic recall improves responsiveness for repeated or related queries within a single run.
- **Governance policy update:** Updated `docs/governance_policy.md` to include working memory operations (`WM_PUT`, `WM_GET`, `WM_DUMP`, `CONTROL_TICK`) under the “AUDIT‑ONLY” authority category.  Governance now logs these operations for traceability but never blocks them.
- **Rationale:** These changes extend the initial working memory support beyond simple storage by enabling recall and cross‑module use.  They also ensure that working memory operations are properly audited by governance, aligning with the Phase B/C principle of lightweight governance over new autonomy features.

## Batch 11 — WM Persistence, Arbitration & Event Processing (Nov 6 2025)

- **TTL‑aware persistence:** Introduced functions `_wm_store_path`, `_wm_persist_append`, `_wm_load_from_disk` and `_wm_load_if_needed` in `memory_librarian.service`.  When `CFG['wm']['persist']` is true (default), entries written via `WM_PUT` are appended to `reports/wm_store.jsonl` and reloaded into working memory on the next run.  The loader skips expired items and prunes stale entries before returning.
- **Arbitration scoring:** Enhanced `WM_GET` to compute a score for competing entries with the same key: `score = confidence × e^(−age_minutes/60) × source_reliability`.  When multiple entries match a key and `CFG['wm']['arbitration']` is true (default), the results are sorted by score and the API returns a `winner` and `alternatives` alongside the full list.  Each entry includes its computed `score`.
- **Event processing op:** Added a new `PROCESS_EVENTS` operation that drains all messages from the internal `message_bus`, logs them to `reports/wm_events.jsonl`, and returns counts by event type.  This supports offline inspection of WM events and prepares for future scheduler integrations.
- **Persistence gating & flags:** Both persistence and arbitration can be disabled via the global configuration (`config/wm.json` or `CFG['wm']` overrides).  Existing behaviour remains unchanged when disabled.
- **Acceptance tests:** Manually verified that entries persist across processes, that arbitration returns the highest‑scoring item first, and that `PROCESS_EVENTS` drains tick‑generated events and logs them.

## Batch 12 — Cognitive Graph Alpha & New Brains (Nov 6 2025)

- **Cognitive graph engine:** Added `brains/cognitive/graph_engine.py` introducing a `GraphEngine` class and `GraphNode` dataclass.  The engine allows brains to register processing functions, declare input and output event types, connect nodes via directed edges and emit events.  It appends a detailed record of each event propagation to `reports/trace_graph.jsonl`.  A helper `default_graph_engine()` demonstrates wrapping the existing reasoning, planner and memory librarian brains into a small graph; this engine is optional and does not replace the broadcast pipeline by default.
- **Episodic memory:** Added `brains/memory/episodic_memory.py` with operations `EPISODE_STORE`, `EPISODE_GET` and `EPISODE_SUMMARY`.  Episodes record questions, answers, confidences and timestamps to `reports/episodic_memory.jsonl`, optionally expiring via a TTL.  Retrieval returns recent episodes in reverse chronological order and summarises key fields.
- **Self‑review brain:** Added `brains/cognitive/self_review/service/self_review_brain.py`.  This brain defines a `RECOMMEND_TUNING` operation that scans `reports/trace_graph.jsonl` (or another specified file) and suggests adjustments to parameters such as reasoning depth or retry limits based on average confidence and processing duration.  Suggestions are advisory only and do not automatically change behaviour.
- **Unified configuration schema:** Added a JSON schema file `config/maven_schema.json` that describes the structure and defaults of Maven’s configuration.  Sections for working memory and motivation brain include flags for persistence, arbitration and attention nudges.
- **Documentation:** Added `docs/step4_cognitive_graph.md` outlining the Step‑4 Alpha changes, including the graph engine API, episodic memory, self‑review brain and configuration schema.  Updated the implementation log and phase BC changelog with this batch.
- **Future direction:** This batch lays the foundation for a true cognitive graph.  In upcoming iterations the motivation brain will influence attention, the planner will handshake with WM plan events, and the integrator will use WM events to modulate reasoning priorities.

