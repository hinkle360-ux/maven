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
