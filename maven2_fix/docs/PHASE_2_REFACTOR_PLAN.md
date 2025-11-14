# Maven Phase 2 Architectural Refactor - Preparation Plan

## Overview

This document outlines the preparation analysis for Maven's Phase 2 architectural refactor, which will convert the system from a language-brain-centric orchestration model to a memory-librarian + blackboard orchestration model (message bus architecture).

**IMPORTANT**: This is a PLANNING document only. NO code changes should be made until Phase 2 implementation is explicitly authorized.

---

## Current Architecture Analysis

### 1. Orchestration Flow

**Current State (Already Partially Refactored)**:
- `run_maven.py` entry point calls `memory_librarian.service_api({"op": "RUN_PIPELINE", ...})`
- `memory_librarian` acts as the **primary orchestrator** for the 15-stage pipeline
- `language_brain.service_api` handles specific operations: PARSE, GENERATE_CANDIDATES, FINALIZE
- Other cognitive brains are invoked via `_brain_module()` helper function

**Key Finding**: The architecture is already closer to the target than initially assumed. Memory librarian IS the current orchestrator, not language brain.

### 2. Language Brain Service API Operations

Located in: `brains/cognitive/language/service/language_brain.py:2332`

**Current Operations**:
1. **PARSE** (line 2345): Intent parsing, NLU classification
2. **GENERATE_CANDIDATES** (line 2721): Response candidate generation
3. **FINALIZE** (line 6069): Final answer formatting with tone/confidence
4. **HEALTH** (line 6580): Health check endpoint

**Stage Operations NOT in language_brain**:
- Stage 1 (Sensorium): Handled by `sensorium_brain`
- Stage 2 (Planner): Handled by `planner_brain`
- Stage 2R (Memory): Handled by `memory_librarian` internal methods
- Stage 4 (Pattern Recognition): Handled by `pattern_recognition_brain`
- Stage 5 (Affect): Handled by `affect_priority_brain`
- Stage 8 (Reasoning/Validation): Handled by `reasoning_brain`
- Stage 8b (Governance): Handled by `council_brain`
- Stage 9 (Storage): Handled by `memory_librarian` internal methods
- Stage 10 (Finalization): Delegated to `language_brain.service_api({op:FINALIZE})`

### 3. Data Dependencies Between Modules

**Context Flow** (`ctx` dictionary):
```
memory_librarian (RUN_PIPELINE)
  ├─> stage_1_sensorium (sensorium_brain)
  ├─> stage_2_planner (planner_brain)
  ├─> stage_3_language (language_brain PARSE)
  ├─> stage_4_pattern_recognition (pattern_recognition_brain)
  ├─> stage_5_affect (affect_priority_brain)
  ├─> stage_5b_attention (integrator_brain)
  ├─> stage_2R_memory (memory_librarian internal)
  ├─> stage_8_validation (reasoning_brain)
  ├─> stage_8b_governance (council_brain via policy_engine)
  ├─> stage_6_candidates (language_brain GENERATE_CANDIDATES)
  ├─> stage_9_storage (memory_librarian internal)
  ├─> stage_10_finalize (language_brain FINALIZE)
  ├─> stage_12_history (system_history_brain)
  ├─> stage_self_eval (self_dmn/self_critique)
  └─> final_answer, final_confidence (returned to caller)
```

**Key Dependencies**:

| Module | Reads From Ctx | Writes To Ctx | External Calls |
|--------|----------------|---------------|----------------|
| memory_librarian | (root orchestrator) | All stages | _brain_module(), _mem_call() |
| language_brain | stage_3_language, stage_5_affect | stage_3_language, stage_6_candidates, stage_10_finalize | _mem_call() for memory operations |
| pattern_recognition | stage_3_language | stage_4_pattern_recognition | None (isolated) |
| reasoning_brain | stage_2R_memory, stage_3_language | stage_8_validation | None |
| affect_priority | stage_3_language | stage_5_affect | None |
| planner_brain | text, intent | stage_2_planner | None |
| sensorium_brain | text, user_id | stage_1_sensorium | None |
| governance/council | stage_8_validation, stage_9_storage | stage_8b_governance | policy_engine |

