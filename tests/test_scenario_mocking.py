"""Tests for DataDrivenMockFactory and register_data_driven."""

from __future__ import annotations

import pytest

from stuntdouble.exceptions import InputNotMatchedError
from stuntdouble.mock_registry import MockToolsRegistry
from stuntdouble.scenario_mocking import DataDrivenMockFactory, register_data_driven

# ---------------------------------------------------------------------------
# DataDrivenMockFactory basics
# ---------------------------------------------------------------------------


class TestDataDrivenMockFactory:
    def test_returns_none_when_no_mock_data(self):
        factory = DataDrivenMockFactory("get_weather")
        result = factory({"mocks": {}})
        assert result is None

    def test_returns_none_when_no_mocks_key(self):
        factory = DataDrivenMockFactory("get_weather")
        result = factory({})
        assert result is None

    def test_single_case_output(self):
        factory = DataDrivenMockFactory("get_weather")
        scenario = {
            "mocks": {
                "get_weather": [{"output": {"temp": 72}}],
            }
        }
        mock_fn = factory(scenario)
        assert mock_fn is not None
        assert mock_fn() == {"temp": 72}

    def test_input_matching(self):
        factory = DataDrivenMockFactory("get_weather")
        scenario = {
            "mocks": {
                "get_weather": [
                    {"input": {"city": "NYC"}, "output": {"temp": 72}},
                    {"input": {"city": "LA"}, "output": {"temp": 85}},
                    {"output": {"temp": 65}},  # catch-all
                ]
            }
        }
        mock_fn = factory(scenario)
        assert mock_fn is not None
        assert mock_fn(city="NYC") == {"temp": 72}
        assert mock_fn(city="LA") == {"temp": 85}
        assert mock_fn(city="Chicago") == {"temp": 65}

    def test_catch_all_case(self):
        factory = DataDrivenMockFactory("tool")
        scenario = {
            "mocks": {
                "tool": [{"output": "default_value"}],
            }
        }
        mock_fn = factory(scenario)
        assert mock_fn is not None
        assert mock_fn(any_arg="anything") == "default_value"

    def test_operator_matching(self):
        factory = DataDrivenMockFactory("query")
        scenario = {
            "mocks": {
                "query": [
                    {"input": {"amount": {"$gt": 1000}}, "output": {"tier": "high"}},
                    {"output": {"tier": "low"}},
                ]
            }
        }
        mock_fn = factory(scenario)
        assert mock_fn is not None
        assert mock_fn(amount=1500) == {"tier": "high"}
        assert mock_fn(amount=500) == {"tier": "low"}

    def test_placeholder_resolution(self):
        factory = DataDrivenMockFactory("tool")
        scenario = {
            "mocks": {
                "tool": [{"output": {"ref": "{{input.name}}"}}],
            }
        }
        mock_fn = factory(scenario)
        assert mock_fn is not None
        result = mock_fn(name="Alice")
        assert result == {"ref": "Alice"}

    def test_uuid_placeholder(self):
        factory = DataDrivenMockFactory("tool")
        scenario = {
            "mocks": {
                "tool": [{"output": {"id": "{{uuid}}"}}],
            }
        }
        mock_fn = factory(scenario)
        assert mock_fn is not None
        result = mock_fn()
        assert isinstance(result["id"], str)
        assert len(result["id"]) == 36  # UUID format

    def test_normalize_single_case_dict(self):
        factory = DataDrivenMockFactory("tool")
        scenario = {
            "mocks": {
                "tool": {"output": {"status": "ok"}},
            }
        }
        mock_fn = factory(scenario)
        assert mock_fn is not None
        assert mock_fn() == {"status": "ok"}

    def test_normalize_direct_output(self):
        factory = DataDrivenMockFactory("tool")
        scenario = {
            "mocks": {
                "tool": {"status": "ok"},
            }
        }
        mock_fn = factory(scenario)
        assert mock_fn is not None
        assert mock_fn() == {"status": "ok"}

    def test_deep_copy_prevents_mutation(self):
        factory = DataDrivenMockFactory("tool")
        scenario = {
            "mocks": {
                "tool": [{"output": {"items": [1, 2, 3]}}],
            }
        }
        mock_fn = factory(scenario)
        assert mock_fn is not None
        result1 = mock_fn()
        result1["items"].append(99)
        result2 = mock_fn()
        assert result2 == {"items": [1, 2, 3]}


