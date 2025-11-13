"""
STM‑only domain bank
---------------------

This bank stores low‑confidence or unknown facts in short‑term memory (STM) only.
It is intended as a lightweight sink for content that should not be persisted
beyond the current session.  Facts stored here remain in the STM tier and
are subject to rotation rules defined in the Maven configuration.  Retrieval
returns records from any tier but most facts will reside in STM.

The implementation simply delegates to the generic ``bank_service_factory``
provided by the domain bank template.  It creates a service_api compatible
with the other domain banks and uses the bank name ``'stm_only'``.

Note: The STM‑only bank is not part of the canonical set of eleven topical
banks defined in the Companion Addendum.  However, it is provided to
maintain backward compatibility with existing routing logic in the reasoning
brain that assigns low‑confidence facts to an STM‑only bank.  Future
architectural revisions may deprecate this bank in favour of more nuanced
routing.
"""

from templates.DOMAIN_BANK_TEMPLATE import bank_service_factory

# Expose the service API using the generic factory.  The factory handles
# storage, retrieval, rotation and simple inverted indexing.
service_api = bank_service_factory('stm_only')
