"""
Phase 7: Domain Bank Seeding Tests

This module tests the domain bank seeding functionality.

Test Coverage:
- Seed file schema validation
- Seeding engine operations (validate and apply)
- Idempotency guarantees
- Domain bank population
- Brain integration with domain lookup
- Governance rules enforcement
"""

import json
import sys
from pathlib import Path
import pytest

# Add paths for imports
MAVEN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MAVEN_ROOT / "brains" / "domain_banks" / "specs" / "data" / "seeds"))
sys.path.insert(0, str(MAVEN_ROOT / "brains" / "domain_banks"))

from seed_validator import validate_seeds, ValidationError
from seeding_engine import SeedingEngine, run_seeding
from domain_lookup import DomainLookup


# Test paths
SEEDS_DIR = MAVEN_ROOT / "brains" / "domain_banks" / "specs" / "data" / "seeds"
RUNTIME_DIR = Path("/home/user/maven/runtime_memory/domain_banks")


class TestPhase7DomainSeeding:
    """Test suite for Phase 7 domain seeding functionality."""

    def test_seed_files_valid_schema(self):
        """Test that all seed files conform to the schema."""
        try:
            report = validate_seeds(str(SEEDS_DIR))
            assert report["ok"], "Seed validation should pass"
            assert report["total_entries"] > 0, "Should have seed entries"
            assert len(report["errors"]) == 0, f"Should have no errors, got: {report['errors']}"
        except ValidationError as e:
            pytest.fail(f"Validation failed: {e}")

    def test_seeding_validate_only_ok(self):
        """Test that validate-only mode works correctly."""
        try:
            report = run_seeding(str(SEEDS_DIR), str(RUNTIME_DIR), validate_only=True)
            assert report["ok"], "Validation should succeed"
            assert report["mode"] == "validate_only", "Mode should be validate_only"
            assert report["total_entries"] > 0, "Should have entries to validate"
            assert len(report["banks"]) > 0, "Should have banks"

            # Verify no writing occurred
            for bank_name, bank_info in report["banks"].items():
                assert not bank_info["written"], f"Bank {bank_name} should not be written in validate mode"

        except Exception as e:
            pytest.fail(f"Validate-only test failed: {e}")

    def test_seeding_apply_idempotent(self):
        """Test that seeding is idempotent (same output when run multiple times)."""
        engine = SeedingEngine(str(SEEDS_DIR), str(RUNTIME_DIR))

        # Run seeding first time
        report1 = engine.run_seeding(validate_only=False)
        assert report1["ok"], "First seeding should succeed"

        # Collect file hashes
        files1 = {}
        for bank_name, bank_info in report1["banks"].items():
            if bank_info["written"]:
                storage_file = Path(bank_info["storage_file"])
                if storage_file.exists():
                    with open(storage_file, 'r') as f:
                        files1[bank_name] = f.read()

        # Run seeding second time
        report2 = engine.run_seeding(validate_only=False)
        assert report2["ok"], "Second seeding should succeed"

        # Collect file hashes again
        files2 = {}
        for bank_name, bank_info in report2["banks"].items():
            if bank_info["written"]:
                storage_file = Path(bank_info["storage_file"])
                if storage_file.exists():
                    with open(storage_file, 'r') as f:
                        files2[bank_name] = f.read()

        # Verify identical
        assert set(files1.keys()) == set(files2.keys()), "Same banks should be written"
        for bank_name in files1.keys():
            assert files1[bank_name] == files2[bank_name], \
                f"Bank {bank_name} content should be identical across runs"

    def test_banks_non_empty_after_seeding(self):
        """Test that domain banks are populated after seeding."""
        # Run seeding
        report = run_seeding(str(SEEDS_DIR), str(RUNTIME_DIR), validate_only=False)
        assert report["ok"], "Seeding should succeed"

        # Verify each bank has entries
        for bank_name, bank_info in report["banks"].items():
            assert bank_info["entries"] > 0, f"Bank {bank_name} should have entries"

            if bank_info["written"]:
                storage_file = Path(bank_info["storage_file"])
                assert storage_file.exists(), f"Storage file should exist for {bank_name}"

                # Verify JSONL content
                with open(storage_file, 'r') as f:
                    lines = [line.strip() for line in f if line.strip()]
                    assert len(lines) > 0, f"Storage file should have content for {bank_name}"

                    # Verify first line is valid JSON
                    try:
                        entry = json.loads(lines[0])
                        assert "id" in entry, "Entry should have ID"
                        assert "bank" in entry, "Entry should have bank"
                        assert "content" in entry, "Entry should have content"
                    except json.JSONDecodeError:
                        pytest.fail(f"Invalid JSON in {bank_name} storage file")

    def test_governance_rules_loaded(self):
        """Test that governance rules are properly loaded and accessible."""
        # Ensure seeds are applied
        run_seeding(str(SEEDS_DIR), str(RUNTIME_DIR), validate_only=False)

        # Use domain lookup to get governance rules
        lookup = DomainLookup(str(RUNTIME_DIR))
        rules = lookup.get_by_bank_and_kind("governance_rules", "rule")

        assert len(rules) > 0, "Should have governance rules"

        # Check for specific critical rules
        rule_ids = {r.get("id") for r in rules}
        assert "governance_rules:rule:no_randomness" in rule_ids, \
            "Should have no_randomness rule"
        assert "governance_rules:rule:python_only" in rule_ids, \
            "Should have python_only rule"

        # Verify rule structure
        no_random_rule = lookup.get_by_id("governance_rules:rule:no_randomness")
        assert no_random_rule is not None, "No randomness rule should exist"
        assert "deterministic" in no_random_rule.get("content", {}).get("tags", []), \
            "Rule should be tagged with deterministic"

    def test_coder_brain_uses_coding_patterns(self):
        """Test that coder_brain can access coding patterns from domain bank."""
        # Ensure seeds are applied
        run_seeding(str(SEEDS_DIR), str(RUNTIME_DIR), validate_only=False)

        # Import coder brain
        sys.path.insert(0, str(MAVEN_ROOT / "brains" / "cognitive" / "coder" / "service"))
        try:
            import coder_brain

            # Test that _get_coding_patterns function exists and works
            if hasattr(coder_brain, '_get_coding_patterns'):
                patterns = coder_brain._get_coding_patterns()
                assert isinstance(patterns, dict), "Should return a dict of patterns"

                # If patterns are available, verify structure
                if len(patterns) > 0:
                    # Check for specific patterns
                    assert any("service_api" in pid for pid in patterns.keys()), \
                        "Should have service_api related patterns"

        except ImportError as e:
            pytest.skip(f"Could not import coder_brain: {e}")

    def test_planner_uses_planning_patterns(self):
        """Test that planner_brain can access planning patterns from domain bank."""
        # Ensure seeds are applied
        run_seeding(str(SEEDS_DIR), str(RUNTIME_DIR), validate_only=False)

        # Import planner brain
        sys.path.insert(0, str(MAVEN_ROOT / "brains" / "cognitive" / "planner" / "service"))
        try:
            import planner_brain

            # Test that _get_planning_patterns function exists and works
            if hasattr(planner_brain, '_get_planning_patterns'):
                patterns = planner_brain._get_planning_patterns()
                assert isinstance(patterns, dict), "Should return a dict of patterns"

                # If patterns are available, verify structure
                if len(patterns) > 0:
                    # Check for specific patterns
                    pattern_ids = list(patterns.keys())
                    assert any("strategy" in pid or "constraint" in pid for pid in pattern_ids), \
                        "Should have strategy or constraint patterns"

        except ImportError as e:
            pytest.skip(f"Could not import planner_brain: {e}")

    def test_domain_lookup_by_id(self):
        """Test domain lookup by ID."""
        run_seeding(str(SEEDS_DIR), str(RUNTIME_DIR), validate_only=False)

        lookup = DomainLookup(str(RUNTIME_DIR))

        # Test getting a specific entry
        entry = lookup.get_by_id("governance_rules:rule:no_randomness")
        assert entry is not None, "Should find entry by ID"
        assert entry["id"] == "governance_rules:rule:no_randomness"
        assert entry["bank"] == "governance_rules"

    def test_domain_lookup_by_tag(self):
        """Test domain lookup by tag."""
        run_seeding(str(SEEDS_DIR), str(RUNTIME_DIR), validate_only=False)

        lookup = DomainLookup(str(RUNTIME_DIR))

        # Test getting entries by tag
        entries = lookup.get_by_tag("determinism")
        assert len(entries) > 0, "Should find entries tagged with 'determinism'"

        # Verify all returned entries have the tag
        for entry in entries:
            tags = entry.get("content", {}).get("tags", [])
            assert "determinism" in tags, f"Entry {entry.get('id')} should have 'determinism' tag"

    def test_domain_lookup_deterministic_ordering(self):
        """Test that domain lookup returns results in deterministic order."""
        run_seeding(str(SEEDS_DIR), str(RUNTIME_DIR), validate_only=False)

        lookup1 = DomainLookup(str(RUNTIME_DIR))
        lookup2 = DomainLookup(str(RUNTIME_DIR))

        # Get entries multiple times
        entries1_run1 = lookup1.get_by_tag("determinism")
        entries1_run2 = lookup1.get_by_tag("determinism")

        entries2_run1 = lookup2.get_by_tag("determinism")

        # Verify same order
        ids1_run1 = [e.get("id") for e in entries1_run1]
        ids1_run2 = [e.get("id") for e in entries1_run2]
        ids2_run1 = [e.get("id") for e in entries2_run1]

        assert ids1_run1 == ids1_run2, "Same lookup should return same order"
        assert ids1_run1 == ids2_run1, "Different lookups should return same order"

    def test_council_brain_seeding_operations(self):
        """Test that council_brain has seeding operations wired."""
        sys.path.insert(0, str(MAVEN_ROOT / "brains" / "governance" / "council" / "service"))

        try:
            import council_brain

            # Test DOMAIN_BANK_SEED_VALIDATE operation
            result = council_brain.service_api({
                "op": "DOMAIN_BANK_SEED_VALIDATE",
                "payload": {}
            })

            assert result.get("ok"), "DOMAIN_BANK_SEED_VALIDATE should succeed"
            payload = result.get("payload", {})
            assert "mode" in payload, "Should have mode field"
            assert payload["mode"] == "validate_only", "Mode should be validate_only"

        except ImportError as e:
            pytest.skip(f"Could not import council_brain: {e}")


def run_tests():
    """Run all Phase 7 tests."""
    print("=" * 70)
    print("  Phase 7: Domain Seeding Tests")
    print("=" * 70)
    print()

    # Use pytest to run tests
    pytest.main([__file__, "-v", "--tb=short"])


if __name__ == "__main__":
    run_tests()
