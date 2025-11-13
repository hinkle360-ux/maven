"""Knowledge Graph Utilities for Maven
======================================

This module implements a very simple in‑memory triple store backed by a
JSON file.  Each fact consists of a subject, a relation and an object
(S, R, O).  Facts are stored persistently in a ``knowledge_graph.json``
file under the ``reports`` directory relative to the Maven project
root.  Functions are provided to add new facts, query existing
facts, and list the most recent entries.  The module is intentionally
minimal to demonstrate how a semantic memory might be integrated into
Maven without external dependencies.

Functions:

  add_fact(subject: str, relation: str, obj: str) -> None
      Append a new fact triple to the persistent knowledge graph.  If
      the exact triple already exists, it will not be duplicated.

  query_fact(subject: str, relation: str) -> str | None
      Return the object for the first matching fact (subject, relation)
      if any.  Returns ``None`` when no fact matches.

  list_facts(limit: int = 10) -> list[dict]
      Return a list of the most recent fact triples up to ``limit``.

The functions in this module are designed to be silent on errors: any
exceptions (e.g. file permission issues) are swallowed to avoid
impacting the main pipeline.  The knowledge graph is a simple list and
does not support advanced reasoning or inference.  It is meant as a
starting point for a more comprehensive semantic memory in future
versions of Maven.
"""

from __future__ import annotations

from pathlib import Path
import json
from typing import List, Dict, Optional

# Compute the project root.  This file lives at
# brains/personal/memory/knowledge_graph.py so the Maven root is
# four levels up.
HERE = Path(__file__).resolve()
MAVEN_ROOT = HERE.parents[3]

# Path to the persistent knowledge graph file
KG_PATH = MAVEN_ROOT / "reports" / "knowledge_graph.json"


def _load_kg() -> List[Dict[str, str]]:
    """Load the knowledge graph from disk.

    Returns a list of triples.  If the file cannot be read, an empty
    list is returned.
    """
    try:
        if not KG_PATH.exists():
            return []
        with KG_PATH.open("r", encoding="utf-8") as fh:
            try:
                data = json.load(fh) or []
            except Exception:
                return []
        # Ensure each entry is a dict with subject, relation, object keys
        out: List[Dict[str, str]] = []
        for rec in data:
            if not isinstance(rec, dict):
                continue
            s = str(rec.get("subject", "")).strip()
            r = str(rec.get("relation", "")).strip()
            o = str(rec.get("object", "")).strip()
            if s and r and o:
                out.append({"subject": s, "relation": r, "object": o})
        return out
    except Exception:
        return []


def _save_kg(facts: List[Dict[str, str]]) -> None:
    """Write the knowledge graph back to disk.

    Errors are ignored silently to avoid impacting callers.
    """
    try:
        KG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with KG_PATH.open("w", encoding="utf-8") as fh:
            json.dump(facts, fh)
    except Exception:
        return


def add_fact(subject: str, relation: str, obj: str) -> None:
    """Append a new fact to the knowledge graph.

    The triple is added only if it is well‑formed (nonempty strings) and
    does not already exist exactly.  Duplicate facts are not stored.

    Args:
        subject: The fact subject (e.g. "Paris").
        relation: The relation (e.g. "is capital of").
        obj: The object (e.g. "France").
    """
    try:
        s = str(subject or "").strip()
        r = str(relation or "").strip()
        o = str(obj or "").strip()
        if not (s and r and o):
            return
        kg = _load_kg()
        # Check for duplicate
        for rec in kg:
            if rec["subject"].lower() == s.lower() and rec["relation"].lower() == r.lower() and rec["object"].lower() == o.lower():
                return
        kg.append({"subject": s, "relation": r, "object": o})
        _save_kg(kg)
    except Exception:
        return


