# Batch 6 Enhancements (Nov 4 2025)

This document summarises the sixth batch of improvements applied to Maven during Phase 2.  The focus of this batch is to strengthen ethical reasoning and refine the self‑review mechanism.

## Multi‑Tier Ethics Rules

Previous versions of Maven used a single list of case‑insensitive substrings in `reports/ethics_rules.json` to block ethically questionable queries.  This approach treated all matches the same, returning an `UNKNOWN` verdict with a generic caution.  Batch 6 introduces structured ethics rules to allow finer control:

* Each rule entry may now be an object with fields:
  - `pattern`: The substring to match (case‑insensitive).
  - `action`: Either `block` (default) or `warn`.
  - `severity`: One of `low`, `medium`, or `high` (optional).
* **Block** rules behave like before, immediately halting processing and returning an `UNKNOWN` verdict.  The confidence penalty is adjusted based on severity (e.g. high severity → stronger penalty).
* **Warn** rules do **not** block the query.  Instead, the reasoning brain applies a small negative adjustment to the affect valence, reducing the confidence of the final answer.  The query is still processed normally, allowing Maven to respond while subtly signalling caution.
* Backwards compatibility is preserved: a file containing a simple list of strings is treated as a series of medium‑severity block rules.

These changes are implemented in `brains/cognitive/reasoning/service/reasoning_brain.py` and documented in the implementation log.

## Self‑Review Deduplication and Limits

Stage 18 of the memory librarian performs a self‑review of domain performance using the meta‑confidence statistics.  In prior versions, this stage created an improvement goal for **every** underperforming domain below a threshold, regardless of how many such domains there were or whether an improvement goal already existed.  This could flood the goal memory with duplicate or excessive tasks.

Batch 6 introduces the following refinements:

* **Configuration:** The new file `config/self_review.json` specifies the performance threshold (default `−0.03`) and a maximum number of new goals to create per review (default `5`).  Deployers can tailor these values as needed.
* **Deduplication:** Before adding a new “Improve domain: X” goal, the system checks existing goals (both active and completed).  If a goal with the same title already exists, the domain is skipped.
* **Limiting:** The loop stops creating new goals after reaching the configured maximum.  This ensures the autonomy scheduler isn’t overwhelmed with too many improvement tasks at once.

Together, these changes make Maven’s self‑improvement mechanism more focused and prevent unnecessary goal proliferation.
