"""Builds the MockToolsRegistry for the reference agent.

One registration per real tool. Data-only tools use ``register_data_driven``;
tools that need logic use a factory from ``mocks.py``. Passing ``tool=``
validates the factory's signature against the real tool at registration time,
so a drift between the two fails fast at startup instead of mid-conversation.
"""

from __future__ import annotations

from tools import create_invoice, get_customer

from mocking.mocks import create_invoice_mock, get_customer_mock
from stuntdouble import MockToolsRegistry


def build_registry() -> MockToolsRegistry:
    """Return a fully populated registry. Call once at startup."""
    registry = MockToolsRegistry()

    # Data-driven: cases live in scenario_metadata["mocks"]["list_bills"].
    # fallback= is returned when no case's "input" matches and there is no catch-all.
    registry.register_data_driven("list_bills", fallback={"bills": [], "total_due": 0})

    # Hand-written factories, validated against the real tool signatures.
    registry.register("get_customer", mock_fn=get_customer_mock, tool=get_customer)
    registry.register("create_invoice", mock_fn=create_invoice_mock, tool=create_invoice)

    return registry