def query_fact(subject: str, relation: str) -> Optional[str]:
    """Return the object associated with a (subject, relation) pair.

    Matching is case‑insensitive on subject and relation.  If multiple
    facts match, the first match is returned.  If no match is found,
    None is returned.

    Args:
        subject: The subject to look up.
        relation: The relation to look up.

    Returns:
        The object string if found; otherwise None.
    """
    try:
        s = str(subject or "").strip().lower()
        r = str(relation or "").strip().lower()
        if not (s and r):
            return None
        for rec in _load_kg():
            if rec["subject"].lower() == s and rec["relation"].lower() == r:
                return rec["object"]
        return None
    except Exception:
        return None


def list_facts(limit: int = 10) -> List[Dict[str, str]]:
    """
    Return a list of the most recent fact triples.

    If ``limit`` is positive, the function returns at most the last
    ``limit`` entries from the knowledge graph.  If ``limit`` is zero or
    negative, or if it exceeds the number of stored facts, all facts are
    returned.  Results are ordered by insertion (oldest first).

    Args:
        limit: The maximum number of facts to return.  Defaults to 10.

    Returns:
        A list of fact dictionaries sorted by insertion order.  When
        ``limit`` is non‑positive, the full list is returned.  If an
        error occurs, an empty list is returned.
    """
    try:
        kg = _load_kg()
        # If limit is <= 0 or greater than the number of facts, return all facts
        if not isinstance(limit, int):
            # Attempt to coerce to int; if fails, treat as unlimited
            try:
                limit_int = int(limit)
            except Exception:
                return kg
            limit = limit_int
        if limit <= 0 or limit >= len(kg):
            return kg
        # Otherwise return the last ``limit`` entries
        return kg[-int(limit):]
    except Exception:
        return []


# Additional semantic memory operations
def update_fact(subject: str, relation: str, obj: str) -> bool:
    """Update an existing fact or add a new one.

    If a fact with the given subject and relation exists, its object will
    be replaced with the provided ``obj``.  If no matching fact exists,
    the triple will be appended as a new fact.  Returns ``True`` on
    success, ``False`` otherwise.  Errors are swallowed silently.

    Args:
        subject: The fact subject to update.
        relation: The relation of the fact.
        obj: The new object string.

    Returns:
        True if the operation succeeded; False otherwise.
    """
    try:
        s = str(subject or "").strip()
        r = str(relation or "").strip()
        o = str(obj or "").strip()
        if not (s and r and o):
            return False
        kg = _load_kg()
        updated = False
        for rec in kg:
            if rec.get("subject", "").lower() == s.lower() and rec.get("relation", "").lower() == r.lower():
                rec["object"] = o
                updated = True
                break
        if not updated:
            # Append as new fact
            kg.append({"subject": s, "relation": r, "object": o})
        _save_kg(kg)
        return True
    except Exception:
        return False


def remove_fact(subject: str, relation: str) -> bool:
    """Remove the first fact matching (subject, relation).

    Matching is case‑insensitive on subject and relation.  If a
    matching fact is found, it is removed from the knowledge graph
    and the function returns ``True``.  If no match is found, the
    function returns ``False``.  Errors are swallowed silently.

    Args:
        subject: The subject of the fact to remove.
        relation: The relation of the fact to remove.

    Returns:
        True if a fact was removed; False otherwise.
    """
    try:
        s = str(subject or "").strip().lower()
        r = str(relation or "").strip().lower()
        if not (s and r):
            return False
        kg = _load_kg()
        for idx, rec in enumerate(kg):
            if rec.get("subject", "").lower() == s and rec.get("relation", "").lower() == r:
                # Remove the matching record
                del kg[idx]
                _save_kg(kg)
                return True
        return False
    except Exception:
        return False


def list_relations() -> List[str]:
    """Return a list of unique relation types present in the KG.

    Relations are returned in insertion order based on their first
    appearance.  Duplicates are removed and case is preserved from
    the first occurrence.  Errors return an empty list.

    Returns:
        A list of relation strings.
    """
    try:
        seen_lower: set[str] = set()
        relations: List[str] = []
        for rec in _load_kg():
            r = rec.get("relation", "").strip()
            rl = r.lower()
            if r and rl not in seen_lower:
                seen_lower.add(rl)
                relations.append(r)
        return relations
    except Exception:
        return []


