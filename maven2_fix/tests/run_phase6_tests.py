"""
Phase 6 Brain Wiring Tests - Standalone Runner

This runs all Phase 6 tests without requiring pytest.
"""

import json
import sys
import traceback
from pathlib import Path
from typing import Dict, Any, List

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


class TestRunner:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.failures = []

    def run_test(self, name, func):
        """Run a single test function."""
        try:
            print(f"\n{'='*70}")
            print(f"TEST: {name}")
            print(f"{'='*70}")
            func()
            self.passed += 1
            print(f"✓ PASSED")
        except AssertionError as e:
            self.failed += 1
            self.failures.append((name, str(e)))
            print(f"✗ FAILED: {e}")
        except Exception as e:
            self.failed += 1
            self.failures.append((name, f"ERROR: {e}"))
            print(f"✗ ERROR: {e}")
            traceback.print_exc()

    def summary(self):
        """Print test summary."""
        print(f"\n\n{'='*70}")
        print(f"TEST SUMMARY")
        print(f"{'='*70}")
        print(f"Passed:  {self.passed}")
        print(f"Failed:  {self.failed}")
        print(f"Skipped: {self.skipped}")
        print(f"Total:   {self.passed + self.failed + self.skipped}")

        if self.failures:
            print(f"\nFAILURES:")
            for name, error in self.failures:
                print(f"\n  {name}:")
                print(f"    {error}")

        print(f"{'='*70}")

        return self.failed == 0


# =============================================================================
# Test 1: Brain Inventory Regression
# =============================================================================

def test_brain_inventory_matches_filesystem():
    """Verify that brain_inventory_phase6.json matches actual brain files."""
    inventory_path = PROJECT_ROOT / "brains" / "domain_banks" / "specs" / "brain_inventory_phase6.json"
    assert inventory_path.exists(), "brain_inventory_phase6.json must exist"

    with open(inventory_path, 'r') as f:
        inventory = json.load(f)

    # Find all actual brain files
    brains_root = PROJECT_ROOT / "brains"
    actual_brains = set()

    # Cognitive brains
    for brain_file in brains_root.glob("cognitive/**/service/*_brain.py"):
        actual_brains.add(brain_file.stem)
    # Add special files
    for special_file in brains_root.glob("cognitive/**/service/memory_librarian.py"):
        actual_brains.add(special_file.stem)
    for special_file in brains_root.glob("cognitive/**/service/thought_synthesizer.py"):
        actual_brains.add(special_file.stem)

    # Personal brains
    for brain_file in brains_root.glob("personal/**/service/*_brain.py"):
        actual_brains.add(brain_file.stem)

    # Governance brains
    for brain_file in brains_root.glob("governance/**/service/*_brain.py"):
        actual_brains.add(brain_file.stem)

    # Compare
    inventory_brains = set(inventory.keys())

    missing_from_inventory = actual_brains - inventory_brains
    phantom_in_inventory = inventory_brains - actual_brains

    assert not missing_from_inventory, f"Brains missing from inventory: {missing_from_inventory}"
    assert not phantom_in_inventory, f"Phantom brains in inventory: {phantom_in_inventory}"

    print(f"✓ Brain inventory matches filesystem ({len(inventory_brains)} brains)")


def test_brain_inventory_structure():
    """Verify each brain in inventory has required fields."""
    inventory_path = PROJECT_ROOT / "brains" / "domain_banks" / "specs" / "brain_inventory_phase6.json"

    with open(inventory_path, 'r') as f:
        inventory = json.load(f)

    required_fields = {"module", "role", "status", "ops"}
    valid_roles = {"core", "specialist", "diagnostic"}
    valid_statuses = {"implemented", "partial", "stub"}

    for brain_name, brain_info in inventory.items():
        missing_fields = required_fields - set(brain_info.keys())
        assert not missing_fields, f"{brain_name} missing fields: {missing_fields}"

        assert brain_info["role"] in valid_roles, f"{brain_name} has invalid role: {brain_info['role']}"
        assert brain_info["status"] in valid_statuses, f"{brain_name} has invalid status: {brain_info['status']}"
        assert isinstance(brain_info["ops"], list), f"{brain_name} ops must be a list"

    print(f"✓ All {len(inventory)} brains have valid structure")


def test_brain_contracts_exist():
    """Verify brain contracts file exists and is well-formed."""
    contracts_path = PROJECT_ROOT / "brains" / "domain_banks" / "specs" / "brain_contracts_phase6.json"
    assert contracts_path.exists(), "brain_contracts_phase6.json must exist"

    with open(contracts_path, 'r') as f:
        contracts = json.load(f)

    assert len(contracts) > 0, "Contracts must not be empty"
    print(f"✓ Brain contracts loaded ({len(contracts)} brains)")