### 4. Internal Calls in language_brain.service_api

**Shared Operations (Stage-independent)**:
- `_diag_enabled()`, `_diag_log()`: Diagnostic logging
- `_safe_val()`: Response validation
- `_clean()`: Text normalization
- `_mem_call()`: Memory librarian API calls
- `nlu_parse()`: Public NLU interface
- `update_context()`, `get_context_window()`: Conversation context

**PARSE Operation (Stage 3)**:
- `_parse_intent()`: Intent classification (lines 1056-1617)
  - Contains 500+ lines of pattern matching logic
  - Handles: greetings, questions, commands, facts, speculation, relationships, preferences, identity queries
  - Returns: `{type, intent, storable, confidence_penalty, is_question, is_command, ...}`
- `_classify_personal()`: Personal information classification
- `_extract_subject()`: Subject extraction from text
- `classify_storable_type()`: Storage type determination

**GENERATE_CANDIDATES Operation (Stage 6)**:
- `_try_template()`: Template-based candidate generation
- `_try_heuristic()`: Heuristic-based candidates
- `_llm_generate()`: LLM fallback generation
- `_passed_memory()`: Check if memory retrieval succeeded
- `knowledge_gap()`: Detect knowledge gaps
- `_governance_permit_generate()`: Check generation permissions
- `allow_llm_fallback()`: Determine LLM fallback eligibility
- `_build_self_description()`: Identity response builder
- `generate_for_acknowledgment()`: Acknowledgment candidates
- `generate_for_continuation()`: Continuation candidates
- `_generate_high_effort_response()`: Complex response generation
- `build_generation_prompt()`: LLM prompt construction

**FINALIZE Operation (Stage 10)**:
- `_answerize()`: Convert evidence to answer form
- `_best_evidence()`: Select best evidence
- `_tone_wrap()`: Apply tone/personality
- `_apply_verbosity()`: Adjust response length
- `_infer_user_tone()`: Detect user tone
- `_confidence_explanation()`: Generate confidence explanations
- `_transparency_tag()`: Add transparency markers
- `_suggest_related_topics()`: Related topic suggestions

---

## Phase 2 Refactor Goals

### Target Architecture: Blackboard + Bus Pattern

**Vision**:
```
┌─────────────────────────────────────────────────┐
│        Message Bus / Blackboard Orchestrator    │
│  (Centralized state, stage scheduling, routing) │
└─────────────────────────────────────────────────┘
              ↓           ↓           ↓
    ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
    │  Sensorium  │  │  Language   │  │   Memory    │
    │    Brain    │  │    Brain    │  │  Librarian  │
    └─────────────┘  └─────────────┘  └─────────────┘
              ↓           ↓           ↓
    ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
    │  Pattern    │  │  Reasoning  │  │  Governance │
    │ Recognition │  │    Brain    │  │   Council   │
    └─────────────┘  └─────────────┘  └─────────────┘
```

### What Should Move

**1. Create New Module: `brains/cognitive/turn_engine/`**

This module will extract the orchestration logic from `memory_librarian` and create a reusable turn-based execution engine.

**Components to Extract**:
- Stage sequencing logic (currently in `memory_librarian.service_api RUN_PIPELINE`)
- Context (`ctx`) initialization and propagation
- Brain invocation via `_brain_module()`
- Diagnostic tracing integration
- Seed management for determinism
- Fast cache and semantic cache integration points
- Stage timing and performance tracking

**2. Keep in memory_librarian**:
- `_mem_call()` internal memory operations
- Bank routing logic (Stage 2R)
- Storage operations (Stage 9)
- Unified retrieve, store, update APIs
- Semantic cache management
- Memory consolidation triggers

