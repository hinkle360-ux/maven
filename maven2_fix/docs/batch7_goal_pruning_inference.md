# Batch 7: Goal Pruning and Membership Inference (Nov 4 2025)

This document summarises the seventh batch of improvements applied to Maven during Phase 2.  The focus of this batch is cleaning up legacy artefacts from the autonomy system and enhancing the reasoning brain’s handling of certain yes/no questions.

## Automatic Pruning of Junk Goals

Early versions of Maven’s planner created spurious “goals” when splitting user inputs containing conjunctions.  Examples include single digits (`"1"`, `"2"`), isolated colour names (`"Red"`, `"orange"`), or partial question fragments (`"3?"`, `"What comes"`).  These junk goals persisted in the system’s memory even after the underlying planner bug was fixed.

Batch 7 introduces a pruning step in Stage 15 of the memory librarian:

* After running autonomy ticks, the librarian fetches all active goals.
* Each goal’s title is inspected using simple heuristics:
  - **Numeric:** Titles matching a sequence of digits (e.g. `"0"`, `"1"`) are treated as junk.
  - **Colour names:** Titles equal to the seven colours of the visible spectrum (`red`, `orange`, `yellow`, `green`, `blue`, `indigo`, `violet`) are removed.
  - **Question fragments:** Titles starting with `"numbers from"` or `"what comes"`, or ending with a question mark (and very short), are considered artefacts.
* Junk goals are marked as completed via `goal_memory.complete_goal()`.  They no longer appear in `stage_15_remaining_goals` and are skipped by the autonomy scheduler.

These heuristics remove the old clutter while leaving legitimate goals intact.  Deployers can modify the patterns as needed.

## Membership Inference in Yes/No Questions

Maven’s reasoning brain now better handles queries like “Is red one of the spectrum colors?”  Previously, the system retrieved the fact “Red is a color” and returned it verbatim, which did not directly answer the yes/no question.

The improved logic works as follows:

* When the original query is a yes/no question beginning with **“Is X one of …”**, the reasoning brain attempts to identify the subject (`X`) and the group (`…`).
* After retrieving evidence, if the subject appears within the retrieved answer text, Maven infers an affirmative response.  For example, given a question about **red** and evidence listing the spectrum colors, the answer becomes “Yes, Red is one of the spectrum colors.”
* The confidence is adjusted based on existing affect metrics and evidence but the answer is concise and directly addresses the membership question.

This heuristic enhances user trust by providing clear yes/no answers when they can be inferred from stored knowledge.
