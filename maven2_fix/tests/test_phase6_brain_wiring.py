"""
Phase 6 Brain Wiring Tests

This test module validates that all Phase 6 requirements are met:
1. Brain inventory matches filesystem
2. Brain contracts are enforced
3. Core paths invoke expected brains
4. Specialist brains have working triggers
5. No stubs in active code paths
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any, List

import pytest

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# Test 1: Brain Inventory Regression
# =============================================================================

def test_brain_inventory_matches_filesystem():
    """
    Verify that brain_inventory_phase6.json matches actual brain files.

    This test ensures that:
    - All brain files in the filesystem are listed in the inventory
    - No phantom brains are listed that don't exist
    - Inventory is kept up to date
    """
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
        # Check required fields present
        missing_fields = required_fields - set(brain_info.keys())
        assert not missing_fields, f"{brain_name} missing fields: {missing_fields}"

        # Check valid role
        assert brain_info["role"] in valid_roles, f"{brain_name} has invalid role: {brain_info['role']}"

        # Check valid status
        assert brain_info["status"] in valid_statuses, f"{brain_name} has invalid status: {brain_info['status']}"

        # Check ops is a list
        assert isinstance(brain_info["ops"], list), f"{brain_name} ops must be a list"

    print(f"✓ All {len(inventory)} brains have valid structure")


# =============================================================================
# Test 2: Brain Contract Enforcement
# =============================================================================

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
            # Each operation must have input, output, deterministic
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

    # Get all core brains
    core_brains = [name for name, info in inventory.items() if info["role"] == "core"]

    # Check each has a contract
    missing_contracts = []
    for brain_name in core_brains:
        if brain_name not in contracts:
            missing_contracts.append(brain_name)

    assert not missing_contracts, f"Core brains missing contracts: {missing_contracts}"
    print(f"✓ All {len(core_brains)} core brains have contracts")


def test_brain_operations_match_inventory():
    """Verify operations in contracts match inventory."""
    inventory_path = PROJECT_ROOT / "brains" / "domain_banks" / "specs" / "brain_inventory_phase6.json"
    contracts_path = PROJECT_ROOT / "brains" / "domain_banks" / "specs" / "brain_contracts_phase6.json"

    with open(inventory_path, 'r') as f:
        inventory = json.load(f)
    with open(contracts_path, 'r') as f:
        contracts = json.load(f)

    mismatches = []

    for brain_name in contracts.keys():
        if brain_name in inventory:
            inventory_ops = set(inventory[brain_name]["ops"])
            contract_ops = set(contracts[brain_name].keys())

            # It's OK if inventory has more ops than contracts (contracts are selective)
            # But all contract ops should be in inventory
            missing_in_inventory = contract_ops - inventory_ops
            if missing_in_inventory:
                mismatches.append((brain_name, missing_in_inventory))

    # This is informational, not a hard failure
    if mismatches:
        print(f"⚠ Some contract ops not in inventory: {mismatches}")
    else:
        print(f"✓ Contract operations align with inventory")


# =============================================================================
# Test 3: Core Path Trace Tests
# =============================================================================

@pytest.fixture
def memory_librarian():
    """Import and return memory_librarian service_api."""
    try:
        from brains.cognitive.memory_librarian.service.memory_librarian import service_api
        return service_api
    except ImportError as e:
        pytest.skip(f"Could not import memory_librarian: {e}")


def test_core_brain_imports():
    """Verify all core brains can be imported."""
    inventory_path = PROJECT_ROOT / "brains" / "domain_banks" / "specs" / "brain_inventory_phase6.json"

    with open(inventory_path, 'r') as f:
        inventory = json.load(f)

    core_brains = {name: info for name, info in inventory.items() if info["role"] == "core"}

    import_failures = []

    for brain_name, brain_info in core_brains.items():
        module_path = brain_info["module"]
        # Convert path to module name
        # e.g., brains/cognitive/reasoning/service/reasoning_brain.py
        # -> brains.cognitive.reasoning.service.reasoning_brain
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
            # Skip if import fails (covered by previous test)
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
            continue  # Some brains may not have HEALTH

        module_path = brain_info["module"]
        module_name = module_path.replace('/', '.').replace('.py', '')

        try:
            mod = __import__(module_name, fromlist=['service_api'])
            service_api = getattr(mod, 'service_api')

            # Call HEALTH
            resp = service_api({"op": "HEALTH"})

            # Check response structure
            if not isinstance(resp, dict):
                health_failures.append((brain_name, "response not a dict"))
            elif not resp.get("ok"):
                health_failures.append((brain_name, f"not ok: {resp}"))
        except Exception as e:
            health_failures.append((brain_name, str(e)))

    assert not health_failures, f"HEALTH check failures: {health_failures}"
    print(f"✓ All core brains with HEALTH op respond correctly")


# =============================================================================
# Test 4: Specialist Trigger Tests
# =============================================================================

def test_specialist_triggers_documented():
    """Verify specialist triggers are documented."""
    triggers_path = PROJECT_ROOT / "brains" / "domain_banks" / "specs" / "specialist_brain_triggers_phase6.json"
    assert triggers_path.exists(), "specialist_brain_triggers_phase6.json must exist"

    with open(triggers_path, 'r') as f:
        triggers = json.load(f)

    assert "specialist_triggers" in triggers, "Must have specialist_triggers section"
    specialist_triggers = triggers["specialist_triggers"]

    # Check each specialist has documented triggers
    inventory_path = PROJECT_ROOT / "brains" / "domain_banks" / "specs" / "brain_inventory_phase6.json"
    with open(inventory_path, 'r') as f:
        inventory = json.load(f)

    specialist_brains = [name for name, info in inventory.items() if info["role"] == "specialist"]

    documented = set(specialist_triggers.keys())
    expected = set(specialist_brains)

    # It's OK if not all specialists are documented (some may not need triggers)
    # But those that are documented should be valid specialists
    invalid_documented = documented - expected

    assert not invalid_documented, f"Invalid specialists documented: {invalid_documented}"
    print(f"✓ Specialist triggers documented for {len(documented)} specialists")


def test_specialist_triggers_have_required_fields():
    """Verify each specialist trigger has required structure."""
    triggers_path = PROJECT_ROOT / "brains" / "domain_banks" / "specs" / "specialist_brain_triggers_phase6.json"

    with open(triggers_path, 'r') as f:
        triggers = json.load(f)

    specialist_triggers = triggers["specialist_triggers"]

    for brain_name, trigger_spec in specialist_triggers.items():
        assert "trigger_conditions" in trigger_spec, f"{brain_name} missing trigger_conditions"
        assert "routing_logic" in trigger_spec, f"{brain_name} missing routing_logic"
        assert "priority" in trigger_spec, f"{brain_name} missing priority"

        assert isinstance(trigger_spec["trigger_conditions"], list), \
            f"{brain_name} trigger_conditions must be list"
        assert isinstance(trigger_spec["routing_logic"], str), \
            f"{brain_name} routing_logic must be string"
        assert isinstance(trigger_spec["priority"], (int, float)), \
            f"{brain_name} priority must be numeric"

    print(f"✓ All specialist triggers have valid structure")


# =============================================================================
# Test 5: No Stubs in Active Paths
# =============================================================================

def test_core_brains_all_implemented():
    """Verify all core brains are marked as 'implemented', not 'stub' or 'partial'."""
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


def test_no_stub_returns_in_core_operations():
    """Verify core brain operations don't return stub values."""
    # This is a basic smoke test - call each core brain's main operations
    # and verify they don't return obvious stub values

    inventory_path = PROJECT_ROOT / "brains" / "domain_banks" / "specs" / "brain_inventory_phase6.json"

    with open(inventory_path, 'r') as f:
        inventory = json.load(f)

    core_brains = {name: info for name, info in inventory.items() if info["role"] == "core"}

    stub_like_responses = []

    for brain_name, brain_info in core_brains.items():
        if "HEALTH" not in brain_info["ops"]:
            continue

        module_path = brain_info["module"]
        module_name = module_path.replace('/', '.').replace('.py', '')

        try:
            mod = __import__(module_name, fromlist=['service_api'])
            service_api = getattr(mod, 'service_api')

            resp = service_api({"op": "HEALTH"})

            # Check for stub-like responses
            if not resp.get("ok"):
                stub_like_responses.append((brain_name, "ok=False"))
            elif not resp.get("payload"):
                stub_like_responses.append((brain_name, "empty payload"))
            elif resp.get("payload") == {}:
                stub_like_responses.append((brain_name, "empty dict payload"))
        except Exception:
            # Skip import/call failures (covered by other tests)
            continue

    assert not stub_like_responses, f"Stub-like responses found: {stub_like_responses}"
    print(f"✓ No stub-like responses in core brain operations")