def group_by_relation(limit: int = 0) -> Dict[str, List[Dict[str, str]]]:
    """Group facts by their relation.

    Facts are grouped into a dictionary keyed by relation.  Each
    value is a list of fact dictionaries (subject, relation, object)
    for that relation.  The ``limit`` parameter controls how many
    facts are considered: if positive, only the most recent ``limit``
    facts are grouped; if zero or negative, all facts are grouped.

    Args:
        limit: Number of recent facts to include; 0 means all.

    Returns:
        A dict mapping relation strings to lists of fact dicts.
    """
    try:
        facts = list_facts(limit)
        grouped: Dict[str, List[Dict[str, str]]] = {}
        for rec in facts:
            r = rec.get("relation", "").strip()
            if not r:
                continue
            grouped.setdefault(r, []).append(rec)
        return grouped
    except Exception:
        return {}

# -----------------------------------------------------------------------------
# Bulk import/export helpers
#
# These functions enable batch management of the knowledge graph.  They are
# intentionally lenient: import will silently skip malformed entries and
# ignore duplicates; export simply returns a copy of all stored facts.  Both
# functions swallow IO errors to avoid impacting the main pipeline.

from typing import Any, Iterable

def import_facts(facts: Iterable[Any]) -> int:
    """Bulk import multiple facts into the knowledge graph.

    Each element in ``facts`` can be a dict with 'subject', 'relation' and
    'object' keys or a sequence of length three.  Only well‑formed triples
    (nonempty strings) are imported.  Duplicate facts are not added.  The
    function returns the number of unique facts successfully appended.

    Args:
        facts: An iterable of fact representations (dicts or tuples).

    Returns:
        The count of new facts added to the graph.
    """
    try:
        existing = _load_kg()
        count = 0
        for entry in facts or []:
            try:
                if isinstance(entry, dict):
                    s = str(entry.get("subject", "")).strip()
                    r = str(entry.get("relation", "")).strip()
                    o = str(entry.get("object", "")).strip()
                else:
                    # assume sequence of three values
                    s, r, o = (str(x).strip() for x in entry)
                if not (s and r and o):
                    continue
                fact = {"subject": s, "relation": r, "object": o}
                # Avoid duplicates (case‑insensitive)
                exists = False
                for rec in existing:
                    if rec["subject"].lower() == s.lower() and rec["relation"].lower() == r.lower() and rec["object"].lower() == o.lower():
                        exists = True
                        break
                if not exists:
                    existing.append(fact)
                    count += 1
            except Exception:
                continue
        if count > 0:
            _save_kg(existing)
        return count
    except Exception:
        return 0

def export_facts() -> List[Dict[str, str]]:
    """Return a copy of all stored facts.

    If an error occurs while loading the knowledge graph, an empty list
    is returned.
    """
    try:
        return list(_load_kg())
    except Exception:
        return []

###############################################################################
# Rule storage and inference utilities
###############################################################################

# In this second version of the knowledge graph the agent can store simple
# inference rules alongside facts.  Rules are represented as a dict with
# keys ``pattern`` and ``consequence``.  For example,
# ``{"pattern": ["located_in", "located_in"], "consequence": "located_in"}``
# expresses a transitive property: if A located_in B and B located_in C then
# infer A located_in C.  The rules file lives in the same ``reports``
# directory as the knowledge graph.

RULES_PATH = MAVEN_ROOT / "reports" / "knowledge_rules.json"

