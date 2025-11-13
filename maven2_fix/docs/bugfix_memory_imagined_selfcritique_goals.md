## Bug Fixes – November 4 2025

This document summarises the bug fixes applied to address several issues identified during a recent system audit.

### 1. Missing Memory Search for Questions

Previously, the memory retrieval stage skipped searches when the input was not considered storable—this included questions (which are marked as non‑storable).  As a result, questions like “Is red one of the spectrum colors?” failed to retrieve existing knowledge.  The retrieval logic has been updated to treat **questions** as eligible for memory search, even when they are not storable.  This change ensures that asking a question triggers a memory lookup so the system can answer based on previously learned facts.

### 2. Imagined Answer Echoing the Question

The imaginer sometimes returned a speculative answer that simply echoed the question with a generic prefix (e.g., “It might be that…”).  A heuristic filter now discards imagined answers that are essentially identical to the original question or its prompt.  Only genuinely different hypotheses are considered, preventing meaningless “imagined_answer” candidates from cluttering the response pool.

### 3. Self‑Critique Always Says “Well Done”

The self‑critique brain previously returned “Well done.” for all answers shorter than 100 characters, regardless of quality.  The critique function now checks for missing or uncertain answers and encourages improvements when appropriate.  Long answers still prompt conciseness, while well‑formed responses receive positive feedback.

### 4. Goal Parent/Child Structure Inconsistency

When splitting compound commands into multiple goals, the planner assigned both a `parent_id` and a `depends_on` relationship for each sub‑goal.  This dual specification caused confusion about the intended execution order.  The planner has been simplified to use **only** the `depends_on` field for sequential tasks; parent–child hierarchy is no longer specified for these sub‑goals.  Each sub‑goal now depends solely on the previous one, clarifying the sequence without redundant hierarchical references.

These fixes improve question answering accuracy, reduce spurious answer candidates, provide more meaningful self‑reflection, and tidy up goal structures.