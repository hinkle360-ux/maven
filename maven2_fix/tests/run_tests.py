#!/usr/bin/env python3
"""
Maven Regression Test Harness

Executes behavioral contract tests defined in maven_behavior_contracts.json
and generates detailed reports on pass/fail status.

Usage:
    python tests/run_tests.py [--suite SUITE_NAME] [--test TEST_ID] [--verbose]

Examples:
    python tests/run_tests.py                          # Run all tests
    python tests/run_tests.py --suite identity_suite   # Run identity tests only
    python tests/run_tests.py --test maven_identity_1  # Run specific test
    python tests/run_tests.py --verbose                # Show detailed output
"""

import json
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Any, Optional
import argparse


# Add maven2_fix to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Import Maven's orchestrator
# For now, we'll use a simple message-based API
# In the future, this will use the bus module
from brains.cognitive.memory_librarian.service.memory_librarian import service_api as memory_librarian_api


class TestHarness:
    """Regression test harness for Maven behavioral contracts."""

    def __init__(self, contracts_path: Path, report_dir: Path):
        self.contracts_path = contracts_path
        self.report_dir = report_dir
        self.contracts = self._load_contracts()
        self.results = []
        self.user_id = "test_user"

    def _load_contracts(self) -> Dict:
        """Load behavioral contracts from JSON file."""
        with open(self.contracts_path, 'r') as f:
            return json.load(f)

    def _reset_user_context(self):
        """Reset user context between tests."""
        # For now, use a timestamp-based user_id to ensure isolation
        self.user_id = f"test_user_{int(time.time() * 1000)}"

    def _send_to_maven(self, text: str) -> Dict[str, Any]:
        """
        Send input to Maven and get response.

        Args:
            text: User input text

        Returns:
            Dict with 'text', 'confidence', 'verdict', 'intent', etc.
        """
        try:
            # Call memory_librarian's RUN_PIPELINE (main orchestrator)
            result = memory_librarian_api({
                "op": "RUN_PIPELINE",
                "mid": f"test_{int(time.time() * 1000)}",
                "payload": {
                    "text": text,
                    "user_id": self.user_id,
                    "session_id": f"test_session_{self.user_id}",
                }
            })

            if not result.get("ok"):
                return {
                    "error": result.get("error", "Unknown error"),
                    "text": "",
                    "confidence": 0.0
                }

            payload = result.get("payload", {})
            return {
                "text": payload.get("final_answer", ""),
                "confidence": payload.get("confidence", 0.0),
                "verdict": payload.get("stage_8_validation", {}).get("verdict", ""),
                "intent": payload.get("stage_3_language", {}).get("intent", ""),
                "stored": not payload.get("stage_9_storage", {}).get("skipped", False),
                "mode": payload.get("stage_8_validation", {}).get("mode", ""),
            }
        except Exception as e:
            return {
                "error": str(e),
                "text": "",
                "confidence": 0.0
            }

    def _check_patterns(self, text: str, patterns: List[str], should_match: bool = True) -> tuple[bool, List[str]]:
        """
        Check if text matches (or doesn't match) expected patterns.

        Args:
            text: Response text to check
            patterns: List of regex patterns or substrings
            should_match: If True, patterns should match; if False, should not match

        Returns:
            (success, list of failures)
        """
        text_lower = text.lower()
        failures = []

        for pattern in patterns:
            # Try as substring first, then as regex
            if pattern.lower() in text_lower:
                matched = True
            else:
                try:
                    matched = bool(re.search(pattern, text, re.IGNORECASE))
                except re.error:
                    matched = False

            if should_match and not matched:
                failures.append(f"Expected pattern '{pattern}' not found in: {text}")
            elif not should_match and matched:
                failures.append(f"Unexpected pattern '{pattern}' found in: {text}")

        return len(failures) == 0, failures

    def run_test(self, suite_name: str, test: Dict[str, Any], verbose: bool = False) -> Dict[str, Any]:
        """
        Run a single test case.

        Args:
            suite_name: Name of the test suite
            test: Test specification dict
            verbose: If True, print detailed output

        Returns:
            Test result dict with pass/fail status and details
        """
        test_id = test.get("id", "unknown")
        description = test.get("description", "")

        if verbose:
            print(f"\n{'=' * 60}")
            print(f"Running: {suite_name}.{test_id}")
            if description:
                print(f"Description: {description}")
            print('=' * 60)

        # Reset context for test isolation
        self._reset_user_context()

        result = {
            "suite": suite_name,
            "test_id": test_id,
            "description": description,
            "passed": True,
            "failures": [],
            "responses": [],
            "duration_ms": 0
        }

        start_time = time.time()

        try:
            # Run setup inputs if any
            setup_inputs = test.get("setup", [])
            for setup_input in setup_inputs:
                response = self._send_to_maven(setup_input)
                if verbose:
                    print(f"Setup: '{setup_input}' → '{response.get('text', '')}'")

            # Run main test inputs
            inputs = test.get("inputs", [])
            for input_text in inputs:
                response = self._send_to_maven(input_text)
                result["responses"].append({
                    "input": input_text,
                    "output": response.get("text", ""),
                    "confidence": response.get("confidence", 0.0),
                    "verdict": response.get("verdict", ""),
                    "intent": response.get("intent", ""),
                    "error": response.get("error")
                })

                if verbose:
                    print(f"\nInput: '{input_text}'")
                    print(f"Output: '{response.get('text', '')}'")
                    print(f"Confidence: {response.get('confidence', 0.0):.2f}")
                    print(f"Verdict: {response.get('verdict', '')}")

                # Check for errors
                if response.get("error"):
                    result["passed"] = False
                    result["failures"].append(f"Error: {response['error']}")
                    continue

                # Check expected patterns
                if "expected_patterns" in test:
                    success, failures = self._check_patterns(
                        response.get("text", ""),
                        test["expected_patterns"],
                        should_match=True
                    )
                    if not success:
                        result["passed"] = False
                        result["failures"].extend(failures)

                # Check not expected patterns
                if "not_expected_patterns" in test:
                    success, failures = self._check_patterns(
                        response.get("text", ""),
                        test["not_expected_patterns"],
                        should_match=False
                    )
                    if not success:
                        result["passed"] = False
                        result["failures"].extend(failures)

                # Check confidence
                if "expected_confidence_min" in test:
                    min_conf = test["expected_confidence_min"]
                    actual_conf = response.get("confidence", 0.0)
                    if actual_conf < min_conf:
                        result["passed"] = False
                        result["failures"].append(
                            f"Confidence {actual_conf:.2f} below minimum {min_conf:.2f}"
                        )

                # Check exact match
                if "expected_exact" in test:
                    expected = str(test["expected_exact"])
                    actual = response.get("text", "").strip()
                    if actual != expected:
                        result["passed"] = False
                        result["failures"].append(
                            f"Expected exact '{expected}', got '{actual}'"
                        )

                # Check verdict
                if "verdict" in test:
                    expected_verdicts = test["verdict"]
                    if isinstance(expected_verdicts, str):
                        expected_verdicts = [expected_verdicts]
                    actual_verdict = response.get("verdict", "")
                    if actual_verdict not in expected_verdicts:
                        result["passed"] = False
                        result["failures"].append(
                            f"Expected verdict in {expected_verdicts}, got '{actual_verdict}'"
                        )

                # Check storage
                if "expected_storage" in test:
                    expected_stored = test["expected_storage"]
                    actual_stored = response.get("stored", False)
                    if actual_stored != expected_stored:
                        result["passed"] = False
                        result["failures"].append(
                            f"Expected storage={expected_stored}, got {actual_stored}"
                        )

        except Exception as e:
            result["passed"] = False
            result["failures"].append(f"Exception: {str(e)}")

        result["duration_ms"] = int((time.time() - start_time) * 1000)

        if verbose:
            print(f"\n{'PASS' if result['passed'] else 'FAIL'}")
            if result["failures"]:
                print("Failures:")
                for failure in result["failures"]:
                    print(f"  - {failure}")

        return result

    def run_suite(self, suite_name: str, verbose: bool = False) -> List[Dict[str, Any]]:
        """Run all tests in a suite."""
        suite = self.contracts["test_suites"].get(suite_name, {})
        tests = suite.get("tests", [])

        if verbose:
            print(f"\n{' ' * 20}Running suite: {suite_name}")
            print(f"Description: {suite.get('description', '')}")
            print(f"Tests: {len(tests)}\n")

        suite_results = []
        for test in tests:
            result = self.run_test(suite_name, test, verbose=verbose)
            suite_results.append(result)
            self.results.append(result)

        return suite_results

    def run_all(self, verbose: bool = False) -> None:
        """Run all test suites."""
        suites = self.contracts["test_suites"].keys()
        for suite_name in suites:
            self.run_suite(suite_name, verbose=verbose)

    def generate_report(self) -> Dict[str, Any]:
        """Generate summary report of test results."""
        total = len(self.results)
        passed = sum(1 for r in self.results if r["passed"])
        failed = total - passed

        # Group by suite
        suite_summary = {}
        for result in self.results:
            suite = result["suite"]
            if suite not in suite_summary:
                suite_summary[suite] = {"total": 0, "passed": 0, "failed": 0, "tests": []}
            suite_summary[suite]["total"] += 1
            if result["passed"]:
                suite_summary[suite]["passed"] += 1
            else:
                suite_summary[suite]["failed"] += 1
                suite_summary[suite]["tests"].append(result)

        report = {
            "timestamp": int(time.time()),
            "summary": {
                "total": total,
                "passed": passed,
                "failed": failed,
                "pass_rate": passed / total if total > 0 else 0.0
            },
            "suites": suite_summary,
            "all_results": self.results
        }

        return report

    def save_report(self, report: Dict[str, Any]) -> Path:
        """Save report to JSON file."""
        self.report_dir.mkdir(parents=True, exist_ok=True)
        timestamp = int(time.time())
        report_path = self.report_dir / f"test_report_{timestamp}.json"

        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)

        return report_path

    def print_summary(self, report: Dict[str, Any]) -> None:
        """Print human-readable summary to console."""
        summary = report["summary"]
        suites = report["suites"]

        print("\n" + "=" * 80)
        print(f"{' ' * 30}TEST SUMMARY")
        print("=" * 80)
        print(f"Total Tests:  {summary['total']}")
        print(f"Passed:       {summary['passed']} ({summary['pass_rate']*100:.1f}%)")
        print(f"Failed:       {summary['failed']}")
        print("=" * 80)

        for suite_name, suite_data in suites.items():
            status = "✓" if suite_data["failed"] == 0 else "✗"
            print(f"\n{status} {suite_name}: {suite_data['passed']}/{suite_data['total']} passed")

            if suite_data["failed"] > 0:
                for test in suite_data["tests"]:
                    print(f"  ✗ {test['test_id']}")
                    for failure in test["failures"]:
                        print(f"      - {failure}")

        print("\n" + "=" * 80)


