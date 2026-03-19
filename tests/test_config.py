"""
Unit tests for stuntdouble config module.

Tests for config utilities: inject_scenario_metadata,
extract_scenario_metadata_from_config, and get_configurable_context.
"""


class TestInjectScenarioMetadata:
    """Tests for inject_scenario_metadata helper function."""

    def test_inject_into_none_config(self):
        from stuntdouble import inject_scenario_metadata

        result = inject_scenario_metadata(None, {"mode": "mock"})

        assert result["configurable"]["scenario_metadata"] == {"mode": "mock"}

    def test_inject_into_empty_config(self):
        from stuntdouble import inject_scenario_metadata

        result = inject_scenario_metadata({}, {"mocks": {"tool_a": []}})

        assert result["configurable"]["scenario_metadata"] == {"mocks": {"tool_a": []}}

    def test_preserves_existing_configurable(self):
        from stuntdouble import inject_scenario_metadata

        config = {"configurable": {"thread_id": "t-1", "user_id": "u-1"}}
        result = inject_scenario_metadata(config, {"scenario_id": "s-1"})

        assert result["configurable"]["thread_id"] == "t-1"
        assert result["configurable"]["user_id"] == "u-1"
        assert result["configurable"]["scenario_metadata"] == {"scenario_id": "s-1"}

    def test_preserves_non_configurable_keys(self):
        from stuntdouble import inject_scenario_metadata

        config = {"callbacks": ["cb1"], "configurable": {"thread_id": "t-1"}}
        result = inject_scenario_metadata(config, {"mode": "test"})

        assert result["callbacks"] == ["cb1"]
        assert result["configurable"]["scenario_metadata"] == {"mode": "test"}

    def test_overwrites_existing_scenario_metadata(self):
        from stuntdouble import inject_scenario_metadata

        config = {"configurable": {"scenario_metadata": {"old": True}}}
        result = inject_scenario_metadata(config, {"new": True})

        assert result["configurable"]["scenario_metadata"] == {"new": True}


class TestExtractScenarioMetadataFromConfig:
    """Tests for extract_scenario_metadata_from_config helper function."""

    def test_returns_none_for_none_config(self):
        from stuntdouble import extract_scenario_metadata_from_config

        assert extract_scenario_metadata_from_config(None) is None

    def test_returns_none_for_empty_config(self):
        from stuntdouble import extract_scenario_metadata_from_config

        assert extract_scenario_metadata_from_config({}) is None

    def test_returns_none_when_no_scenario_metadata(self):
        from stuntdouble import extract_scenario_metadata_from_config

        config = {"configurable": {"thread_id": "t-1"}}
        assert extract_scenario_metadata_from_config(config) is None

    def test_returns_scenario_metadata(self):
        from stuntdouble import extract_scenario_metadata_from_config

        metadata = {"mocks": {"tool_a": [{"output": {"ok": True}}]}}
        config = {"configurable": {"scenario_metadata": metadata}}

        result = extract_scenario_metadata_from_config(config)
        assert result == metadata

    def test_returns_none_for_non_dict_configurable(self):
        from stuntdouble import extract_scenario_metadata_from_config

        config = {"configurable": "not_a_dict"}
        assert extract_scenario_metadata_from_config(config) is None

    def test_returns_none_for_missing_configurable(self):
        from stuntdouble import extract_scenario_metadata_from_config

        config = {"other_key": "value"}
        assert extract_scenario_metadata_from_config(config) is None


class TestInjectAndExtractRoundTrip:
    """Tests for inject + extract round-trip consistency."""

    def test_round_trip(self):
        from stuntdouble import (
            extract_scenario_metadata_from_config,
            inject_scenario_metadata,
        )

        metadata = {"scenario_id": "s-1", "mocks": {"tool_a": [{"output": 42}]}}
        config = inject_scenario_metadata(None, metadata)

        extracted = extract_scenario_metadata_from_config(config)
        assert extracted == metadata