**3. Keep in language_brain**:
- `_parse_intent()` and all NLU pattern matching (Stage 3 PARSE)
- Candidate generation logic (Stage 6 GENERATE_CANDIDATES)
- Finalization logic (Stage 10 FINALIZE)
- Conversation context management

### What Stays

**Unchanged Modules**:
- All cognitive brains (sensorium, planner, pattern_recognition, reasoning, affect, etc.)
- All governance brains (council, policy_engine, repair_engine)
- All domain banks
- All personal/agent brains
- Test harness and spec bundle
- Entry point (`run_maven.py`)

---

## Minimum Viable Bus/Orchestrator Module

### Proposed Structure

```
brains/cognitive/turn_engine/
├── __init__.py
├── service/
│   ├── __init__.py
│   ├── turn_orchestrator.py    # Main orchestrator
│   ├── blackboard.py            # Shared context/state
│   ├── stage_registry.py        # Stage definitions
│   └── brain_invoker.py         # Brain invocation helper
└── config/
    └── pipeline_config.json     # Stage order, dependencies
```

### Core Interfaces

**1. TurnOrchestrator**:
```python
def run_turn(text: str, user_id: str, session_id: str) -> Dict[str, Any]:
    """Execute one complete cognitive turn through all stages."""
    # Initialize blackboard
    # Load pipeline config
    # Execute stages in order
    # Return final context
```

**2. Blackboard**:
```python
class Blackboard:
    """Shared context state across all brains in a turn."""
    def __init__(self):
        self.ctx = {}  # Current context
        self.history = []  # Stage execution history
        self.trace = []  # Diagnostic trace

    def get_stage_result(self, stage_name: str) -> Any:
        """Retrieve result from specific stage."""

    def set_stage_result(self, stage_name: str, result: Any):
        """Store result from stage."""
```

**3. StageRegistry**:
```python
class StageRegistry:
    """Registry of all pipeline stages and their brain mappings."""
    stages = {
        "stage_1_sensorium": {"brain": "sensorium", "op": "PROCESS"},
        "stage_2_planner": {"brain": "planner", "op": "PLAN"},
        "stage_3_language": {"brain": "language", "op": "PARSE"},
        # ... etc
    }
```

---

## Exact Order of Code Movement

### Phase 2A: Preparation (Current Phase - Planning Only)
1. ✅ Document current architecture
2. ✅ Map all dependencies
3. ✅ Identify extraction candidates
4. ✅ Create refactor plan
5. ⏸️ Wait for explicit authorization to proceed

### Phase 2B: Create Turn Engine Stub (NOT YET AUTHORIZED)
1. Create `brains/cognitive/turn_engine/` directory structure
2. Create empty `turn_orchestrator.py` with function signatures
3. Create `blackboard.py` with basic context class
4. Create `stage_registry.py` with stage definitions
5. **DO NOT** modify any existing brain code

### Phase 2C: Extract Orchestration Logic (NOT YET AUTHORIZED)
1. Copy RUN_PIPELINE logic from `memory_librarian.py` to `turn_orchestrator.py`
2. Refactor to use Blackboard pattern instead of raw ctx dict
3. Extract `_brain_module()` helper to `brain_invoker.py`
4. Update memory_librarian to delegate RUN_PIPELINE to turn_orchestrator
5. Run full regression test suite
6. Verify all tests pass

### Phase 2D: Consolidate Stage Operations (NOT YET AUTHORIZED)
1. Move stage sequencing to `stage_registry.py`
2. Make turn_orchestrator config-driven
3. Enable dynamic stage injection/removal
4. Add stage dependency checking
5. Run full regression test suite

### Phase 2E: Cleanup and Documentation (NOT YET AUTHORIZED)
1. Remove dead code from memory_librarian
2. Update all documentation
3. Update maven_design.md spec
4. Create migration guide
5. Final regression testing

