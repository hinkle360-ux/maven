"""
Procedural domain bank
----------------------

This bank stores step‑by‑step procedures, how‑to guides and action
instructions that do not fit into a single subject area.  It uses the
generic domain bank template for persistence and retrieval.

Procedural knowledge is often transient or contextual; this bank
provides a dedicated place for such content.  The bank is retained
primarily for backwards compatibility with older tests and routing
logic.
"""

from templates.DOMAIN_BANK_TEMPLATE import bank_service_factory

service_api = bank_service_factory('procedural')