class TestGetConfigurableContext:
    """Tests for get_configurable_context helper function."""

    def test_returns_empty_dict_for_none_config(self):
        """Test that None config returns empty dict."""
        from stuntdouble import get_configurable_context

        result = get_configurable_context(None)

        assert result == {}

    def test_returns_empty_dict_for_empty_config(self):
        """Test that empty config returns empty dict."""
        from stuntdouble import get_configurable_context

        result = get_configurable_context({})

        assert result == {}

    def test_returns_configurable_dict(self):
        """Test that configurable dict is returned."""
        from stuntdouble import get_configurable_context

        config = {
            "configurable": {
                "agent_context": {"user_id": "test_user"},
                "thread_id": "thread_123",
            }
        }

        result = get_configurable_context(config)

        assert result == {
            "agent_context": {"user_id": "test_user"},
            "thread_id": "thread_123",
        }

    def test_returns_empty_dict_for_non_dict_configurable(self):
        """Test that non-dict configurable returns empty dict."""
        from stuntdouble import get_configurable_context

        config = {"configurable": "not_a_dict"}

        result = get_configurable_context(config)

        assert result == {}

    def test_returns_empty_dict_for_missing_configurable(self):
        """Test that missing configurable key returns empty dict."""
        from stuntdouble import get_configurable_context

        config = {"other_key": "value"}

        result = get_configurable_context(config)

        assert result == {}

    def test_can_access_agent_context(self):
        """Test that agent_context can be accessed from result."""
        from stuntdouble import get_configurable_context

        config = {
            "configurable": {
                "agent_context": {
                    "auth_header": {
                        "auth_context": {
                            "user_id": "user_123",
                            "org_id": "org_456",
                        }
                    }
                }
            }
        }

        ctx = get_configurable_context(config)
        agent_context = ctx.get("agent_context")

        assert agent_context is not None
        assert (
            agent_context["auth_header"]["auth_context"]["user_id"]
            == "user_123"
        )

    def test_can_access_custom_fields(self):
        """Test that custom fields in configurable can be accessed."""
        from stuntdouble import get_configurable_context

        config = {
            "configurable": {
                "custom_field": "custom_value",
                "another_field": {"nested": True},
            }
        }

        ctx = get_configurable_context(config)

        assert ctx.get("custom_field") == "custom_value"
        assert ctx.get("another_field") == {"nested": True}


class TestGetConfigurableContextExport:
    """Tests for get_configurable_context export."""

    def test_exported_from_hook_module(self):
        """Test that get_configurable_context is exported from hook module."""
        from stuntdouble import get_configurable_context

        assert callable(get_configurable_context)

    def test_in_all_exports(self):
        """Test that get_configurable_context is in __all__."""
        from stuntdouble import __all__

        assert "get_configurable_context" in __all__


class TestGetConfigurableContextUsageInMockFactory:
    """Tests demonstrating get_configurable_context usage in mock factories."""

    def test_mock_factory_can_use_helper(self):
        """Test that mock factory can use get_configurable_context."""
        from stuntdouble import MockToolsRegistry, get_configurable_context

        registry = MockToolsRegistry()

        def user_aware_factory(scenario_metadata, config=None):
            ctx = get_configurable_context(config)
            user_id = ctx.get("agent_context", {}).get("user_id", "anonymous")
            return lambda: {"user_id": user_id}

        registry.register("user_tool", mock_fn=user_aware_factory)

        # Test with config containing user_id
        config_with_user = {"configurable": {"agent_context": {"user_id": "alice"}}}
        mock_fn = registry.resolve("user_tool", {}, config=config_with_user)
        assert mock_fn is not None
        assert mock_fn() == {"user_id": "alice"}

        # Test without config
        mock_fn = registry.resolve("user_tool", {}, config=None)
        assert mock_fn is not None
        assert mock_fn() == {"user_id": "anonymous"}

    def test_mock_factory_selects_user_specific_data(self):
        """Test that mock factory can select user-specific mock data."""
        from stuntdouble import MockToolsRegistry, get_configurable_context

        registry = MockToolsRegistry()

        def lending_factors_factory(scenario_metadata, config=None):
            ctx = get_configurable_context(config)
            user_id = ctx.get("agent_context", {}).get("user_id")

            mock_data = scenario_metadata.get("mocks", {}).get(
                "get_lending_factors", {}
            )
            user_data = mock_data.get(user_id, mock_data.get("default", {}))

            return lambda: user_data

        registry.register("get_lending_factors", mock_fn=lending_factors_factory)

        scenario_metadata = {
            "mocks": {
                "get_lending_factors": {
                    "user_excellent": {"approval_segment": "Excellent"},
                    "user_poor": {"approval_segment": "Poor"},
                    "default": {"approval_segment": "Fair"},
                }
            }
        }

        # Test excellent user
        config_excellent = {
            "configurable": {"agent_context": {"user_id": "user_excellent"}}
        }
        mock_fn = registry.resolve(
            "get_lending_factors", scenario_metadata, config=config_excellent
        )
        assert mock_fn is not None
        assert mock_fn() == {"approval_segment": "Excellent"}

        # Test poor user
        config_poor = {"configurable": {"agent_context": {"user_id": "user_poor"}}}
        mock_fn = registry.resolve(
            "get_lending_factors", scenario_metadata, config=config_poor
        )
        assert mock_fn is not None
        assert mock_fn() == {"approval_segment": "Poor"}

        # Test unknown user gets default
        config_unknown = {"configurable": {"agent_context": {"user_id": "unknown"}}}
        mock_fn = registry.resolve(
            "get_lending_factors", scenario_metadata, config=config_unknown
        )
        assert mock_fn is not None
        assert mock_fn() == {"approval_segment": "Fair"}