---

## Potential Risks

### High Risk
1. **Breaking existing behavior**: Any refactor of the orchestration layer could break deterministic behaviors
2. **Context propagation bugs**: `ctx` dict is central to all stages; errors in propagation = pipeline failures
3. **Test coverage gaps**: Not all edge cases may be covered by current test suite

### Medium Risk
1. **Performance regression**: Adding indirection layers (bus/blackboard) could slow down turns
2. **Diagnostic compatibility**: Current tracing and logging must remain functional
3. **Governance bypass**: Refactor could accidentally bypass policy checks

### Low Risk
1. **Import path changes**: Moving code = different import paths, but fixable
2. **Configuration complexity**: New config files add complexity but are manageable

---

## Required Tests

### Unit Tests
- [ ] Blackboard state management
- [ ] Stage registry lookups
- [ ] Brain invoker message passing
- [ ] Turn orchestrator initialization

### Integration Tests
- [ ] Full pipeline execution (sensorium → finalize)
- [ ] Context propagation across all stages
- [ ] Error handling at each stage
- [ ] Fast cache + semantic cache integration
- [ ] Governance policy enforcement

### Regression Tests
- [ ] All existing behavioral contracts MUST pass
- [ ] All identity tests MUST pass
- [ ] All preference/relationship tests MUST pass
- [ ] All storage tests MUST pass
- [ ] Performance benchmarks MUST NOT regress >10%

---

## Files Affected (When Implementation Begins)

### New Files
- `brains/cognitive/turn_engine/__init__.py`
- `brains/cognitive/turn_engine/service/__init__.py`
- `brains/cognitive/turn_engine/service/turn_orchestrator.py`
- `brains/cognitive/turn_engine/service/blackboard.py`
- `brains/cognitive/turn_engine/service/stage_registry.py`
- `brains/cognitive/turn_engine/service/brain_invoker.py`
- `brains/cognitive/turn_engine/config/pipeline_config.json`

### Modified Files
- `brains/cognitive/memory_librarian/service/memory_librarian.py` (extract RUN_PIPELINE logic)
- `run_maven.py` (potentially update imports if entry point changes)
- `docs/maven_design.md` (update architecture documentation)
- `tests/run_tests.py` (potentially add turn_engine tests)

### Unchanged Files (Many - Key Ones)
- `brains/cognitive/language/service/language_brain.py` (no changes)
- `brains/cognitive/pattern_recognition/service/pattern_recognition_brain.py`
- `brains/cognitive/reasoning/service/reasoning_brain.py`
- All domain banks
- All governance brains
- All personal brains
- Test contracts and spec bundle

---

## Summary

**Current Status**:
- Memory librarian is already the orchestrator (better than expected!)
- Language brain handles 3 specific stage operations (PARSE, GENERATE_CANDIDATES, FINALIZE)
- Architecture is partially modular but orchestration logic is embedded in memory_librarian

**Phase 2 Goal**:
- Extract orchestration logic into dedicated `turn_engine` module
- Implement blackboard/bus pattern for cleaner state management
- Make pipeline config-driven and extensible
- Maintain 100% behavioral compatibility

**Next Steps**:
- ✅ Phase 2A Complete: Planning and dependency mapping done
- ⏸️ **AWAITING AUTHORIZATION** for Phase 2B (stub creation)
- ⏸️ **AWAITING AUTHORIZATION** for Phase 2C (code extraction)

**Recommendation**:
Before proceeding with Phase 2 implementation, complete Phase 3 (repair engine infrastructure) to ensure self-repair capabilities are in place BEFORE making architectural changes. This provides a safety net if refactoring introduces regressions.

---

## End of Phase 2 Preparation Document
**Date**: 2025-11-14
**Status**: Planning Complete, Implementation NOT Started
**Author**: Claude (Maven Development Assistant)