# ---------------------------------------------------------------------------
# Fallback behavior
# ---------------------------------------------------------------------------


class TestFallback:
    def test_fallback_when_no_match(self):
        factory = DataDrivenMockFactory("tool", fallback="not found")
        scenario = {
            "mocks": {
                "tool": [
                    {"input": {"id": "123"}, "output": "found"},
                ]
            }
        }
        mock_fn = factory(scenario)
        assert mock_fn is not None
        assert mock_fn(id="123") == "found"
        assert mock_fn(id="999") == "not found"

    def test_fallback_dict(self):
        factory = DataDrivenMockFactory("tool", fallback={"error": "none"})
        scenario = {
            "mocks": {
                "tool": [
                    {"input": {"id": "1"}, "output": "ok"},
                ]
            }
        }
        mock_fn = factory(scenario)
        assert mock_fn is not None
        assert mock_fn(id="999") == {"error": "none"}

    def test_fallback_not_used_when_catch_all_exists(self):
        factory = DataDrivenMockFactory("tool", fallback="FALLBACK")
        scenario = {
            "mocks": {
                "tool": [
                    {"input": {"id": "1"}, "output": "matched"},
                    {"output": "catch-all"},
                ]
            }
        }
        mock_fn = factory(scenario)
        assert mock_fn is not None
        assert mock_fn(id="999") == "catch-all"

    def test_no_fallback_raises_on_no_match(self):
        factory = DataDrivenMockFactory("tool")
        scenario = {
            "mocks": {
                "tool": [
                    {"input": {"id": "1"}, "output": "first"},
                    {"input": {"id": "2"}, "output": "second"},
                ]
            }
        }
        mock_fn = factory(scenario)
        assert mock_fn is not None
        assert mock_fn(id="1") == "first"
        assert mock_fn(id="2") == "second"
        with pytest.raises(InputNotMatchedError):
            mock_fn(id="999")


# ---------------------------------------------------------------------------
# echo_input mode
# ---------------------------------------------------------------------------


class TestEchoInput:
    def test_echo_input_returns_kwargs(self):
        factory = DataDrivenMockFactory("tool", echo_input=True)
        scenario = {
            "mocks": {
                "tool": [
                    {"input": {"id": "1"}, "output": "matched"},
                ]
            }
        }
        mock_fn = factory(scenario)
        assert mock_fn is not None
        assert mock_fn(id="1") == "matched"
        assert mock_fn(id="999", extra="data") == {"id": "999", "extra": "data"}

    def test_echo_input_takes_precedence_over_first_case_fallback(self):
        factory = DataDrivenMockFactory("tool", echo_input=True)
        scenario = {
            "mocks": {
                "tool": [
                    {"input": {"x": "1"}, "output": "matched"},
                ]
            }
        }
        mock_fn = factory(scenario)
        assert mock_fn is not None
        result = mock_fn(x="other")
        assert result == {"x": "other"}

    def test_echo_input_with_fallback_prefers_echo(self):
        # echo_input is checked before fallback
        factory = DataDrivenMockFactory("tool", fallback="fb", echo_input=True)
        scenario = {
            "mocks": {
                "tool": [{"input": {"a": "1"}, "output": "ok"}],
            }
        }
        mock_fn = factory(scenario)
        assert mock_fn is not None
        assert mock_fn(a="other") == {"a": "other"}


# ---------------------------------------------------------------------------
# when_predicate
# ---------------------------------------------------------------------------


