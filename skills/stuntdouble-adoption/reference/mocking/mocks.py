"""Hand-written mock factories.

Only tools that need logic get a factory here. Tools whose mock is pure data
(``list_bills``) are registered with ``register_data_driven`` in ``registry.py``
and need no code at all.

Every inner ``mock_fn`` mirrors the real tool's parameters exactly (names,
defaults, order) so ``validate_signatures=True`` passes and the LLM's tool
call binds without surprises.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from stuntdouble import get_configurable_context, resolve_output


def get_customer_mock(scenario_metadata: dict[str, Any]) -> Callable[..., Any]:
    """Simple pattern: return the configured output, or a sensible default."""
    cases = scenario_metadata.get("mocks", {}).get("get_customer", [])
    configured = cases[0].get("output") if cases else None

    def mock_fn(customer_id: str) -> dict:
        return configured or {"id": customer_id, "name": "Mock Customer", "tier": "standard"}

    return mock_fn


def create_invoice_mock(scenario_metadata: dict[str, Any], config: dict[str, Any] | None = None) -> Callable[..., Any]:
    """Conditional pattern: behaviour driven by scenario_metadata plus runtime config.

    ``scenario_metadata["invoice_policy"]`` selects the behaviour:
      - ``"accept"`` (default): return a resolved invoice, echoing the input.
      - ``"reject_large"``: raise for amounts above ``max_amount`` so the
        agent's error handling can be exercised.

    ``config`` is the RunnableConfig; anything the service put under
    ``configurable`` (here ``user_id``) is available for context-aware output.
    """
    policy = scenario_metadata.get("invoice_policy", "accept")
    max_amount = scenario_metadata.get("max_amount", 10_000)
    created_by = get_configurable_context(config).get("user_id", "system")

    def mock_fn(customer_id: str, amount: float, due_date: str | None = None) -> dict:
        if policy == "reject_large" and amount > max_amount:
            raise ValueError(f"Invoice amount {amount} exceeds limit {max_amount}")
        template = {
            "invoice_id": "{{uuid}}",
            "customer_id": "{{input.customer_id}}",
            "amount": "{{input.amount}}",
            "due_date": due_date or "{{now + 30d}}",
            "created_at": "{{now}}",
            "created_by": created_by,
            "status": "draft",
        }
        return resolve_output(template, input_data={"customer_id": customer_id, "amount": amount})

    return mock_fn