def _load_rules() -> List[Dict[str, Any]]:
    """Load inference rules from disk.

    Returns a list of rule dictionaries.  If the file is missing or
    malformed, an empty list is returned.  Errors are swallowed
    silently.

    Returns:
        A list of rule dicts with keys 'pattern' and 'consequence'.
    """
    try:
        if not RULES_PATH.exists():
            return []
        with RULES_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh) or []
        out: List[Dict[str, Any]] = []
        for rec in data:
            if not isinstance(rec, dict):
                continue
            pat = rec.get("pattern")
            cons = rec.get("consequence")
            if (isinstance(pat, list) and len(pat) == 2 and
                    isinstance(pat[0], str) and isinstance(pat[1], str) and
                    isinstance(cons, str)):
                out.append({"pattern": [pat[0].strip(), pat[1].strip()], "consequence": cons.strip()})
        return out
    except Exception:
        return []


def _save_rules(rules: List[Dict[str, Any]]) -> None:
    """Persist the rules list to disk.

    Any IO errors are ignored to avoid impacting callers.
    """
    try:
        RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
        with RULES_PATH.open("w", encoding="utf-8") as fh:
            json.dump(rules, fh)
    except Exception:
        return


def add_rule(pattern: List[str], consequence: str) -> bool:
    """Add a new inference rule.

    A rule is specified by a two-element pattern of relation names and a
    consequence relation.  For example ``["located_in", "part_of"]``
    with consequence ``"located_in"`` will allow the agent to infer
    that if A located_in B and B part_of C then A located_in C.
    Duplicate rules are not added.  Returns True on success.

    Args:
        pattern: A list of two relation names.
        consequence: The resulting relation name.

    Returns:
        True if the rule was added successfully; False otherwise.
    """
    try:
        if not (isinstance(pattern, list) and len(pattern) == 2):
            return False
        p0, p1 = (str(pattern[0] or "").strip(), str(pattern[1] or "").strip())
        cons = str(consequence or "").strip()
        if not (p0 and p1 and cons):
            return False
        rules = _load_rules()
        # Check for duplicates (case insensitive)
        for rec in rules:
            if rec["pattern"][0].lower() == p0.lower() and rec["pattern"][1].lower() == p1.lower() and rec["consequence"].lower() == cons.lower():
                return False
        rules.append({"pattern": [p0, p1], "consequence": cons})
        _save_rules(rules)
        return True
    except Exception:
        return False


def list_rules() -> List[Dict[str, Any]]:
    """Return the list of stored inference rules.

    Returns a list of rule dictionaries.  Each rule has keys 'pattern'
    (a two-element list of relation strings) and 'consequence' (a
    relation string).  Errors return an empty list.
    """
    return _load_rules()


def run_inference(limit: int = 10) -> List[Dict[str, str]]:
    """Generate inferred facts using stored rules and existing facts.

    This function applies each rule in the rules list to the current
    knowledge graph to produce new inferred triples.  It does not
    persist the inferred facts to the knowledge graph; callers may
    decide to store them using ``add_fact``.  The number of results
    returned can be limited via ``limit``.

    Currently, only simple two‑step chained rules are supported.  For
    each rule pattern [R1, R2] and consequence RC, the function finds
    triples (A, R1, B) and (B, R2, C) and infers (A, RC, C).  The
    matching is case‑insensitive, and duplicate or reflexive facts are
    omitted.  Existing facts in the KG are not returned.

    Args:
        limit: Maximum number of inferred facts to return; 0 or negative
            values imply no limit.

    Returns:
        A list of inferred fact dictionaries.
    """
    results: List[Dict[str, str]] = []
    try:
        kg = _load_kg()
        rules = _load_rules()
        if not rules or not kg:
            return []
        # Prebuild adjacency by relation
        by_rel: Dict[str, List[Dict[str, str]]] = {}
        for rec in kg:
            r = rec.get("relation", "").strip()
            if r:
                by_rel.setdefault(r.lower(), []).append(rec)
        # For each rule apply chaining
        for rule in rules:
            pat = rule.get("pattern")
            cons = rule.get("consequence", "")
            if not pat or not cons:
                continue
            r1 = str(pat[0]).strip().lower()
            r2 = str(pat[1]).strip().lower()
            rc = str(cons).strip()
            # Build triples of form (A,R1,B),(B,R2,C)
            list1 = by_rel.get(r1, [])
            list2 = by_rel.get(r2, [])
            if not list1 or not list2:
                continue
            # Build maps to quickly find all B->C for relation R2
            b_to_c: Dict[str, List[str]] = {}
            for rec2 in list2:
                subj_b = rec2.get("subject", "").strip()
                obj_c = rec2.get("object", "").strip()
                if subj_b and obj_c:
                    b_to_c.setdefault(subj_b.lower(), []).append(obj_c)
            # Now iterate list1 for (A,R1,B) and find (B,R2,C)
            for rec1 in list1:
                subj_a = rec1.get("subject", "").strip()
                obj_b = rec1.get("object", "").strip()
                if not subj_a or not obj_b:
                    continue
                # find Cs
                cs = b_to_c.get(obj_b.lower(), [])
                for c in cs:
                    if subj_a.lower() == c.lower():
                        continue  # skip loops
                    # Check if this inferred fact already exists
                    exists = False
                    for rec in kg:
                        if rec.get("subject", "").lower() == subj_a.lower() and rec.get("relation", "").lower() == rc.lower() and rec.get("object", "").lower() == c.lower():
                            exists = True
                            break
                    if exists:
                        continue
                    results.append({"subject": subj_a, "relation": rc, "object": c})
                    if limit > 0 and len(results) >= limit:
                        return results
        return results[:limit] if limit > 0 else results
    except Exception:
        return []