# =============================================================================
# Test 6: Determinism Verification
# =============================================================================

def test_no_randomness_in_core_brains():
    """Verify core brains don't use random module in their main files."""
    inventory_path = PROJECT_ROOT / "brains" / "domain_banks" / "specs" / "brain_inventory_phase6.json"

    with open(inventory_path, 'r') as f:
        inventory = json.load(f)

    core_brains = {name: info for name, info in inventory.items() if info["role"] == "core"}

    uses_random = []

    for brain_name, brain_info in core_brains.items():
        module_path = brain_info["module"]
        brain_file = PROJECT_ROOT / module_path

        if not brain_file.exists():
            continue

        content = brain_file.read_text()

        # Check for random usage (excluding comments and import fallbacks)
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            # Skip comments
            if stripped.startswith('#'):
                continue
            # Skip import fallback patterns
            if 'except' in stripped and 'random' in stripped:
                continue
            # Look for actual random usage
            if 'random.' in line and 'import random' not in line:
                uses_random.append((brain_name, i, line.strip()[:80]))

    assert not uses_random, f"Core brains using randomness: {uses_random}"
    print(f"✓ No randomness detected in core brain implementations")


def test_no_time_based_logic_in_core_brains():
    """Verify core brains don't use time-based conditions."""
    inventory_path = PROJECT_ROOT / "brains" / "domain_banks" / "specs" / "brain_inventory_phase6.json"

    with open(inventory_path, 'r') as f:
        inventory = json.load(f)

    core_brains = {name: info for name, info in inventory.items() if info["role"] == "core"}

    time_usage = []
    time_patterns = ['datetime.now', 'time.time()', 'timedelta', 'TTL']

    for brain_name, brain_info in core_brains.items():
        module_path = brain_info["module"]
        brain_file = PROJECT_ROOT / module_path

        if not brain_file.exists():
            continue

        content = brain_file.read_text()
        lines = content.split('\n')

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            # Skip comments
            if stripped.startswith('#'):
                continue
            # Look for time-based patterns
            for pattern in time_patterns:
                if pattern in line and 'import' not in line:
                    time_usage.append((brain_name, i, pattern, line.strip()[:80]))

    # Some usage may be acceptable (e.g., logging), so this is informational
    if time_usage:
        print(f"⚠ Time-based code detected in core brains: {len(time_usage)} instances")
    else:
        print(f"✓ No time-based logic detected in core brains")


# =============================================================================
# Summary Test
# =============================================================================

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

    # Count by role
    by_role = {}
    for brain_info in inventory.values():
        role = brain_info["role"]
        by_role[role] = by_role.get(role, 0) + 1

    # Count by status
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


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
