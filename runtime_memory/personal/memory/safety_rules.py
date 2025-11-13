"""Helper for storing and retrieving safety rules.

The safety rules mechanism allows developers or governance modules to
persist and manage a list of simple rule patterns that the reasoning
brain can use to detect and filter obviously false or harmful
statements.  Each rule is a case‑insensitive string that should
appear verbatim (or as a substring) in a query; when matched, the
reasoning brain may downgrade confidence or return a corrective
response.  Rules are stored on disk in the reports directory as
``safety_rules.json``.

Functions:
    get_rules() -> List[str]: return the list of stored rules.
    add_rule(rule: str) -> bool: add a new rule if not present.
    clear_rules() -> bool: remove all stored rules.

The module tolerates file errors by catching exceptions and returning
defaults.  It uses simple JSON serialization for persistence.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

# Compute the path to the reports directory.  We ascend from this file's
# location up to the Maven project root and then into reports.
HERE = Path(__file__).resolve()
MAVEN_ROOT = HERE.parents[4]  # brains/personal/memory/safety_rules.py → maven_new/maven/
RULES_PATH = MAVEN_ROOT / "reports" / "safety_rules.json"


def _load() -> List[str]:
    """Load the list of safety rules from disk.  Returns an empty list on error."""
    try:
        if RULES_PATH.exists():
            with RULES_PATH.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, list):
                # Normalize to lower case strings
                return [str(r).strip().lower() for r in data if isinstance(r, str) and r.strip()]
    except Exception:
        pass
    return []


def _save(rules: List[str]) -> None:
    """Persist the given list of safety rules to disk."""
    try:
        RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
        with RULES_PATH.open("w", encoding="utf-8") as fh:
            json.dump(rules, fh, ensure_ascii=False, indent=2)
    except Exception:
        # Silently ignore errors; we don't want to break the pipeline
        pass


def get_rules() -> List[str]:
    """Return the current list of safety rule patterns.  Always returns a list."""
    return _load()


def add_rule(rule: str) -> bool:
    """Add a new rule pattern.  Returns True if added, False if already exists or invalid."""
    if not isinstance(rule, str) or not rule.strip():
        return False
    rule_norm = rule.strip().lower()
    rules = _load()
    if rule_norm in rules:
        return False
    rules.append(rule_norm)
    _save(rules)
    return True


def clear_rules() -> bool:
    """Remove all stored safety rules.  Returns True on success."""
    try:
        _save([])
        return True
    except Exception:
        return False