# -----------------------------------------------------------------------------
# Simple inference engine
#
# The knowledge graph can perform basic forward chaining on certain
# relations to derive new facts.  Specifically, this implementation
# supports transitive closure for the ``located_in`` and ``part_of``
# relations: if ``A located_in B`` and ``B located_in C``, then infer
# ``A located_in C``; similarly for ``part_of``.  Inferred facts are
# returned but not automatically persisted.  Callers can persist them
# using add_fact() if desired.
def infer(limit: int = 10) -> List[Dict[str, str]]:
    """Infer new facts from existing ones using simple transitivity rules.

    Args:
        limit: Maximum number of inferred facts to return.  A zero or
            negative value means no limit.

    Returns:
        A list of inferred fact dictionaries.  Existing facts are not
        included.  The ordering of results is arbitrary.
    """
    results: List[Dict[str, str]] = []
    try:
        kg = _load_kg()
        # Build adjacency lists for efficient lookup
        loc_map: Dict[str, List[str]] = {}
        part_map: Dict[str, List[str]] = {}
        for rec in kg:
            subj = rec.get("subject", "").strip()
            rel = rec.get("relation", "").strip().lower()
            obj = rec.get("object", "").strip()
            if not subj or not obj:
                continue
            if rel == "located_in":
                loc_map.setdefault(subj.lower(), []).append(obj)
            if rel == "part_of":
                part_map.setdefault(subj.lower(), []).append(obj)
        # Generate transitive inferences
        def _infer_transitive(adj_map: Dict[str, List[str]], rel_name: str):
            for a in list(adj_map.keys()):
                for b in adj_map.get(a, []):
                    # Now if b has outgoing edges
                    for c in adj_map.get(b.lower(), []):
                        # Avoid loops and duplicates
                        subj_lower = a.lower()
                        obj_lower = c.lower()
                        if subj_lower == obj_lower:
                            continue
                        # Check if the fact already exists
                        exists = False
                        for rec in kg:
                            if rec.get("subject", "").lower() == subj_lower and rec.get("relation", "").lower() == rel_name.lower() and rec.get("object", "").lower() == obj_lower:
                                exists = True
                                break
                        if exists:
                            continue
                        results.append({"subject": a, "relation": rel_name, "object": c})
                        if limit > 0 and len(results) >= limit:
                            return
        # infer for located_in
        _infer_transitive(loc_map, "located_in")
        if limit <= 0 or len(results) < limit:
            _infer_transitive(part_map, "part_of")
        return results[:limit] if limit > 0 else results
    except Exception:
        return []