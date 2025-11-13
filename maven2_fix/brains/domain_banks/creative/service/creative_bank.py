"""
Creative domain bank
--------------------

This bank stores creative ideas, stories and non‑factual generative content.
It delegates persistence and retrieval to the generic domain bank template.

The creative bank exists for compatibility with earlier versions of Maven
that distinguished creative outputs from factual knowledge.  It may be
deprecated in future in favour of contextual creative generation.
"""

from templates.DOMAIN_BANK_TEMPLATE import bank_service_factory

service_api = bank_service_factory('creative')
