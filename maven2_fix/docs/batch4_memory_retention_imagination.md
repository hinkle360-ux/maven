## Batch 4 — Memory Retention & Imagination Config (Nov 4 2025)

This document records the fourth batch of enhancements applied during Phase 2 of Maven’s development.  The updates focus on controlling memory growth and tuning the imagination sandbox via configuration files.  These changes ensure that Maven’s persistent logs remain manageable and that speculative reasoning can be adjusted without modifying code.

### Query log pruning

To prevent unbounded growth of the cross‑run query history, the `_save_context_snapshot()` helper in `memory_librarian.py` now prunes the `reports/query_log.jsonl` file based on a configurable limit.  After each snapshot is written, the system reads `config/memory.json` for the key `query_log_max_entries` (defaulting to 500).  If the query log contains more than this number of entries, the oldest lines are removed, keeping only the most recent queries.  Pruning is performed silently and does not affect the normal pipeline flow.

### Memory configuration extension

The memory configuration file (`config/memory.json`) has been extended with a new property:

```json
{
  "qa_memory_max_entries": 100,
  "query_log_max_entries": 500
}
```

This new key exposes the retention threshold for the query log.  Administrators can adjust this number up or down to control how many past queries Maven remembers across sessions.  Setting the value to 0 disables pruning altogether.

### Imagination sandbox tuning

The imaginer brain has been modified to respect a configurable maximum number of hypothetical roll‑outs.  The service now reads `config/imagination.json` and checks the `max_rollouts` field.  When generating hypotheses via the `HYPOTHESIZE` operation, the imaginer limits the number of returned statements to the minimum of:

1. The number requested by the caller (`n`);
2. The configured `max_rollouts` (if present and within 1–20);
3. The number of available template prompts (currently five).

If the configuration file is missing or contains an invalid value, the imaginer falls back to the number of available templates.  By increasing `max_rollouts` (e.g. to 10) in `config/imagination.json`, developers can enable deeper speculative reasoning without changing code.

These updates collectively improve the robustness and tunability of Maven’s memory and imagination systems, supporting long‑term operation and flexible experimentation.
