"""
Unit tests for StuntDouble LangGraph MockToolsRegistry.
"""

from typing import Any

import pytest


class TestMockToolsRegistry:
    """Tests for MockToolsRegistry."""

    def test_register_simple_factory(self):
        """Test registering a simple mocked tool."""
        from stuntdouble import MockToolsRegistry

        registry = MockToolsRegistry()

        # Register a factory that returns a simple mock
        registry.register(
            "get_weather",
            mock_fn=lambda md: lambda city: {"temp": 72, "city": city},
        )

        assert "get_weather" in registry
        assert registry.is_registered("get_weather")
        assert len(registry) == 1

    def test_register_with_when_predicate(self):
        """Test registering with a conditional when predicate."""
        from stuntdouble import MockToolsRegistry

        registry = MockToolsRegistry()

        registry.register(
            "bills_query",
            mock_fn=lambda md: lambda **kw: md["fixtures"]["bills_query"],
            when=lambda md: md.get("mode") == "mock",
        )

        assert registry.is_registered("bills_query")

    def test_resolve_returns_callable(self):
        """Test that resolve returns a callable mock function."""
        from stuntdouble import MockToolsRegistry

        registry = MockToolsRegistry()
        registry.register(
            "get_user",
            mock_fn=lambda md: lambda user_id: {"id": user_id, "name": "Test"},
        )

        mock_fn = registry.resolve("get_user", {"mode": "mock"})

        assert mock_fn is not None
        assert callable(mock_fn)
        result = mock_fn(user_id="123")
        assert result == {"id": "123", "name": "Test"}

    def test_resolve_returns_none_for_unregistered(self):
        """Test that resolve returns None for unregistered tools."""
        from stuntdouble import MockToolsRegistry

        registry = MockToolsRegistry()

        mock_fn = registry.resolve("unknown_tool", {"mode": "mock"})

        assert mock_fn is None

    def test_resolve_respects_when_predicate(self):
        """Test that resolve respects the when predicate."""
        from stuntdouble import MockToolsRegistry

        registry = MockToolsRegistry()
        registry.register(
            "conditional_tool",
            mock_fn=lambda md: lambda: "mocked",
            when=lambda md: md.get("mode") == "mock",
        )

        # When predicate returns True
        mock_fn = registry.resolve("conditional_tool", {"mode": "mock"})
        assert mock_fn is not None
        assert mock_fn() == "mocked"

        # When predicate returns False
        mock_fn = registry.resolve("conditional_tool", {"mode": "real"})
        assert mock_fn is None

    def test_resolve_uses_scenario_metadata_in_mocked_tool(self):
        """Test that mocked tool receives scenario_metadata."""
        from stuntdouble import MockToolsRegistry

        registry = MockToolsRegistry()

        def fixture_factory(scenario_metadata):
            fixtures = scenario_metadata.get("fixtures", {})
            return lambda: fixtures.get("data_tool", "default")

        registry.register("data_tool", mock_fn=fixture_factory)

        # Resolve with fixtures
        mock_fn = registry.resolve(
            "data_tool",
            {"fixtures": {"data_tool": "fixture_value"}},
        )
        assert mock_fn is not None
        assert mock_fn() == "fixture_value"

        # Resolve without fixtures
        mock_fn = registry.resolve("data_tool", {"fixtures": {}})
        assert mock_fn is not None
        assert mock_fn() == "default"

    def test_unregister(self):
        """Test unregistering a mock."""
        from stuntdouble import MockToolsRegistry

        registry = MockToolsRegistry()
        registry.register("tool", mock_fn=lambda md: lambda: "mock")

        assert registry.is_registered("tool")

        result = registry.unregister("tool")
        assert result is True
        assert not registry.is_registered("tool")

        # Unregistering non-existent returns False
        result = registry.unregister("tool")
        assert result is False

    def test_clear(self):
        """Test clearing all registrations."""
        from stuntdouble import MockToolsRegistry

        registry = MockToolsRegistry()
        registry.register("tool1", mock_fn=lambda md: lambda: "1")
        registry.register("tool2", mock_fn=lambda md: lambda: "2")

        assert len(registry) == 2

        registry.clear()

        assert len(registry) == 0
        assert not registry.is_registered("tool1")

    def test_list_registered(self):
        """Test listing registered tool names."""
        from stuntdouble import MockToolsRegistry

        registry = MockToolsRegistry()
        registry.register("tool_a", mock_fn=lambda md: lambda: "a")
        registry.register("tool_b", mock_fn=lambda md: lambda: "b")

        registered = registry.list_registered()

        assert set(registered) == {"tool_a", "tool_b"}

    def test_mocked_tool_exception_returns_none(self):
        """Test that mocked tool exceptions result in None resolution."""
        from stuntdouble import MockToolsRegistry

        registry = MockToolsRegistry()

        def bad_factory(md):
            raise RuntimeError("Mocked tool error")

        registry.register("bad_tool", mock_fn=bad_factory)

        mock_fn = registry.resolve("bad_tool", {})
        assert mock_fn is None

    def test_when_predicate_exception_returns_none(self):
        """Test that when predicate exceptions result in None resolution."""
        from stuntdouble import MockToolsRegistry

        registry = MockToolsRegistry()

        def bad_when(md):
            raise RuntimeError("Predicate error")

        registry.register(
            "bad_predicate_tool",
            mock_fn=lambda md: lambda: "mock",
            when=bad_when,
        )

        registry.resolve("bad_predicate_tool", {})

    def test_resolve_passes_config_to_new_style_factory(self):
        """Test that resolve passes config to factories that accept 2 params."""
        from stuntdouble import MockToolsRegistry

        registry = MockToolsRegistry()

        received_config = None

        def new_style_factory(scenario_metadata, config=None):
            nonlocal received_config
            received_config = config
            return lambda: {"from_new_style": True}

        registry.register("new_style_tool", mock_fn=new_style_factory)

        test_config = {"configurable": {"agent_context": {"user_id": "test_user"}}}
        mock_fn = registry.resolve("new_style_tool", {"mode": "mock"}, config=test_config)

        assert mock_fn is not None
        assert received_config == test_config
        assert mock_fn() == {"from_new_style": True}

    def test_resolve_works_with_old_style_factory(self):
        """Test that resolve still works with old-style 1-param factories."""
        from stuntdouble import MockToolsRegistry

        registry = MockToolsRegistry()

        # Old-style factory: only takes scenario_metadata
        def old_style_factory(scenario_metadata):
            return lambda: {"from_old_style": True}

        registry.register("old_style_tool", mock_fn=old_style_factory)

        test_config = {"configurable": {"agent_context": {"user_id": "test_user"}}}
        mock_fn = registry.resolve("old_style_tool", {"mode": "mock"}, config=test_config)

        assert mock_fn is not None
        assert mock_fn() == {"from_old_style": True}

    def test_resolve_with_kwargs_factory(self):
        """Test that resolve works with **kwargs factory."""
        from stuntdouble import MockToolsRegistry

        registry = MockToolsRegistry()

        # Factory with **kwargs - sig.bind({}, {}) will succeed
        def kwargs_factory(scenario_metadata, **kwargs):
            return lambda: {"kwargs_received": list(kwargs.keys())}

        registry.register("kwargs_tool", mock_fn=kwargs_factory)

        test_config: dict[str, Any] = {"configurable": {}}
        mock_fn = registry.resolve("kwargs_tool", {"mode": "mock"}, config=test_config)

        assert mock_fn is not None

    def test_resolve_config_defaults_to_none(self):
        """Test that config defaults to None when not provided."""
        from stuntdouble import MockToolsRegistry

        registry = MockToolsRegistry()

        received_config = "NOT_SET"

        def factory_checking_config(scenario_metadata, config=None):
            nonlocal received_config
            received_config = config
            return lambda: {"checked": True}

        registry.register("config_check_tool", mock_fn=factory_checking_config)

        # Call without config parameter
        mock_fn = registry.resolve("config_check_tool", {"mode": "mock"})

        assert mock_fn is not None
        assert received_config is None  # Should be None, not "NOT_SET"
        assert mock_fn() == {"checked": True}

    def test_register_validation(self):
        """Test that register validates inputs."""
        from stuntdouble import MockToolsRegistry

        registry = MockToolsRegistry()

        # Empty tool name
        with pytest.raises(ValueError, match="tool_name cannot be empty"):
            registry.register("", mock_fn=lambda md: lambda: "mock")

        # Non-callable mock_fn
        with pytest.raises(ValueError, match="mock_fn must be callable"):
            registry.register("tool", mock_fn="not_callable")  # type: ignore

        # Non-callable when
        with pytest.raises(ValueError, match="when must be callable or None"):
            registry.register(
                "tool",
                mock_fn=lambda md: lambda: "mock",
                when="not_callable",  # type: ignore
            )