class TestWhenPredicate:
    def test_returns_true_when_tool_in_mocks(self):
        factory = DataDrivenMockFactory("my_tool")
        assert factory.when_predicate({"mocks": {"my_tool": []}}) is True

    def test_returns_false_when_tool_not_in_mocks(self):
        factory = DataDrivenMockFactory("my_tool")
        assert factory.when_predicate({"mocks": {"other_tool": []}}) is False

    def test_returns_false_when_no_mocks_key(self):
        factory = DataDrivenMockFactory("my_tool")
        assert factory.when_predicate({}) is False


# ---------------------------------------------------------------------------
# register_data_driven (free function)
# ---------------------------------------------------------------------------


class TestRegisterDataDriven:
    def test_registers_on_registry(self):
        registry = MockToolsRegistry()
        register_data_driven(registry, "my_tool")
        assert registry.is_registered("my_tool")

    def test_returns_factory(self):
        registry = MockToolsRegistry()
        factory = register_data_driven(registry, "my_tool", echo_input=True)
        assert isinstance(factory, DataDrivenMockFactory)
        assert factory.echo_input is True

    def test_resolve_returns_mock(self):
        registry = MockToolsRegistry()
        register_data_driven(registry, "query_bills", echo_input=True)
        scenario = {
            "mocks": {
                "query_bills": [{"output": {"total": 5}}],
            }
        }
        mock_fn = registry.resolve("query_bills", scenario)
        assert mock_fn is not None
        assert mock_fn() == {"total": 5}

    def test_resolve_returns_none_when_no_data(self):
        registry = MockToolsRegistry()
        register_data_driven(registry, "query_bills")
        mock_fn = registry.resolve("query_bills", {"mocks": {}})
        assert mock_fn is None


# ---------------------------------------------------------------------------
# MockToolsRegistry.register_data_driven (convenience method)
# ---------------------------------------------------------------------------


class TestRegistryConvenienceMethod:
    def test_register_data_driven_method(self):
        registry = MockToolsRegistry()
        registry.register_data_driven("my_tool")
        assert registry.is_registered("my_tool")

    def test_register_data_driven_with_options(self):
        registry = MockToolsRegistry()
        registry.register_data_driven("my_tool", fallback="nope", echo_input=True)

        scenario = {
            "mocks": {
                "my_tool": [{"input": {"x": "1"}, "output": "match"}],
            }
        }
        mock_fn = registry.resolve("my_tool", scenario)
        assert mock_fn is not None
        # Should match
        assert mock_fn(x="1") == "match"
        # echo_input on no-match
        assert mock_fn(x="other") == {"x": "other"}

    def test_full_pipeline_multiple_tools(self):
        """Simulates the agent-bourne replacement pattern."""
        registry = MockToolsRegistry()
        for tool in ["list_customers", "query_bills", "account_balance"]:
            registry.register_data_driven(tool, echo_input=True)
        registry.register_data_driven("knowledgebase", fallback="No documents found.")

        scenario = {
            "mocks": {
                "list_customers": [
                    {"input": {"status": "active"}, "output": [{"id": "C1"}]},
                    {"output": []},
                ],
                "query_bills": [{"output": {"total": 42}}],
                "knowledgebase": [
                    {
                        "input": {"query": "refund"},
                        "output": "Refund policy: ...",
                    },
                ],
            }
        }

        # list_customers - matches
        fn = registry.resolve("list_customers", scenario)
        assert fn is not None
        assert fn(status="active") == [{"id": "C1"}]
        assert fn(status="inactive") == []

        # query_bills - catch-all
        fn = registry.resolve("query_bills", scenario)
        assert fn is not None
        assert fn(vendor="Acme") == {"total": 42}

        # knowledgebase - with fallback
        fn = registry.resolve("knowledgebase", scenario)
        assert fn is not None
        assert fn(query="refund") == "Refund policy: ..."
        assert fn(query="unknown") == "No documents found."

        # account_balance - not in scenario mocks, should skip
        fn = registry.resolve("account_balance", scenario)
        assert fn is None


