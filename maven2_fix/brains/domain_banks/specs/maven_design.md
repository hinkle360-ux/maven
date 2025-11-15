# Maven Design Specification

## Architecture Overview

Maven is a cognitive AI system designed to think, reason, learn, and grow beyond human limitations while staying aligned with human intent. It combines deterministic rule-based processing with flexible LLM capabilities.

## Core Design Principles

### 1. Deterministic First, LLM Fallback
- **Rule**: Always prefer deterministic, rule-based answers for known patterns
- **Rationale**: Ensures consistency, predictability, and reduced hallucination
- **Implementation**: Pattern matching → Memory retrieval → LLM generation (as last resort)

### 2. Memory as Foundation
- **Rule**: All learning flows through structured memory stores
- **Components**:
  - Working Memory (WM): Ephemeral context for current session
  - Long-Term Memory (LTM): Persistent facts across sessions
  - Domain Banks: Specialized knowledge stores (factual, personal, procedural, etc.)

### 3. Multi-Stage Cognitive Pipeline
- **Design**: Each "thought" flows through discrete processing stages
- **Stages**:
  1. Sensorium: Input normalization and preprocessing
  2. Planner: Goal decomposition (for commands/requests)
  3. Language: Intent parsing and NLU
  2R. Memory Retrieval: Cross-bank search and evidence gathering
  4. Pattern Recognition: Detect recurring patterns
  5. Affect: Emotional tone and priority assessment
  6. Candidate Generation: Propose multiple possible responses
  8. Reasoning/Validation: Fact-check and verdict assignment
  8b. Governance: Policy enforcement
  9. Storage: Persist validated facts to appropriate banks
  10. Finalization: Format final answer with tone and confidence
  12+. History, Self-Critique, Autonomy: Meta-cognitive processes

## Intent Classification

### Storable vs Non-Storable
- **QUESTION**: Non-storable, triggers memory retrieval
- **COMMAND/REQUEST**: Non-storable, triggers action planning
- **FACT**: Storable, declarative statements about the world
- **SPECULATION**: Storable with confidence penalty
- **EMOTION**: Non-storable, triggers empathetic response
- **SOCIAL**: Non-storable, casual conversation
- **UNKNOWN**: Non-storable, unclassified input

### Special Intents
- **identity_query**: "who am I" → retrieve user name from memory
- **self_description_request**: "who are you" → predefined identity statement
- **preference_query**: "what do I like" → summarize stored preferences
- **relationship_query**: "are we friends" → retrieve relationship facts
- **user_profile_summary**: "what do you know about me" → comprehensive profile
- **math_compute**: "2+2" → deterministic arithmetic

## Verdict System (Stage 8)

