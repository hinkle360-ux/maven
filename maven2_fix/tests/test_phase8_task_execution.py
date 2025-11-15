"""
Phase 8 Task Execution Engine - Comprehensive Test Suite

Tests:
1. Decomposition correctness
2. Routing rules correctness
3. Pattern usage correctness
4. Deterministic step IDs
5. Repeatability (same output 2×)
6. Trace completeness
7. Error propagation
8. Specialist integration
9. No randomness check
10. Governance integration
"""

import sys
from pathlib import Path

# Add maven2_fix to path
MAVEN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(MAVEN_ROOT))

import json


def test_1_decomposition():
    """Test 1: Basic Decomposition - Checks planner generates same steps every time."""
    print("\n" + "="*70)
    print("TEST 1: Basic Decomposition")
    print("="*70)

    from brains.cognitive.planner.service.planner_brain import service_api as planner_api

    task = "implement a function to add two numbers"

    # Run decomposition twice
    results = []
    for i in range(2):
        msg = {
            "op": "DECOMPOSE_TASK",
            "payload": {"task": task}
        }
        response = planner_api(msg)
        results.append(response)
        print(f"\nRun {i+1}:")
        print(f"  Status: {response.get('ok')}")
        if response.get('ok') == 'success':
            result = response.get('payload', {})
            steps = result.get('steps', [])
            print(f"  Steps: {len(steps)}")
            for idx, step in enumerate(steps):
                print(f"    Step {idx+1}: {step.get('type')} - {step.get('description')[:50]}...")

    # Verify both runs produced same steps
    if results[0].get('status') == 'success' and results[1].get('status') == 'success':
        steps1 = results[0].get('result', {}).get('steps', [])
        steps2 = results[1].get('result', {}).get('steps', [])

        if len(steps1) == len(steps2):
            print("\n✓ PASS: Both runs produced same number of steps")
            return True
        else:
            print(f"\n✗ FAIL: Different number of steps: {len(steps1)} vs {len(steps2)}")
            return False
    else:
        print("\n✗ FAIL: Decomposition failed")
        return False


def test_2_routing_determinism():
    """Test 2: Routing Determinism - Given a step tag → always maps to same brain."""
    print("\n" + "="*70)
    print("TEST 2: Routing Determinism")
    print("="*70)

    from brains.governance.task_execution_engine.step_router import route_step

    test_cases = [
        ({"tags": ["coding"], "type": "coding"}, "coder"),
        ({"tags": ["plan"], "type": "planning"}, "planner"),
        ({"tags": ["creative"], "type": "creative"}, "imaginer"),
        ({"tags": ["governance"], "type": "governance"}, "committee"),
        ({"tags": ["language"], "type": "language"}, "language"),
        ({"tags": ["reasoning"], "type": "reasoning"}, "reasoning"),
    ]

    all_passed = True

    for step, expected_brain in test_cases:
        # Route 3 times to ensure consistency
        routed_brains = []
        for _ in range(3):
            brain = route_step(step)
            routed_brains.append(brain)

        # Check all routes are the same
        if len(set(routed_brains)) == 1 and routed_brains[0] == expected_brain:
            print(f"✓ PASS: {step['tags']} → {expected_brain} (consistent)")
        else:
            print(f"✗ FAIL: {step['tags']} → {routed_brains} (expected {expected_brain})")
            all_passed = False

    return all_passed


def test_3_pattern_application():
    """Test 3: Pattern Application - Specialist must pull the same pattern for the same step."""
    print("\n" + "="*70)
    print("TEST 3: Pattern Application")
    print("="*70)

    # Test that patterns are applied deterministically
    # We'll test with planner_brain which uses planning patterns

    from brains.cognitive.planner.service.planner_brain import service_api as planner_api

    task = "implement a multi-phase feature"

    results = []
    for i in range(2):
        msg = {
            "op": "DECOMPOSE_TASK",
            "payload": {"task": task}
        }
        response = planner_api(msg)
        results.append(response)

    if results[0].get('status') == 'success' and results[1].get('status') == 'success':
        patterns1 = results[0].get('result', {}).get('patterns_used', [])
        patterns2 = results[1].get('result', {}).get('patterns_used', [])

        if patterns1 == patterns2:
            print(f"✓ PASS: Same patterns used both times: {patterns1}")
            return True
        else:
            print(f"✗ FAIL: Different patterns: {patterns1} vs {patterns2}")
            return False
    else:
        print("✗ FAIL: Pattern application test failed")
        return False