def main():
    parser = argparse.ArgumentParser(description="Run Maven regression tests")
    parser.add_argument("--suite", help="Run specific test suite")
    parser.add_argument("--test", help="Run specific test ID")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    # Paths
    root = Path(__file__).resolve().parent.parent
    contracts_path = root / "brains" / "domain_banks" / "specs" / "maven_behavior_contracts.json"
    report_dir = root / "reports" / "tests"

    # Initialize harness
    harness = TestHarness(contracts_path, report_dir)

    # Run tests
    print("Maven Regression Test Harness")
    print(f"Contracts: {contracts_path}")
    print(f"Reports:   {report_dir}")

    if args.test:
        # Run specific test
        print(f"\nRunning test: {args.test}")
        found = False
        for suite_name, suite_data in harness.contracts["test_suites"].items():
            for test in suite_data.get("tests", []):
                if test.get("id") == args.test:
                    result = harness.run_test(suite_name, test, verbose=True)
                    harness.results.append(result)
                    found = True
                    break
        if not found:
            print(f"Error: Test '{args.test}' not found")
            sys.exit(1)

    elif args.suite:
        # Run specific suite
        print(f"\nRunning suite: {args.suite}")
        if args.suite not in harness.contracts["test_suites"]:
            print(f"Error: Suite '{args.suite}' not found")
            sys.exit(1)
        harness.run_suite(args.suite, verbose=args.verbose)

    else:
        # Run all tests
        harness.run_all(verbose=args.verbose)

    # Generate and save report
    report = harness.generate_report()
    report_path = harness.save_report(report)

    # Print summary
    harness.print_summary(report)
    print(f"\nDetailed report saved to: {report_path}")

    # Exit with appropriate code
    sys.exit(0 if report["summary"]["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
