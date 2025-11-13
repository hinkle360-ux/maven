# Phase 6: True Blackboard and Identity UX Hardening

This document summarises the key concepts and APIs introduced in Phase 6.

## Blackboard Core

The blackboard is a shared working memory that allows cognitive modules
to subscribe to specific keys or tags and receive events when matching
items are added.  Each subscription includes:

- a unique subscriber identifier (usually the brain name),
- an optional `key` filter,
- an optional list of `tags`,
- a minimum confidence threshold,
- a time‑to‑live (`ttl`) defining the maximum age of events, and
- a base priority hint used for arbitration.

Subscriptions are registered via the `BB_SUBSCRIBE` operation on the
memory librarian.  When `CONTROL_CYCLE` is invoked, the librarian:

1. Prunes expired entries from working memory.
2. Collects matching events for each subscriber.
3. Scores each event based on the subscription priority, confidence,
   recency and source reliability.
4. Passes the highest scoring event to the integrator brain for
   arbitration.
5. Dispatches the winning event via the internal message bus.
6. Updates internal cursors to avoid reprocessing the same entries.

Results of each cycle are logged to `reports/blackboard_trace.jsonl`
for offline analysis.

## Identity UX

Identity persistence and recall now respect user consent.  When a user
introduces themselves (e.g. “*I am Alice*”), Maven stores the name in
short‑term memory and asks whether it should remember the name across
sessions.  If the user consents, the name is written to the user
profile (`reports/user_profile.json`).  Subsequent “*Who am I?*”
queries search the current session and, if needed, the persistent
profile.  If Maven fails to recall a name that was just provided, it
apologises and self‑corrects.

Privacy defaults can be configured via `config/privacy.json`:

- `default_retention`: `"session"` or `"persist"`.
- `ask_consent_on_identity`: whether Maven prompts before persisting.
- `session_ttl_minutes`: how long session data remains valid.

## Configuration

Blackboard parameters are defined in `config/blackboard.json`.  These
values can be overridden via environment‑specific JSON files in the
same directory.  Key settings include:

- `max_steps`: maximum nodes visited per event in the graph engine.
- `max_events_per_tick`: maximum events dispatched per cycle.
- `max_runtime_ms`: runtime budget for a single control cycle.
- `starvation_guard`: prevents a single subscriber from monopolising
  the blackboard.

## Observability

Two new JSONL logs enhance transparency:

- `reports/blackboard_trace.jsonl`: records each dispatched event,
  including the subscriber, chosen brain and scores.
- `reports/ux_incidents.jsonl`: records any identity recall misses
  and the corresponding recovery actions.

These logs can be analysed offline to tune arbitration parameters,
detect starvation patterns and verify that identity handling behaves
as intended.