# ---------------------------------------------------------------------------
# Config placeholder resolution ({{config.*}})
# ---------------------------------------------------------------------------


class TestConfigPlaceholders:
    def test_config_placeholder_resolved(self):
        factory = DataDrivenMockFactory("tool")
        scenario = {
            "mocks": {
                "tool": [{"output": {"user": "{{config.user_id}}"}}],
            }
        }
        config = {"configurable": {"user_id": "U-123"}}
        mock_fn = factory(scenario, config)
        assert mock_fn is not None
        assert mock_fn() == {"user": "U-123"}

    def test_config_placeholder_with_default(self):
        factory = DataDrivenMockFactory("tool")
        scenario = {
            "mocks": {
                "tool": [{"output": {"env": "{{config.env | default('prod')}}"}}],
            }
        }
        mock_fn = factory(scenario, config=None)
        assert mock_fn is not None
        assert mock_fn() == {"env": "prod"}

    def test_config_and_input_placeholders_together(self):
        factory = DataDrivenMockFactory("tool")
        scenario = {
            "mocks": {
                "tool": [
                    {
                        "output": {
                            "realm": "{{config.realm_id}}",
                            "query": "{{input.q}}",
                            "ts": "{{now}}",
                        }
                    }
                ],
            }
        }
        config = {"configurable": {"realm_id": "R-456"}}
        mock_fn = factory(scenario, config)
        assert mock_fn is not None
        result = mock_fn(q="test")
        assert result["realm"] == "R-456"
        assert result["query"] == "test"
        assert "T" in result["ts"]  # ISO timestamp

    def test_config_data_key_takes_precedence(self):
        factory = DataDrivenMockFactory("tool")
        scenario = {
            "mocks": {
                "tool": [{"output": {"val": "{{config.key}}"}}],
            }
        }
        config = {
            "configurable": {
                "key": "from_configurable",
                "config_data": {"key": "from_config_data"},
            }
        }
        mock_fn = factory(scenario, config)
        assert mock_fn is not None
        assert mock_fn() == {"val": "from_config_data"}

    def test_config_without_configurable_key(self):
        factory = DataDrivenMockFactory("tool")
        scenario = {
            "mocks": {
                "tool": [{"output": {"val": "{{config.x | default('none')}}"}}],
            }
        }
        mock_fn = factory(scenario, config={})
        assert mock_fn is not None
        assert mock_fn() == {"val": "none"}

    def test_config_passed_through_registry_resolve(self):
        registry = MockToolsRegistry()
        registry.register_data_driven("tool")
        scenario = {
            "mocks": {
                "tool": [{"output": {"rid": "{{config.realm_id}}"}}],
            }
        }
        config = {"configurable": {"realm_id": "R-789"}}
        mock_fn = registry.resolve("tool", scenario, config=config)
        assert mock_fn is not None
        assert mock_fn() == {"rid": "R-789"}


# ---------------------------------------------------------------------------
# Import paths
# ---------------------------------------------------------------------------


class TestImports:
    def test_import_from_top_level(self):
        from stuntdouble import (
            DataDrivenMockFactory,
            register_data_driven,
        )

        assert DataDrivenMockFactory is not None
        assert register_data_driven is not None

    def test_import_from_scenario_mocking_module(self):
        from stuntdouble.scenario_mocking import (
            DataDrivenMockFactory,
            register_data_driven,
        )

        assert DataDrivenMockFactory is not None
        assert register_data_driven is not None


# ---------------------------------------------------------------------------
# repr
# ---------------------------------------------------------------------------


class TestRepr:
    def test_basic_repr(self):
        f = DataDrivenMockFactory("tool")
        assert repr(f) == "DataDrivenMockFactory('tool')"

    def test_repr_with_options(self):
        f = DataDrivenMockFactory("tool", fallback="x", echo_input=True)
        assert "fallback='x'" in repr(f)
        assert "echo_input=True" in repr(f)
