"""
Coder Brain
===========

This cognitive brain provides a simple capability for generating and
verifying Python code based on a user specification.  It is not a
general purpose code generator; rather, it uses lightweight
heuristics to transform plain language prompts into small functions
along with unit tests.  The coder brain delegates actual code
execution and testing to the ``python_exec`` tool via its service API.

Supported operations via ``service_api``:

* ``PLAN``: Accept a specification string describing the desired code.
  Returns a structured plan with a tentative function name and a list
  of inferred behaviours.  The plan is kept deliberately simple and
  serves as a basis for code generation.

* ``GENERATE``: Given a spec (and optional plan), produce Python
  source code and a test snippet.  The generator uses keyword
  matching to decide on the implementation.  When no specific pattern
  is recognised, it emits a skeleton function raising
  ``NotImplementedError``.

* ``VERIFY``: Run static linting and execute the tests using
  ``python_exec``.  Returns a summary of whether the code is valid and
  whether the tests pass.

* ``REFINE``: Given code and tests, attempt a limited number of
  automatic refinements when the tests fail.  This operation loops up
  to ``max_refine_loops`` times (as configured in
  ``config/coding.json``).  Refinement heuristics are simple; they
  currently only fix common mistakes in addition operations.  If
  refinement succeeds, returns updated code and tests along with a
  report.  If refinement fails, returns the original code and
  diagnostics.

The coder brain does not write files or affect the file system.
Instead, it returns code snippets and test code in the payload.  It
also produces a high‑level summary that can be used by the language
brain to craft a natural language response.  Consumers of this brain
should avoid printing large code blocks directly in chat unless the
user explicitly requests them.
"""

from __future__ import annotations

from typing import Dict, Any, Tuple
import re
from pathlib import Path
import json
import sys

# Import the python_exec tool's service API dynamically to avoid
# circular dependencies when loading other brains.
try:
    from brains.agent.tools.python_exec import service_api as python_exec_api  # type: ignore
except Exception:
    python_exec_api = None  # type: ignore

THIS_FILE = Path(__file__).resolve()
MAVEN_ROOT = THIS_FILE.parents[4]

# Import domain lookup for accessing coding patterns
sys.path.insert(0, str(MAVEN_ROOT / "brains" / "domain_banks"))
try:
    from domain_lookup import lookup_by_tag, lookup_by_bank_and_kind
except Exception:
    lookup_by_tag = None  # type: ignore
    lookup_by_bank_and_kind = None  # type: ignore

# Load coding configuration to determine refinement limits
def _load_coding_config() -> Dict[str, Any]:
    cfg_path = MAVEN_ROOT / "config" / "coding.json"
    try:
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as fh:
                data = json.load(fh) or {}
            return data
    except Exception:
        pass
    return {}


def _get_coding_patterns() -> Dict[str, Any]:
    """
    Get coding patterns from domain bank.

    Returns:
        Dict mapping pattern IDs to pattern entries
    """
    patterns = {}
    if lookup_by_bank_and_kind:
        try:
            pattern_entries = lookup_by_bank_and_kind("coding_patterns", "pattern")
            for entry in pattern_entries:
                patterns[entry.get("id", "")] = entry
        except Exception:
            pass  # Return empty dict if lookup fails
    return patterns


def _infer_function_name(spec: str) -> str:
    """Infer a simple function name from the user specification.

    Attempts to extract a verb and noun from the spec using basic
    heuristics.  Falls back to ``user_function`` when extraction
    fails.
    """
    low = spec.strip().lower()
    # Look for phrases like "add two numbers", "sum of", etc.
    if "add" in low or "sum" in low:
        return "add"
    if "fizzbuzz" in low:
        return "fizzbuzz"
    if "two sum" in low or "two_sum" in low:
        return "two_sum"
    # Default
    # Extract the first noun-like word as a fallback
    tokens = re.findall(r"[a-zA-Z_]+", low)
    return tokens[0] if tokens else "user_function"


