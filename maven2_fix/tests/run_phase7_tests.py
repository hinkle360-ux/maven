#!/usr/bin/env python3
"""
Phase 7: Domain Seeding Test Runner

Standalone test runner for Phase 7 domain seeding functionality.
Can be run independently without pytest.
"""

import sys
from pathlib import Path

# Add paths for imports
MAVEN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MAVEN_ROOT / "brains" / "domain_banks" / "specs" / "data" / "seeds"))
sys.path.insert(0, str(MAVEN_ROOT / "brains" / "domain_banks"))
sys.path.insert(0, str(MAVEN_ROOT / "tests"))


def print_header(title: str) -> None:
    """Print a formatted header."""
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)
    print()


def print_section(title: str) -> None:
    """Print a section header."""
    print()
    print(f"--- {title} ---")
    print()


def run_standalone_tests() -> int:
    """
    Run Phase 7 tests without pytest.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    from seed_validator import validate_seeds, ValidationError
    from seeding_engine import run_seeding, SeedingEngine
    from domain_lookup import DomainLookup

    SEEDS_DIR = MAVEN_ROOT / "brains" / "domain_banks" / "specs" / "data" / "seeds"
    RUNTIME_DIR = Path("/home/user/maven/runtime_memory/domain_banks")

    print_header("Phase 7: Domain Seeding Tests (Standalone)")

    passed = 0
    failed = 0
    errors = []

    # Test 1: Seed file schema validation
    print_section("Test 1: Seed File Schema Validation")
    try:
        report = validate_seeds(str(SEEDS_DIR))
        if report["ok"] and report["total_entries"] > 0 and len(report["errors"]) == 0:
            print(f"✓ PASS: Validated {report['total_entries']} seed entries")
            passed += 1
        else:
            print(f"✗ FAIL: Validation failed - {report.get('errors', [])}")
            failed += 1
            errors.append("Seed schema validation failed")
    except Exception as e:
        print(f"✗ FAIL: {e}")
        failed += 1
        errors.append(f"Seed schema validation error: {e}")

    # Test 2: Validate-only mode
    print_section("Test 2: Seeding Validate-Only Mode")
    try:
        report = run_seeding(str(SEEDS_DIR), str(RUNTIME_DIR), validate_only=True)
        if report["ok"] and report["mode"] == "validate_only":
            print(f"✓ PASS: Validate-only mode works ({report['total_entries']} entries)")
            passed += 1
        else:
            print(f"✗ FAIL: Validate-only mode failed")
            failed += 1
            errors.append("Validate-only mode failed")
    except Exception as e:
        print(f"✗ FAIL: {e}")
        failed += 1
        errors.append(f"Validate-only mode error: {e}")

    # Test 3: Apply seeds
    print_section("Test 3: Apply Seeds to Domain Banks")
    try:
        report = run_seeding(str(SEEDS_DIR), str(RUNTIME_DIR), validate_only=False)
        if report["ok"] and report["banks_seeded"] > 0:
            print(f"✓ PASS: Applied seeds to {report['banks_seeded']} banks")
            passed += 1
        else:
            print(f"✗ FAIL: Seeding application failed")
            failed += 1
            errors.append("Seeding application failed")
    except Exception as e:
        print(f"✗ FAIL: {e}")
        failed += 1
        errors.append(f"Seeding application error: {e}")

    # Test 4: Idempotency
    print_section("Test 4: Idempotency Verification")
    try:
        engine = SeedingEngine(str(SEEDS_DIR), str(RUNTIME_DIR))
        result = engine.verify_idempotency()
        if result["ok"] and result["idempotent"]:
            print(f"✓ PASS: Seeding is idempotent ({result['runs']} runs)")
            passed += 1
        else:
            print(f"✗ FAIL: Idempotency check failed - {result.get('differences', [])}")
            failed += 1
            errors.append("Idempotency verification failed")
    except Exception as e:
        print(f"✗ FAIL: {e}")
        failed += 1
        errors.append(f"Idempotency error: {e}")

    # Test 5: Domain lookup functionality
    print_section("Test 5: Domain Lookup Functionality")
    try:
        lookup = DomainLookup(str(RUNTIME_DIR))

        # Test by ID
        entry = lookup.get_by_id("governance_rules:rule:no_randomness")
        if entry and entry["id"] == "governance_rules:rule:no_randomness":
            print("  ✓ Lookup by ID works")
        else:
            raise Exception("Lookup by ID failed")

        # Test by tag
        entries = lookup.get_by_tag("determinism")
        if len(entries) > 0:
            print(f"  ✓ Lookup by tag works ({len(entries)} entries found)")
        else:
            raise Exception("Lookup by tag failed")

        # Test by bank and kind
        rules = lookup.get_by_bank_and_kind("governance_rules", "rule")
        if len(rules) > 0:
            print(f"  ✓ Lookup by bank and kind works ({len(rules)} rules found)")
        else:
            raise Exception("Lookup by bank and kind failed")

        print("✓ PASS: Domain lookup works correctly")
        passed += 1

    except Exception as e:
        print(f"✗ FAIL: {e}")
        failed += 1
        errors.append(f"Domain lookup error: {e}")

    # Test 6: Governance rules loaded
    print_section("Test 6: Governance Rules Loaded")
    try:
        lookup = DomainLookup(str(RUNTIME_DIR))
        rules = lookup.get_by_bank_and_kind("governance_rules", "rule")

        rule_ids = {r.get("id") for r in rules}
        critical_rules = [
            "governance_rules:rule:no_randomness",
            "governance_rules:rule:python_only",
            "governance_rules:rule:explicit_errors"
        ]

        missing = [r for r in critical_rules if r not in rule_ids]
        if len(missing) == 0:
            print(f"✓ PASS: All critical governance rules loaded ({len(rules)} total)")
            passed += 1
        else:
            print(f"✗ FAIL: Missing critical rules: {missing}")
            failed += 1
            errors.append(f"Missing governance rules: {missing}")

    except Exception as e:
        print(f"✗ FAIL: {e}")
        failed += 1
        errors.append(f"Governance rules error: {e}")

    # Test 7: Brain integration
    print_section("Test 7: Brain Integration with Domain Lookup")
    try:
        brain_tests_passed = 0
        brain_tests_total = 0

        # Test coder_brain
        try:
            sys.path.insert(0, str(MAVEN_ROOT / "brains" / "cognitive" / "coder" / "service"))
            import coder_brain
            if hasattr(coder_brain, '_get_coding_patterns'):
                patterns = coder_brain._get_coding_patterns()
                if isinstance(patterns, dict):
                    print("  ✓ coder_brain can access coding patterns")
                    brain_tests_passed += 1
            brain_tests_total += 1
        except Exception as e:
            print(f"  ⚠ coder_brain test skipped: {e}")

        # Test planner_brain
        try:
            sys.path.insert(0, str(MAVEN_ROOT / "brains" / "cognitive" / "planner" / "service"))
            import planner_brain
            if hasattr(planner_brain, '_get_planning_patterns'):
                patterns = planner_brain._get_planning_patterns()
                if isinstance(patterns, dict):
                    print("  ✓ planner_brain can access planning patterns")
                    brain_tests_passed += 1
            brain_tests_total += 1
        except Exception as e:
            print(f"  ⚠ planner_brain test skipped: {e}")

        # Test council_brain seeding operations
        try:
            sys.path.insert(0, str(MAVEN_ROOT / "brains" / "governance" / "council" / "service"))
            import council_brain
            result = council_brain.service_api({
                "op": "DOMAIN_BANK_SEED_VALIDATE",
                "payload": {}
            })
            if result.get("ok"):
                print("  ✓ council_brain seeding operations work")
                brain_tests_passed += 1
            brain_tests_total += 1
        except Exception as e:
            print(f"  ⚠ council_brain test skipped: {e}")

        if brain_tests_passed >= 2:  # At least 2 out of 3
            print(f"✓ PASS: Brain integration works ({brain_tests_passed}/{brain_tests_total} passed)")
            passed += 1
        else:
            print(f"✗ FAIL: Insufficient brain integration ({brain_tests_passed}/{brain_tests_total})")
            failed += 1
            errors.append("Brain integration incomplete")

    except Exception as e:
        print(f"✗ FAIL: {e}")
        failed += 1
        errors.append(f"Brain integration error: {e}")

    # Summary
    print_header("Test Summary")
    print(f"Total tests:  {passed + failed}")
    print(f"Passed:       {passed}")
    print(f"Failed:       {failed}")

    if failed > 0:
        print()
        print("Errors:")
        for error in errors:
            print(f"  ! {error}")

    print()

    return 0 if failed == 0 else 1


def main() -> int:
    """
    Main entry point.

    Returns:
        Exit code
    """
    if "--pytest" in sys.argv:
        # Run with pytest
        import pytest
        test_file = MAVEN_ROOT / "tests" / "test_phase7_domain_seeding.py"
        return pytest.main([str(test_file), "-v", "--tb=short"])
    else:
        # Run standalone
        return run_standalone_tests()


if __name__ == "__main__":
    sys.exit(main())
