"""
Working Theories domain bank
---------------------------

This bank stores moderate‑confidence facts and educated guesses that are not
considered fully verified.  Records are persisted using the generic domain
bank template with rotation across STM, MTM and LTM tiers according to
configuration thresholds.  Retrieval searches across all tiers.

The implementation delegates to the ``bank_service_factory`` from the
``templates.DOMAIN_BANK_TEMPLATE`` module, which provides standard store
and retrieve operations and handles tier rotation.

While the canonical set of Maven domain banks focuses on subject areas
and theories/contradictions, the working_theories bank is retained for
backwards compatibility with earlier routing logic.  Future revisions may
consolidate moderate‑confidence facts into other banks.
"""

from templates.DOMAIN_BANK_TEMPLATE import bank_service_factory

service_api = bank_service_factory('working_theories')
