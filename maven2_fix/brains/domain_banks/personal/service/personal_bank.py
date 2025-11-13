"""
Personal domain bank
---------------------

This bank stores personal knowledge and self‑identity information about Maven.
It uses the generic domain bank template for persistence and retrieval.

Personal knowledge includes foundational facts about Maven such as who
created it, why it exists, and other self‑referential information. This
bank allows retrieval of such facts through the routing system.

The implementation delegates to the ``bank_service_factory`` from the
``templates.DOMAIN_BANK_TEMPLATE`` module, which provides standard store
and retrieve operations and handles tier rotation.
"""

from templates.DOMAIN_BANK_TEMPLATE import bank_service_factory

service_api = bank_service_factory('personal')