def test_contract_structure():
    """Verify each contract has valid structure."""
    contracts_path = PROJECT_ROOT / "brains" / "domain_banks" / "specs" / "brain_contracts_phase6.json"

    with open(contracts_path, 'r') as f:
        contracts = json.load(f)

    for brain_name, brain_ops in contracts.items():
        for op_name, op_contract in brain_ops.items():
            assert "input" in op_contract, f"{brain_name}.{op_name} missing input spec"
            assert "output" in op_contract, f"{brain_name}.{op_name} missing output spec"
            assert "deterministic" in op_contract, f"{brain_name}.{op_name} missing deterministic flag"

            assert isinstance(op_contract["deterministic"], bool), \
                f"{brain_name}.{op_name} deterministic must be bool"

    print(f"✓ All contracts have valid structure")


def test_core_brains_have_contracts():
    """Verify all core brains have contracts defined."""
    inventory_path = PROJECT_ROOT / "brains" / "domain_banks" / "specs" / "brain_inventory_phase6.json"
    contracts_path = PROJECT_ROOT / "brains" / "domain_banks" / "specs" / "brain_contracts_phase6.json"

    with open(inventory_path, 'r') as f:
        inventory = json.load(f)
    with open(contracts_path, 'r') as f:
        contracts = json.load(f)

    core_brains = [name for name, info in inventory.items() if info["role"] == "core"]

    missing_contracts = []
    for brain_name in core_brains:
        if brain_name not in contracts:
            missing_contracts.append(brain_name)

    assert not missing_contracts, f"Core brains missing contracts: {missing_contracts}"
    print(f"✓ All {len(core_brains)} core brains have contracts")


def test_core_brain_imports():
    """Verify all core brains can be imported."""
    inventory_path = PROJECT_ROOT / "brains" / "domain_banks" / "specs" / "brain_inventory_phase6.json"

    with open(inventory_path, 'r') as f:
        inventory = json.load(f)

    core_brains = {name: info for name, info in inventory.items() if info["role"] == "core"}

    import_failures = []

    for brain_name, brain_info in core_brains.items():
        module_path = brain_info["module"]
        module_name = module_path.replace('/', '.').replace('.py', '')

        try:
            __import__(module_name)
        except Exception as e:
            import_failures.append((brain_name, str(e)))

    assert not import_failures, f"Failed to import core brains: {import_failures}"
    print(f"✓ All {len(core_brains)} core brains can be imported")


def test_core_brains_have_service_api():
    """Verify all core brains expose service_api function."""
    inventory_path = PROJECT_ROOT / "brains" / "domain_banks" / "specs" / "brain_inventory_phase6.json"

    with open(inventory_path, 'r') as f:
        inventory = json.load(f)

    core_brains = {name: info for name, info in inventory.items() if info["role"] == "core"}

    missing_service_api = []

    for brain_name, brain_info in core_brains.items():
        module_path = brain_info["module"]
        module_name = module_path.replace('/', '.').replace('.py', '')

        try:
            mod = __import__(module_name, fromlist=['service_api'])
            if not hasattr(mod, 'service_api'):
                missing_service_api.append(brain_name)
        except Exception:
            continue

    assert not missing_service_api, f"Core brains missing service_api: {missing_service_api}"
    print(f"✓ All core brains expose service_api")


def test_core_brains_respond_to_health():
    """Verify all core brains respond to HEALTH operation."""
    inventory_path = PROJECT_ROOT / "brains" / "domain_banks" / "specs" / "brain_inventory_phase6.json"

    with open(inventory_path, 'r') as f:
        inventory = json.load(f)

    core_brains = {name: info for name, info in inventory.items() if info["role"] == "core"}

    health_failures = []

    for brain_name, brain_info in core_brains.items():
        if "HEALTH" not in brain_info["ops"]:
            continue

        module_path = brain_info["module"]
        module_name = module_path.replace('/', '.').replace('.py', '')

        try:
            mod = __import__(module_name, fromlist=['service_api'])
            service_api = getattr(mod, 'service_api')

            resp = service_api({"op": "HEALTH"})

            if not isinstance(resp, dict):
                health_failures.append((brain_name, "response not a dict"))
            elif not resp.get("ok"):
                health_failures.append((brain_name, f"not ok: {resp}"))
        except Exception as e:
            health_failures.append((brain_name, str(e)))

    assert not health_failures, f"HEALTH check failures: {health_failures}"
    print(f"✓ All core brains with HEALTH op respond correctly")


