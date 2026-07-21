"""Cross-surface conformance scaffold (parity slice #1605).

The direct application service is the behavioral oracle for the parity epic
(#1593).  This package supplies the three pieces adapter suites build on:

- :mod:`tests.conformance.corpus`: the deterministic fixture corpus.
- :mod:`tests.conformance.normalize`: helpers that strip presentation-only
  differences from requests, plans, results, errors, and audit events.
- :mod:`tests.conformance.driver`: the adapter-driver protocol and the
  direct-service reference driver.

Adapter drivers (#1595-#1598) implement
:class:`tests.conformance.driver.OrganizationConformanceDriver` and reuse the
corpus and normalization helpers unchanged; golden expectations always come
from canonical service semantics, never from any adapter.
"""