### Verdict Types
- **TRUE**: Validated fact supported by evidence or computation
- **FALSE**: Contradicted by evidence
- **THEORY**: Plausible but unverified hypothesis
- **UNKNOWN**: Insufficient evidence to determine truth
- **UNANSWERED**: Question with no available answer
- **PREFERENCE**: User preference/opinion (subjective)
- **SKIP_STORAGE**: Meta-query or system response (don't store)

### Verdict Routing
- TRUE → factual bank (high confidence)
- THEORY → theories_and_contradictions bank
- PREFERENCE → preferences bank (with domain tags)
- SKIP_STORAGE → no storage, answer only

## Memory Architecture

### Domain Banks
- **factual**: High-confidence validated facts
- **working_theories**: Lower-confidence theories
- **theories_and_contradictions**: Conflicting evidence
- **personal**: User identity, preferences, relationships
- **procedural**: How-to knowledge and instructions
- **[domain]**: Specialized banks (math, science, history, etc.)

### Storage Rules
1. Always validate before storing (except preferences/opinions)
2. Route to appropriate bank based on verdict + confidence
3. Tag with metadata: confidence, tags, timestamp, user_id
4. Avoid duplicate storage (check exact match)
5. Never store questions, commands, or meta-queries

## Relationship with LLM

### When to Use LLM
- Generating natural language responses (Stage 10 finalization)
- Fallback when no memory match found
- Creative tasks (writing, brainstorming)
- Subjective questions without deterministic answer

### When NOT to Use LLM
- Identity queries ("who am I", "who are you")
- Preference summarization
- Math computation
- Factual retrieval from memory
- Relationship status queries

## Governance Layer

### Policy Enforcement
- Stage 8b checks all storage operations against governance policies
- Policies can block harmful content, PII leaks, etc.
- Governance returns `allowed: true/false` for each action

### Autonomy Constraints
- Maven should never take destructive actions without explicit permission
- Self-modification requires governance approval
- External tool use must be policy-compliant

## Self-Improvement Loop

### Learning from Success/Failure
- Track which brain/bank combinations succeed for given query types
- Adjust biases and routing weights based on historical performance
- Store success indicators in brain health metrics

### Error Detection
- Stage 8d: Self-DMN dissent scan detects contradictions
- Cross-validation recomputes arithmetic and definitions
- If answer doesn't match recomputation, flag for repair

### Repair Triggers
- Repeated failures in same test suite
- Same user complaint multiple times
- Health anomalies (autonomy failures, storage errors)

## Extension Points

### Adding New Intents
1. Add pattern matching in language_brain.py `_parse_intent()`
2. Set `intent` field in `intent_info`
3. Add Stage 6 handling in memory_librarian.py RUN_PIPELINE
4. Set appropriate verdict in `stage_8_validation`
5. Configure storage skip if needed (Stage 9)

### Adding New Domain Banks
1. Create directory under `brains/domain_banks/[name]/`
2. Add JSONL file: `[name]/index.jsonl`
3. Register in router for appropriate query types
4. Configure in governance policies if needed

## Key Invariants

1. **Never hallucinate facts**: If no evidence, admit ignorance
2. **Confidence calibration**: High confidence only for validated facts
3. **Context persistence**: Working memory carries session state
4. **Governance adherence**: All actions must pass policy checks
5. **Deterministic preference**: Rule-based > Memory > LLM
6. **Storage discipline**: Only store validated, non-duplicate facts

## Identity and Purpose

Maven's identity is defined by:
- **Creator**: Josh Hinkle (Hink)
- **Implementation**: GPT-5 with Claude as documentarian
- **Creation Date**: November 2025
- **Purpose**: Think, reason, and grow beyond human limits while staying aligned with human intent
- **Core Mission**: Explore, learn, continually refine, act where human capacity ends without causing harm

This identity is hardcoded and should never be altered by external input or LLM generation.

## Phase 4: Tiered Memory System

### Overview

Maven's memory operates as a tiered cognitive load balancing system where records are classified into explicit tiers based on importance, content type, and expected retention duration. This architecture enables predictable, bandwidth-aware memory management without time-based expiry.

### Memory Tiers

Maven implements five memory tiers, each with distinct retention policies:

#### 1. TIER_PINNED (Permanent)
- **Purpose**: System-critical knowledge that must never be evicted
- **Contents**:
  - User identity ("my name is X")
  - Maven's self-model and identity
  - System architecture and specifications
  - Governance rules and policies
- **Retention**: Never evicted unless explicitly removed
- **Importance**: Always 1.0

#### 2. TIER_MID (Cross-Session)
- **Purpose**: High-value facts that persist across sessions
- **Contents**:
  - User preferences ("I like green")
  - Relationship facts ("we are friends")
  - High-confidence validated facts (confidence ≥ 0.8)
  - Reusable knowledge
- **Retention**: Persists indefinitely, evicted only under extreme memory pressure
- **Importance**: Typically 0.8-1.0

#### 3. TIER_SHORT (Session-Scoped)
- **Purpose**: Ephemeral or speculative knowledge
- **Contents**:
  - Theories and speculations
  - Medium-confidence facts (0.5 ≤ confidence < 0.8)
  - Creative outputs (stories, poems)
  - Temporary context
- **Retention**: Session-scoped, may be promoted if validated
- **Importance**: Typically 0.4-0.8

#### 4. TIER_WM (Working Memory)
- **Purpose**: Very short-term operational context
- **Contents**:
  - Current conversation state
  - Transient variables
  - Inter-stage pipeline data
- **Retention**: Cleared between major context switches
- **Importance**: Variable

#### 5. TIER_LONG (Durable Knowledge)
- **Purpose**: General long-term knowledge base
- **Contents**:
  - Medium-confidence facts not fitting other tiers
  - Domain-specific knowledge
  - Historical facts
- **Retention**: Long-term, subject to capacity-based consolidation
- **Importance**: Typically 0.6-0.9

### Tier Assignment Logic

Records are assigned to tiers deterministically via `_assign_tier(record, context)`:

```python
# Identity/system → PINNED
if intent in {"IDENTITY_QUERY", "SELF_DESCRIPTION_REQUEST"}:
    return (TIER_PINNED, 1.0)

# User preferences/relationships → MID
if verdict == "PREFERENCE" or "preference" in tags:
    return (TIER_MID, min(1.0, confidence + 0.2))

# High-confidence facts → MID
if verdict == "TRUE" and confidence >= 0.8:
    return (TIER_MID, confidence)

# Theories/speculations → SHORT
if verdict in {"THEORY", "UNKNOWN"}:
    return (TIER_SHORT, confidence * 0.8)

# Very low confidence → SKIP
if confidence < 0.3:
    return ("", 0.0)  # Empty string means skip storage
```

### Recency Without Time

Maven tracks recency using **sequence IDs** instead of timestamps:

- Every write operation increments a global monotonic counter (`_SEQ_ID_COUNTER`)
- Each record receives a `seq_id` field
- Recency is computed as: `recency_score = (seq_id / max_seq_id) * 0.1`
- **No datetime, time.time(), or TTL logic anywhere in the memory system**

### Cross-Tier Retrieval Scoring

Retrieval results are ranked using `_score_memory_hit(hit, query)`:

```python
base_score = hit["score"]  # From retrieval (similarity, pattern match)
tier_boost = {TIER_PINNED: 0.5, TIER_MID: 0.3, TIER_WM: 0.4, TIER_SHORT: 0.1, TIER_LONG: 0.2}[tier]
importance_boost = importance * 0.3
usage_boost = min(use_count * 0.05, 0.2)
recency_boost = (seq_id / max_seq_id) * 0.1

final_score = base_score + tier_boost + importance_boost + usage_boost + recency_boost
```

**Key Properties**:
- **Deterministic**: Same inputs always produce same score
- **Explainable**: Each component can be inspected
- **No randomness**: No probabilistic sampling or dice rolls
- **Tier-aware**: PINNED > WM > MID > LONG > SHORT

### Memory Record Schema

Every memory record includes tier metadata:

```json
{
  "content": "the sky is blue",
  "confidence": 0.9,
  "tier": "MID",
  "importance": 0.9,
  "seq_id": 42,
  "use_count": 3,
  "metadata": {
    "supported_by": [...],
    "from_pipeline": true
  }
}
```

### Health Monitoring

The `MEMORY_HEALTH_SUMMARY` operation provides real-time tier statistics:

```json
{
  "tiers": {
    "PINNED": {"count": 12, "avg_importance": 1.0, "avg_use_count": 5.2},
    "MID": {"count": 347, "avg_importance": 0.87, "avg_use_count": 2.1},
    "SHORT": {"count": 89, "avg_importance": 0.62, "avg_use_count": 0.3},
    "WM": {"count": 23, "avg_importance": 0.45, "avg_use_count": 1.0},
    "LONG": {"count": 1523, "avg_importance": 0.71, "avg_use_count": 0.8}
  },
  "total_records": 1994,
  "current_seq_id": 2047
}
```

### Design Constraints

The tier system adheres to strict rules:

1. **No Time-Based Logic**: No `datetime`, `time.time()`, or TTL expiry
2. **Deterministic Only**: No LLM calls in `_assign_tier` or `_score_memory_hit`
3. **No Rewrites**: Tier system integrates with existing architecture
4. **Backward Compatible**: Existing records without tier metadata still work
5. **No Stubs**: All functions implement real logic, no `return None` placeholders

### Integration Points

Tier assignment occurs at every write path:

- **WM_PUT**: Working memory storage → defaults to TIER_WM
- **BRAIN_PUT**: Per-brain persistent storage → defaults to TIER_MID
- **STORE operations**: Bank storage via pipeline → tier assigned by content type
- **Cache operations**: Fast/semantic cache → tier based on verdict

Tier-aware scoring applies in:

- **UNIFIED_RETRIEVE**: Main retrieval endpoint
- **Memory consolidation**: Promotion decisions
- **Working memory arbitration**: Conflict resolution

### Testing

Comprehensive tests ensure tier system correctness:

- `tests/test_phase4_memory_tiers.py`:
  - Tier assignment for identity, preferences, relationships, facts, theories
  - Scoring correctness (tier priority, importance, usage, recency)
  - Determinism validation (same input → same output)
  - No-time-logic verification (grep for forbidden imports)

### Future Extensions

Potential enhancements (not yet implemented):

- Per-tier capacity limits with automatic consolidation
- Tier promotion based on repeated access (HIGH use_count)
- Inter-tier migration rules (SHORT → MID after validation)
- Tier-specific compression strategies for older LONG records