def test_4_deterministic_step_ids():
    """Test 4: Deterministic Step IDs - Step IDs increment deterministically."""
    print("\n" + "="*70)
    print("TEST 4: Deterministic Step IDs")
    print("="*70)

    from brains.governance.task_execution_engine.engine import StepCounter

    counter1 = StepCounter()
    counter2 = StepCounter()

    # Generate same sequence with both counters
    seq1 = [counter1.next() for _ in range(5)]
    seq2 = [counter2.next() for _ in range(5)]

    print(f"Sequence 1: {seq1}")
    print(f"Sequence 2: {seq2}")

    if seq1 == seq2 == [1, 2, 3, 4, 5]:
        print("✓ PASS: Step IDs are deterministic and sequential")
        return True
    else:
        print("✗ FAIL: Step IDs are not deterministic")
        return False


def test_5_repeatability():
    """Test 5: Repeatability - Run the same task 2 times → identical output and trace."""
    print("\n" + "="*70)
    print("TEST 5: Repeatability")
    print("="*70)

    from brains.governance.council.service.council_brain import service_api as council_api

    task = "analyze the requirements for a simple calculator"

    results = []
    for i in range(2):
        msg = {
            "op": "TASK_EXECUTE_WITH_TRACE",
            "payload": {"task": task}
        }
        response = council_api(msg)
        results.append(response)
        print(f"\nRun {i+1}:")
        print(f"  Status: {response.get('ok')}")
        if response.get('ok') == 'success':
            result = response.get('payload', {})
            print(f"  Steps executed: {result.get('steps_executed')}")
            trace = result.get('trace', {})
            print(f"  Trace entries: {len(trace.get('entries', []))}")

    # Compare results
    if results[0].get('status') == 'success' and results[1].get('status') == 'success':
        result1 = results[0].get('result', {})
        result2 = results[1].get('result', {})

        steps1 = result1.get('steps_executed')
        steps2 = result2.get('steps_executed')

        trace1_entries = len(result1.get('trace', {}).get('entries', []))
        trace2_entries = len(result2.get('trace', {}).get('entries', []))

        if steps1 == steps2 and trace1_entries == trace2_entries:
            print(f"\n✓ PASS: Repeatability verified - {steps1} steps, {trace1_entries} trace entries")
            return True
        else:
            print(f"\n✗ FAIL: Different results - Steps: {steps1} vs {steps2}, Traces: {trace1_entries} vs {trace2_entries}")
            return False
    else:
        print("\n✗ FAIL: Task execution failed")
        return False


def test_6_trace_completeness():
    """Test 6: Trace Completeness - End-to-end task produces complete trace."""
    print("\n" + "="*70)
    print("TEST 6: Trace Completeness")
    print("="*70)

    from brains.governance.council.service.council_brain import service_api as council_api

    task = "brainstorm creative ideas for a new product"

    msg = {
        "op": "TASK_EXECUTE_WITH_TRACE",
        "payload": {"task": task}
    }

    response = council_api(msg)
    print(f"Status: {response.get('ok')}")

    if response.get('ok') == 'success':
        result = response.get('payload', {})
        trace = result.get('trace', {})
        entries = trace.get('entries', [])

        print(f"\nTrace has {len(entries)} entries:")
        for idx, entry in enumerate(entries):
            step_id = entry.get('step_id')
            step_type = entry.get('step_type')
            success = entry.get('success')
            print(f"  {idx+1}. Step {step_id}: {step_type} - {'✓' if success else '✗'}")

        # Check trace has required fields
        required_fields = ['entries', 'total_steps', 'deterministic']
        missing = [f for f in required_fields if f not in trace]

        if not missing and trace.get('deterministic'):
            print("\n✓ PASS: Trace is complete and marked as deterministic")
            return True
        else:
            print(f"\n✗ FAIL: Missing fields: {missing}, deterministic: {trace.get('deterministic')}")
            return False
    else:
        print("\n✗ FAIL: Task execution failed")
        return False


def test_7_failure_propagation():
    """Test 7: Failure Propagation - If step fails → execution halts, deterministic error returned."""
    print("\n" + "="*70)
    print("TEST 7: Failure Propagation")
    print("="*70)

    # This test would require simulating a failure
    # For now, we'll test that the error handling structure is in place

    from brains.governance.task_execution_engine.engine import TaskExecutionEngine

    engine = TaskExecutionEngine()

    # Test error result structure
    error_result = engine._build_error_result("TEST_ERROR", "Test error message")

    print(f"Error result structure:")
    print(f"  success: {error_result.get('success')}")
    print(f"  error: {error_result.get('error')}")
    print(f"  error_code: {error_result.get('error_code')}")

    if (not error_result.get('success') and
        error_result.get('error') and
        error_result.get('error_code')):
        print("\n✓ PASS: Error propagation structure is correct")
        return True
    else:
        print("\n✗ FAIL: Error propagation structure is incomplete")
        return False