def test_specialist_triggers_documented():
    """Verify specialist triggers are documented."""
    triggers_path = PROJECT_ROOT / "brains" / "domain_banks" / "specs" / "specialist_brain_triggers_phase6.json"
    assert triggers_path.exists(), "specialist_brain_triggers_phase6.json must exist"

    with open(triggers_path, 'r') as f:
        triggers = json.load(f)

    assert "specialist_triggers" in triggers, "Must have specialist_triggers section"
    specialist_triggers = triggers["specialist_triggers"]

    inventory_path = PROJECT_ROOT / "brains" / "domain_banks" / "specs" / "brain_inventory_phase6.json"
    with open(inventory_path, 'r') as f:
        inventory = json.load(f)

    specialist_brains = [name for name, info in inventory.items() if info["role"] == "specialist"]

    documented = set(specialist_triggers.keys())
    expected = set(specialist_brains)

    invalid_documented = documented - expected

    assert not invalid_documented, f"Invalid specialists documented: {invalid_documented}"
    print(f"✓ Specialist triggers documented for {len(documented)} specialists")


def test_core_brains_all_implemented():
    """Verify all core brains are marked as 'implemented'."""
    inventory_path = PROJECT_ROOT / "brains" / "domain_banks" / "specs" / "brain_inventory_phase6.json"

    with open(inventory_path, 'r') as f:
        inventory = json.load(f)

    core_brains = {name: info for name, info in inventory.items() if info["role"] == "core"}

    not_implemented = []
    for brain_name, brain_info in core_brains.items():
        if brain_info["status"] != "implemented":
            not_implemented.append((brain_name, brain_info["status"]))

    assert not not_implemented, f"Core brains not fully implemented: {not_implemented}"
    print(f"✓ All {len(core_brains)} core brains are fully implemented")


def test_phase6_summary():
    """Print a summary of Phase 6 implementation status."""
    inventory_path = PROJECT_ROOT / "brains" / "domain_banks" / "specs" / "brain_inventory_phase6.json"
    contracts_path = PROJECT_ROOT / "brains" / "domain_banks" / "specs" / "brain_contracts_phase6.json"
    triggers_path = PROJECT_ROOT / "brains" / "domain_banks" / "specs" / "specialist_brain_triggers_phase6.json"

    with open(inventory_path, 'r') as f:
        inventory = json.load(f)
    with open(contracts_path, 'r') as f:
        contracts = json.load(f)
    with open(triggers_path, 'r') as f:
        triggers = json.load(f)

    by_role = {}
    for brain_info in inventory.values():
        role = brain_info["role"]
        by_role[role] = by_role.get(role, 0) + 1

    by_status = {}
    for brain_info in inventory.values():
        status = brain_info["status"]
        by_status[status] = by_status.get(status, 0) + 1

    print("\n" + "="*70)
    print("PHASE 6 SUMMARY")
    print("="*70)
    print(f"Total brains: {len(inventory)}")
    print(f"\nBy role:")
    for role, count in sorted(by_role.items()):
        print(f"  {role:15s}: {count:3d}")
    print(f"\nBy status:")
    for status, count in sorted(by_status.items()):
        print(f"  {status:15s}: {count:3d}")
    print(f"\nContracts defined: {len(contracts)}")
    print(f"Specialist triggers: {len(triggers['specialist_triggers'])}")
    print("="*70)


def main():
    """Run all Phase 6 tests."""
    runner = TestRunner()

    # Run all tests
    runner.run_test("test_brain_inventory_matches_filesystem", test_brain_inventory_matches_filesystem)
    runner.run_test("test_brain_inventory_structure", test_brain_inventory_structure)
    runner.run_test("test_brain_contracts_exist", test_brain_contracts_exist)
    runner.run_test("test_contract_structure", test_contract_structure)
    runner.run_test("test_core_brains_have_contracts", test_core_brains_have_contracts)
    runner.run_test("test_core_brain_imports", test_core_brain_imports)
    runner.run_test("test_core_brains_have_service_api", test_core_brains_have_service_api)
    runner.run_test("test_core_brains_respond_to_health", test_core_brains_respond_to_health)
    runner.run_test("test_specialist_triggers_documented", test_specialist_triggers_documented)
    runner.run_test("test_core_brains_all_implemented", test_core_brains_all_implemented)
    runner.run_test("test_phase6_summary", test_phase6_summary)

    # Print summary
    success = runner.summary()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
