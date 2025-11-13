# Step‑4 Cognitive Graph (Alpha)

This document summarises the changes introduced in the **Step‑4 Alpha**
upgrade of Maven.  Building upon the working memory and control shell
added in Step 1 and the persistence/arbitration/event handling in
Step 2, this phase begins the transition from a strictly linear
broadcast pipeline to a graph‑based cognitive architecture.  While the
existing 14‑stage flow remains intact by default, developers can now
experiment with a *cognitive graph engine* that routes events between
brains based on their declared inputs and outputs.

## Graph Engine

The new `graph_engine.py` module introduces a simple **GraphEngine** and
**GraphNode** classes.  Brains register as nodes with a name, a
processing function and lists of input and output event types.  The
engine supports:

- **register_node(name, func, inputs, outputs)** to add a node.
- **connect(source, dest)** to add a directed edge.
- **emit(event_type, payload, context)** to propagate an event through
  the graph.  Each processed node appends a record to
  `reports/trace_graph.jsonl` containing the timestamp, event type,
  payload and visits.
- **run(context)** to drain the existing message bus and emit all
  pending events.  This allows the graph to be run as a batch after
  the traditional pipeline completes.

By default the graph engine is **disabled**.  A helper `default_graph_engine()`
illustrates how to wrap the existing reasoning, planner and memory
librarian brains into graph nodes.  The graph listens for
`"WM_EVENT"` events and forwards them to the reasoning and planner
nodes.  Developers can extend this pattern to register additional
brains and edges.

## Motivation Brain Enhancements

The motivation brain now provides an opinionated scoring mechanism
(`SCORE_OPPORTUNITIES`) and a goal formulation helper
(`FORMULATE_GOALS`).  These operations assist the autonomy brain
in identifying knowledge gaps and creating high‑level goals.  In
Step‑4 Alpha no changes were made to the public API, but the motivation
brain can be connected into the graph engine to influence attention and
planning via future upgrades.

## Episodic Memory

A new **episodic memory** module (`brains/memory/episodic_memory.py`)
allows Maven to persist experiences.  Episodes capture interaction
snapshots with question, answer, confidence, tags and timestamps.  The
service API supports:

- `EPISODE_STORE`: write an episode to `reports/episodic_memory.jsonl`,
  with optional TTL for expiry.
- `EPISODE_GET`: retrieve stored episodes, optionally limiting the
  number returned.
- `EPISODE_SUMMARY`: produce a compact summary of recent episodes.

Episodic memory enables retrieval of past contexts and paves the way
for eventual integration with semantic and procedural memory.

## Self‑Review Brain

The **self‑review brain** performs rudimentary analysis of trace
records.  Its `RECOMMEND_TUNING` operation reads
`reports/trace_graph.jsonl` (or a custom path) and recommends
parameter adjustments when average confidence is low or processing
times are high.  Suggestions include increasing reasoning depth or
reducing the number of retries.  These recommendations are advisory
only and do not modify behaviour automatically.

## Unified Configuration Schema

To centralise configuration, a `config/maven_schema.json` file has been
added.  It describes top‑level configuration sections such as **wm**
(working memory) and **motivation**, along with default values and
descriptions.  Maven continues to read configuration from
`goals/config.yaml` and environment variables, but this schema
provides a single source of truth for documenting options.

## Future Directions

The Step‑4 Alpha release lays the groundwork for a truly adaptive
cognitive graph.  Upcoming efforts will wire the motivation brain into
the integrator, implement attention nudges based on working memory
events and formalise the planner handshake for plan events.  The
graph engine will gradually assume more responsibilities until it fully
replaces the linear broadcast model.  Meanwhile the existing pipeline
remains functional, ensuring continuity for existing use cases.