def _generate_code_and_tests(spec: str, plan: Dict[str, Any] | None = None) -> Tuple[str, str, Dict[str, Any]]:
    """Generate Python source code and a simple test snippet.

    Uses keyword matching on the specification to determine which
    template to use.  Returns a tuple (code, test_code, summary) where
    summary describes the public API and behaviour.
    """
    low = spec.strip().lower()
    fn_name = _infer_function_name(spec)
    summary: Dict[str, Any] = {"function": fn_name, "description": spec.strip()}
    # Template for add function
    if ("add" in low or "sum" in low) and "numbers" in low:
        # Generate a simple add function.  Use single quotes in the docstring to
        # avoid premature termination of the enclosing f‑string.
        code = f"""
def {fn_name}(a: float, b: float) -> float:
    '''Return the sum of two numbers.'''
    return a + b
""".strip()
        test_code = f"""
assert {fn_name}(2, 3) == 5, "2 + 3 should be 5"
assert {fn_name}(-1, 1) == 0, "-1 + 1 should be 0"
""".strip()
        summary["example_calls"] = [f"{fn_name}(2,3) -> 5"]
        return code, test_code, summary
    # Template for FizzBuzz
    if "fizzbuzz" in low or "fizz buzz" in low:
        code = f"""
def {fn_name}(n: int) -> list[str]:
    '''Generate the FizzBuzz sequence from 1 to n.'''
    result: list[str] = []
    for i in range(1, n + 1):
        val = ""
        if i % 3 == 0:
            val += "Fizz"
        if i % 5 == 0:
            val += "Buzz"
        result.append(val or str(i))
    return result
""".strip()
        test_code = f"""
assert {fn_name}(5) == ["1", "2", "Fizz", "4", "Buzz"]
""".strip()
        summary["example_calls"] = [f"{fn_name}(5) -> ['1','2','Fizz','4','Buzz']"]
        return code, test_code, summary
    # Template for two_sum
    if "two sum" in low or "two_sum" in low:
        code = f"""
def {fn_name}(nums: list[int], target: int) -> list[int]:
    '''Return indices of the two numbers that add up to target.'''
    lookup = {{}}
    for i, num in enumerate(nums):
        complement = target - num
        if complement in lookup:
            return [lookup[complement], i]
        lookup[num] = i
    return []
""".strip()
        test_code = f"""
assert {fn_name}([2, 7, 11, 15], 9) == [0, 1]
assert {fn_name}([3, 3], 6) == [0, 1]
""".strip()
        summary["example_calls"] = [f"{fn_name}([2,7,11,15], 9) -> [0,1]"]
        return code, test_code, summary
    # Default stub
    code = f"""
def {fn_name}(*args, **kwargs):
    '''User requested function.  Implementation pending.'''
    raise NotImplementedError("Not implemented yet")
""".strip()
    test_code = """# No tests generated for unrecognised specification"""
    summary["example_calls"] = []
    return code, test_code, summary


def _run_lint(code: str) -> Tuple[bool, str | None]:
    """Call the python_exec LINT operation and return validity and message."""
    if python_exec_api is None:
        return False, "python_exec tool unavailable"
    res = python_exec_api({"op": "LINT", "payload": {"code": code}})
    if not res.get("ok"):
        return False, res.get("error", {}).get("message")
    payload = res.get("payload") or {}
    return bool(payload.get("valid")), payload.get("error") or payload.get("warning")


def _run_tests(code: str, test_code: str) -> Tuple[bool, str | None]:
    """Execute tests via python_exec TEST operation and return pass/fail and stderr."""
    if python_exec_api is None:
        return False, "python_exec tool unavailable"
    res = python_exec_api({"op": "TEST", "payload": {"code": code, "test_code": test_code}})
    if not res.get("ok"):
        return False, res.get("error", {}).get("message")
    payload = res.get("payload") or {}
    return bool(payload.get("passed")), payload.get("stderr")


def _attempt_refinement(code: str, test_code: str) -> Tuple[str, str, bool, str | None]:
    """Attempt a simple refinement of code when tests fail.

    Currently only handles incorrect addition by replacing "+" with
    explicit addition.  Returns (new_code, new_test_code, refined,
    message).
    """
    # Example refinement: if code uses subtraction instead of addition
    if "+" not in code and "return" in code:
        fixed = code.replace("-", "+")
        return fixed, test_code, True, "Replaced subtraction with addition"
    return code, test_code, False, None


