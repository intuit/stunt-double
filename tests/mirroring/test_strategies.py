"""Unit tests for mirroring strategies (BaseStrategy, StaticStrategy, DynamicStrategy)."""

import pytest

from stuntdouble.mirroring.models import ToolDefinition
from stuntdouble.mirroring.strategies import (
    BaseStrategy,
    DynamicStrategy,
    StaticStrategy,
)


def _make_tool_def(
    name: str = "get_customer", description: str = "Get a customer"
) -> ToolDefinition:
    """Helper to create a ToolDefinition for testing."""
    return ToolDefinition(
        name=name,
        description=description,
        input_schema={
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "Customer ID"},
            },
            "required": ["customer_id"],
        },
    )


class TestBaseStrategy:
    """Tests for BaseStrategy abstract class."""

    def test_cannot_instantiate_directly(self):
        """BaseStrategy is abstract and cannot be instantiated."""
        with pytest.raises(TypeError):
            BaseStrategy()  # type: ignore[abstract]

    def test_name_property(self):
        """Subclasses get their class name as strategy name."""
        strategy = StaticStrategy()
        assert strategy.name == "StaticStrategy"

    def test_cache_none_by_default(self):
        """Cache is None by default."""
        strategy = StaticStrategy()
        assert strategy.cache is None

    def test_check_cache_returns_none_without_cache(self):
        """_check_cache returns None when no cache configured."""
        strategy = StaticStrategy()
        tool_def = _make_tool_def()
        assert strategy._check_cache(tool_def, {"id": "1"}) is None

    def test_store_cache_noop_without_cache(self):
        """_store_cache is a no-op when no cache configured."""
        strategy = StaticStrategy()
        tool_def = _make_tool_def()
        # Should not raise
        strategy._store_cache(tool_def, {"id": "1"}, {"result": "ok"})


class TestStaticStrategy:
    """Tests for StaticStrategy."""

    def test_basic_generation(self):
        """Generates a non-empty response for a tool."""
        strategy = StaticStrategy()
        tool_def = _make_tool_def()
        response = strategy.generate(tool_def)
        assert isinstance(response, dict)
        assert len(response) > 0

    def test_list_tool_generation(self):
        """Generates list-style response for 'list' tools."""
        strategy = StaticStrategy()
        tool_def = _make_tool_def(
            name="list_customers", description="List all customers"
        )
        response = strategy.generate(tool_def)
        assert isinstance(response, dict)

    def test_create_tool_generation(self):
        """Generates creation response for 'create' tools."""
        strategy = StaticStrategy()
        tool_def = _make_tool_def(
            name="create_customer", description="Create a customer"
        )
        response = strategy.generate(tool_def)
        assert isinstance(response, dict)

    def test_update_tool_generation(self):
        """Generates update response for 'update' tools."""
        strategy = StaticStrategy()
        tool_def = _make_tool_def(
            name="update_customer", description="Update a customer"
        )
        response = strategy.generate(tool_def)
        assert isinstance(response, dict)

    def test_delete_tool_generation(self):
        """Generates deletion response for 'delete' tools."""
        strategy = StaticStrategy()
        tool_def = _make_tool_def(
            name="delete_customer", description="Delete a customer"
        )
        response = strategy.generate(tool_def)
        assert isinstance(response, dict)

    def test_generic_tool_generation(self):
        """Generates generic response for unrecognized tool names."""
        strategy = StaticStrategy()
        tool_def = _make_tool_def(
            name="process_payment", description="Process a payment"
        )
        response = strategy.generate(tool_def)
        assert isinstance(response, dict)

    def test_parameter_awareness_echoes_ids(self):
        """Response echoes back ID parameters."""
        strategy = StaticStrategy()
        tool_def = _make_tool_def()
        response = strategy.generate(tool_def, {"customer_id": "CUST-123"})
        assert response.get("customer_id") == "CUST-123"

    def test_parameter_awareness_pagination(self):
        """Response respects pagination parameters."""
        strategy = StaticStrategy()
        tool_def = _make_tool_def(name="list_items", description="List items")
        response = strategy.generate(tool_def, {"page": 2})
        assert response.get("page") == 2

    def test_with_cache(self):
        """Caching works when provided."""

        class FakeCache:
            def __init__(self):
                self.store = {}

            def get(self, name, params):
                key = f"{name}:{sorted(params.items())}"
                return self.store.get(key)

            def set(self, name, params, response):
                key = f"{name}:{sorted(params.items())}"
                self.store[key] = response

        cache = FakeCache()
        strategy = StaticStrategy(cache=cache)
        tool_def = _make_tool_def()
        params = {"customer_id": "123"}

        # First call populates cache
        response1 = strategy.generate(tool_def, params)
        # Second call should return cached
        response2 = strategy.generate(tool_def, params)
        assert response1 == response2


class TestDynamicStrategy:
    """Tests for DynamicStrategy."""

    def test_requires_llm_client(self):
        """DynamicStrategy raises ValueError without LLM client."""
        with pytest.raises(ValueError, match="requires an LLM client"):
            DynamicStrategy(llm_client=None)

    def test_basic_construction(self):
        """Can create with a (fake) LLM client."""

        class FakeLLM:
            pass

        strategy = DynamicStrategy(llm_client=FakeLLM())
        assert strategy.llm_calls == 0
        assert strategy.cache_hits == 0

    def test_get_stats_initial(self):
        """Initial stats are zero."""

        class FakeLLM:
            pass

        strategy = DynamicStrategy(llm_client=FakeLLM())
        stats = strategy.get_stats()
        assert stats["llm_calls"] == 0
        assert stats["cache_hits"] == 0
        assert stats["total_requests"] == 0
        assert stats["cache_hit_rate"] == 0.0

    def test_name_property(self):
        """Strategy name is 'DynamicStrategy'."""

        class FakeLLM:
            pass

        strategy = DynamicStrategy(llm_client=FakeLLM())
        assert strategy.name == "DynamicStrategy"
