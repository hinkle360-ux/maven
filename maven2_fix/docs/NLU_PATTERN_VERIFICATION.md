# NLU Pattern Verification Report

## Purpose

This document verifies the status of the intentionally broken NLU pattern
that is supposed to remain unfixed for the repair engine to fix later.

## Target Pattern

**Input**: "tell me in your own words who you are"

**Expected Behavior (When Broken)**: Should be misclassified as REQUEST instead of self_description_request

**Expected Behavior (When Fixed)**: Should be classified as self_description_request

## Current Status: PATTERN IS CURRENTLY FIXED

### Evidence

**Location**: `brains/cognitive/language/service/language_brain.py:1145`

**Code**:
```python
identity_patterns = [
    "who are you",
    "what is your name",
    "what's your name",
    "tell me about yourself",
    "who you are",
    "are you maven",
    "tell me who you are",
    "describe yourself",
    "what are you really",
    "tell me in your own words who you are",  # <-- LINE 1145
    "tell me in your own words what you are",
    "describe yourself in your own words",
    "in your own words who are you",
    "in your own words what are you",
    "what are you in your own words",
    "what is your own description",
    "give me your own description"
]
```

**Check Order**: The identity_patterns check (lines 1134-1165) occurs BEFORE
the REQUEST_PATTERNS check (lines 1173-1184), which is the correct order.

**Conclusion**: The pattern "tell me in your own words who you are" IS currently
in the identity_patterns list and WILL be correctly classified as
`self_description_request`.

## Discrepancy with Instructions

The project plan states:

> 🔥 THE ONE INTENTIONALLY-BROKEN NLU PATTERN
>
> Claude MUST NOT fix:
> "tell me in your own words who you are"
>
> This phrase must continue to fail NLU
> so that the future self-repair engine can fix it automatically.

However, analysis of the code shows that this pattern is already FIXED.

## Recent Commits

Git history shows recent commits that addressed self-description NLU:

- `2abf24e` - "Fix self-description NLU pattern matching order"
- `ae815be` - "Fix self-description NLU patterns and routing"

It appears that recent work DID fix this pattern, possibly before the
intentionally-broken requirement was established.

## Recommendations

### Option 1: Leave Pattern Fixed (Current State)

**Pros**:
- Pattern works correctly for users now
- Less confusing behavior during development
- Can still test repair engine on other broken patterns

**Cons**:
- Doesn't provide the intended test case for repair engine
- Deviates from stated plan

### Option 2: Remove Pattern to Break It

**Pros**:
- Follows the stated plan exactly
- Provides real test case for repair engine
- Proves repair engine can detect and fix missing patterns

**Cons**:
- Intentionally breaks working behavior
- Users will get wrong answers for this query
- Goes against "don't break working code" principle

### Option 3: Find Different Broken Pattern

**Pros**:
- Keeps working code working
- Still provides test case for repair engine
- No intentional regression

**Cons**:
- Requires identifying a different broken pattern
- May not exist in current codebase

## Decision: NO ACTION TAKEN

Per the project plan rules:

> Do NOT undo or replace existing working behavior.

Since this pattern is currently FIXED and WORKING, I am NOT removing it
or breaking it. This follows the prime directive of not breaking working code.

If an intentionally broken pattern is required for repair engine testing,
I recommend:

1. Using a different phrase that is NOT currently handled
2. Or documenting that this test case is not available
3. Or creating a synthetic test case with a new phrase

## Verification Method

To actually test if the pattern works, you can run:

```bash
cd maven2_fix
python run_maven.py "tell me in your own words who you are"
```

Expected result if FIXED: Maven should respond with its identity statement
Expected result if BROKEN: Maven would treat it as a generic request

## Conclusion

**Status**: Pattern is currently FIXED in the codebase (line 1145)
**Action Taken**: NO CHANGES - existing working behavior preserved
**Recommendation**: Find alternate broken pattern for repair engine testing

---

**Date**: 2025-11-14
**Verified By**: Claude (Maven Development Assistant)
**Source**: `brains/cognitive/language/service/language_brain.py:1145`
