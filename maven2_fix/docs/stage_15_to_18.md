# Stage 15–18 Interactions
This document summarises the interactions between stages 15 through 18 in Maven's cognitive pipeline.

## Stage 15 – Goal Replanning
Pending goals are inspected, and stale goals (older than the configured replan_age_minutes) are broken down into fresh sub-goals. The original goal is marked completed and new goals are added to goal memory with split actions.

## Stage 16 – Regression Harness
A lightweight regression check compares current answers against the QA memory. Contradictions or drifts are logged to `reports/self_repair.jsonl` for later repair. When enough QA entries exist, the regression harness invokes the reasoning brain on stored questions to detect divergences.

## Stage 17 – Memory Pruning & Assimilation
If the QA memory file exceeds a configurable size (default 100 entries), old entries are pruned. Simple definitions (questions like “what is X?” or “who is X?” with short answers) are assimilated into the semantic knowledge graph before deletion. Statistics about the pruning and assimilation process are recorded in `stage_17_memory_pruning` within the pipeline context.

## Stage 18 – Self‑Review & Improvement Goals
Meta-confidence statistics identify domains where recent performance is poor (adjustment below a threshold). For each underperforming domain, a new goal “Improve domain: <domain>” is created. These self-review goals guide the autonomy scheduler to focus learning on weak areas. Errors are recorded under `stage_18_self_review_error`.