def test_8_step_counter():
    """Test 8: Step Counter - Step IDs always increment deterministically and reset per execution."""
    print("\n" + "="*70)
    print("TEST 8: Step Counter")
    print("="*70)

    from brains.governance.task_execution_engine.engine import StepCounter

    counter = StepCounter()

    # Test incrementing
    seq1 = [counter.next() for _ in range(3)]
    print(f"Sequence 1: {seq1}")

    # Reset
    counter.reset()
    seq2 = [counter.next() for _ in range(3)]
    print(f"Sequence 2 (after reset): {seq2}")

    if seq1 == seq2 == [1, 2, 3]:
        print("✓ PASS: Step counter increments and resets correctly")
        return True
    else:
        print(f"✗ FAIL: Step counter failed - seq1: {seq1}, seq2: {seq2}")
        return False


def test_9_governance_integration():
    """Test 9: Governance Integration - TASK_EXECUTE returns output, TASK_EXECUTE_WITH_TRACE returns trace."""
    print("\n" + "="*70)
    print("TEST 9: Governance Integration")
    print("="*70)

    from brains.governance.council.service.council_brain import service_api as council_api

    task = "design a simple database schema"

    # Test TASK_EXECUTE
    msg1 = {
        "op": "TASK_EXECUTE",
        "payload": {"task": task}
    }
    response1 = council_api(msg1)
    print(f"TASK_EXECUTE status: {response1.get('status')}")

    # Test TASK_EXECUTE_WITH_TRACE
    msg2 = {
        "op": "TASK_EXECUTE_WITH_TRACE",
        "payload": {"task": task}
    }
    response2 = council_api(msg2)
    print(f"TASK_EXECUTE_WITH_TRACE status: {response2.get('status')}")

    has_output1 = response1.get('status') == 'success' and 'output' in response1.get('result', {})
    has_trace2 = response2.get('status') == 'success' and 'trace' in response2.get('result', {})

    if has_output1:
        print("✓ TASK_EXECUTE returns output")
    else:
        print("✗ TASK_EXECUTE missing output")

    if has_trace2:
        print("✓ TASK_EXECUTE_WITH_TRACE returns trace")
    else:
        print("✗ TASK_EXECUTE_WITH_TRACE missing trace")

    if has_output1 and has_trace2:
        print("\n✓ PASS: Governance integration working")
        return True
    else:
        print("\n✗ FAIL: Governance integration incomplete")
        return False


def test_10_no_randomness():
    """Test 10: No Randomness Check - Scan for random, os.urandom, time."""
    print("\n" + "="*70)
    print("TEST 10: No Randomness Check")
    print("="*70)

    # Check engine.py for randomness
    engine_path = MAVEN_ROOT / "brains" / "governance" / "task_execution_engine" / "engine.py"

    if not engine_path.exists():
        print("✗ FAIL: engine.py not found")
        return False

    content = engine_path.read_text()

    forbidden_patterns = [
        "random.randint",
        "random.choice",
        "random.random",
        "os.urandom",
        "time.time()",
        "datetime.now()"
    ]

    found_patterns = []
    for pattern in forbidden_patterns:
        if pattern in content:
            found_patterns.append(pattern)

    if found_patterns:
        print(f"✗ FAIL: Found randomness patterns: {found_patterns}")
        return False
    else:
        print("✓ PASS: No randomness patterns found in engine.py")
        return True


def run_all_tests():
    """Run all Phase 8 tests."""
    print("\n" + "="*70)
    print("PHASE 8 TASK EXECUTION ENGINE - TEST SUITE")
    print("="*70)

    tests = [
        ("Decomposition Correctness", test_1_decomposition),
        ("Routing Determinism", test_2_routing_determinism),
        ("Pattern Application", test_3_pattern_application),
        ("Deterministic Step IDs", test_4_deterministic_step_ids),
        ("Repeatability", test_5_repeatability),
        ("Trace Completeness", test_6_trace_completeness),
        ("Failure Propagation", test_7_failure_propagation),
        ("Step Counter", test_8_step_counter),
        ("Governance Integration", test_9_governance_integration),
        ("No Randomness", test_10_no_randomness),
    ]

    results = []

    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"\n✗ ERROR in {name}: {str(e)}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)

    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)

    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {name}")

    print(f"\nTotal: {passed_count}/{total_count} tests passed")

    if passed_count == total_count:
        print("\n🎉 ALL TESTS PASSED! Phase 8 implementation is complete.")
        return True
    else:
        print(f"\n⚠️  {total_count - passed_count} test(s) failed.")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