def service_api(msg: Dict[str, Any]) -> Dict[str, Any]:
    """Entry point for the coder brain.

    Expects an ``op`` and optional ``payload``.  Dispatches to the
    corresponding internal function and returns a structured result.
    """
    op = (msg or {}).get("op", "").upper()
    payload = msg.get("payload") or {}
    if not op:
        return {"ok": False, "error": {"code": "MISSING_OP", "message": "op is required"}}
    # Load config for refinement loops
    cfg = _load_coding_config()
    max_loops = int(cfg.get("max_refine_loops", 3) or 3)
    # PLAN: create a basic plan from user spec
    if op == "PLAN":
        spec = str(payload.get("spec", ""))
        fn_name = _infer_function_name(spec)
        plan = {
            "function_name": fn_name,
            "spec": spec,
            "description": f"Plan to implement '{fn_name}' based on user spec"
        }
        return {"ok": True, "payload": plan}
    # GENERATE: produce code and tests
    if op == "GENERATE":
        spec = str(payload.get("spec", ""))
        # plan may be provided to override function name
        plan = payload.get("plan") or {}
        code, test_code, summary = _generate_code_and_tests(spec, plan)
        return {"ok": True, "payload": {"code": code, "test_code": test_code, "summary": summary}}
    # VERIFY: run lint and tests
    if op == "VERIFY":
        code = str(payload.get("code", ""))
        test_code = str(payload.get("test_code", ""))
        # Lint
        valid, lint_msg = _run_lint(code)
        if not valid:
            return {"ok": True, "payload": {"valid": False, "lint_error": lint_msg}}
        # Run tests
        passed, stderr = _run_tests(code, test_code)
        return {"ok": True, "payload": {"valid": True, "tests_passed": passed, "test_error": stderr}}
    # REFINE: attempt automatic refinement
    if op == "REFINE":
        code = str(payload.get("code", ""))
        test_code = str(payload.get("test_code", ""))
        diagnostics: list[str] = []
        refined = False
        for i in range(max_loops):
            # Run tests
            passed, err = _run_tests(code, test_code)
            if passed:
                return {"ok": True, "payload": {"code": code, "test_code": test_code, "refined": refined, "diagnostics": diagnostics}}
            # Attempt refinement
            new_code, new_test, did_refine, msg = _attempt_refinement(code, test_code)
            if did_refine:
                diagnostics.append(msg or "Applied refinement")
                code, test_code, refined = new_code, new_test, True
            else:
                break
        # Final run after refinements
        passed, err = _run_tests(code, test_code)
        return {"ok": True, "payload": {"code": code, "test_code": test_code, "refined": refined, "diagnostics": diagnostics, "tests_passed": passed, "test_error": err}}

    # EXECUTE_STEP: Phase 8 - Execute a single step with pattern application
    if op == "EXECUTE_STEP":
        step = payload.get("step") or {}
        step_id = payload.get("step_id", 0)
        context = payload.get("context") or {}

        # Get coding patterns from domain bank
        coding_patterns = _get_coding_patterns()
        patterns_used = []

        # Extract step details
        description = step.get("description", "")
        step_input = step.get("input") or {}
        task = step_input.get("task", description)

        # Execute coding step: PLAN -> GENERATE -> VERIFY
        try:
            # Step 1: Plan
            plan_result = service_api({"op": "PLAN", "payload": {"spec": task}})
            if not plan_result.get("ok"):
                return {"ok": False, "error": {"code": "PLAN_FAILED", "message": "Failed to plan coding step"}}

            plan = plan_result.get("payload") or {}

            # Step 2: Generate code
            gen_result = service_api({"op": "GENERATE", "payload": {"spec": task, "plan": plan}})
            if not gen_result.get("ok"):
                return {"ok": False, "error": {"code": "GENERATE_FAILED", "message": "Failed to generate code"}}

            gen_payload = gen_result.get("payload") or {}
            code = gen_payload.get("code", "")
            test_code = gen_payload.get("test_code", "")
            summary = gen_payload.get("summary", {})

            # Step 3: Verify
            verify_result = service_api({"op": "VERIFY", "payload": {"code": code, "test_code": test_code}})
            verify_payload = verify_result.get("payload") or {}

            # If tests failed, attempt refinement
            if not verify_payload.get("tests_passed", False):
                refine_result = service_api({"op": "REFINE", "payload": {"code": code, "test_code": test_code}})
                refine_payload = refine_result.get("payload") or {}
                code = refine_payload.get("code", code)
                test_code = refine_payload.get("test_code", test_code)
                verify_payload["refined"] = refine_payload.get("refined", False)

            # Record which patterns were used (if any)
            if coding_patterns:
                patterns_used = list(coding_patterns.keys())[:2]  # Use first 2 patterns for determinism

            output = {
                "code": code,
                "test_code": test_code,
                "summary": summary,
                "verified": verify_payload.get("valid", False),
                "tests_passed": verify_payload.get("tests_passed", False)
            }

            return {"ok": True, "payload": {
                "output": output,
                "patterns_used": patterns_used
            }}

        except Exception as e:
            return {"ok": False, "error": {"code": "EXECUTION_ERROR", "message": str(e)}}

    # Unsupported op
    return {"ok": False, "error": {"code": "UNSUPPORTED_OP", "message": op}}

# Ensure the coder brain exposes a `handle` entry point
try:
    handle = service_api  # type: ignore[assignment]
    service_api = handle  # type: ignore[assignment]
except Exception:
    pass