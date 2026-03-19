"""
Unit tests for create_mockable_tool_wrapper.

Tests the mockable tool wrapper factory and its behavior.
"""

import asyncio
from unittest.mock import MagicMock

import pytest


def run_async(coro):
    """Helper to run async code in sync tests."""
    return asyncio.run(coro)


def create_mock_tool_runtime(config: dict | None = None):
    """Create a mock ToolRuntime for testing."""
    from langgraph.prebuilt.tool_node import ToolRuntime

    return ToolRuntime(
        state={},
        context=None,
        config=config or {},
        stream_writer=None,
        tool_call_id=None,
        store=None,
    )


class TestCreateMockableToolWrapper:
    """Tests for create_mockable_tool_wrapper factory."""

    def _create_request(
        self,
        tool_name: str = "test_tool",
        tool_args: dict | None = None,
        scenario_metadata: dict | None = None,
    ):
        """Create a mock ToolCallRequest using native LangGraph types."""
        from langgraph.prebuilt.tool_node import ToolCallRequest

        tool_call = {
            "name": tool_name,
            "args": tool_args or {},
            "id": "call-123",
        }

        config = {}
        if scenario_metadata is not None:
            config = {"configurable": {"scenario_metadata": scenario_metadata}}

        tool = MagicMock()
        tool.name = tool_name

        runtime = create_mock_tool_runtime(config)

        return ToolCallRequest(
            tool_call=tool_call,
            tool=tool,
            state={},
            runtime=runtime,
        )

    def test_creates_callable_wrapper(self):
        """Test that factory returns a callable wrapper."""
        from stuntdouble import MockToolsRegistry
        from stuntdouble.wrapper import create_mockable_tool_wrapper

        registry = MockToolsRegistry()
        wrapper = create_mockable_tool_wrapper(registry)

        assert callable(wrapper)

    def test_no_scenario_metadata_calls_execute(self):
        """Test that without scenario_metadata, execute is called."""
        from langchain_core.messages import ToolMessage

        from stuntdouble import MockToolsRegistry
        from stuntdouble.wrapper import create_mockable_tool_wrapper

        registry = MockToolsRegistry()
        wrapper = create_mockable_tool_wrapper(registry)

        request = self._create_request(scenario_metadata=None)

        execute_called = False
        expected_result = ToolMessage(
            content="real_result",
            name="test_tool",
            tool_call_id="call-123",
        )

        async def mock_execute(req):
            nonlocal execute_called
            execute_called = True
            return expected_result

        result = run_async(wrapper(request, mock_execute))

        assert execute_called is True
        assert result == expected_result

    def test_with_mock_returns_mocked_result(self):
        """Test that with scenario_metadata and mock, mocked result is returned."""
        from stuntdouble import MockToolsRegistry
        from stuntdouble.wrapper import create_mockable_tool_wrapper

        registry = MockToolsRegistry()
        registry.register(
            "test_tool",
            mock_fn=lambda md: lambda **kw: {"mocked": True, **kw},
        )

        wrapper = create_mockable_tool_wrapper(registry)

        request = self._create_request(
            tool_args={"city": "NYC"},
            scenario_metadata={"mode": "mock"},
        )

        async def mock_execute(req):
            raise AssertionError("Execute should not be called")

        result = run_async(wrapper(request, mock_execute))

        assert result.status == "success"
        assert "mocked" in result.content
        assert "NYC" in result.content

    def test_missing_mock_raises_error_in_strict_mode(self):
        """Test that missing mock raises MissingMockError in strict mode."""
        from stuntdouble import (
            MissingMockError,
            MockToolsRegistry,
            create_mockable_tool_wrapper,
        )

        registry = MockToolsRegistry()
        # No mock registered for test_tool

        wrapper = create_mockable_tool_wrapper(
            registry,
            require_mock_when_scenario=True,
        )

        request = self._create_request(scenario_metadata={"mode": "mock"})

        async def mock_execute(req):
            raise AssertionError("Execute should not be called")

        with pytest.raises(MissingMockError) as exc_info:
            run_async(wrapper(request, mock_execute))

        assert exc_info.value.tool_name == "test_tool"

    def test_missing_mock_falls_back_in_lenient_mode(self):
        """Test that missing mock falls back to execute in lenient mode."""
        from langchain_core.messages import ToolMessage

        from stuntdouble import MockToolsRegistry
        from stuntdouble.wrapper import create_mockable_tool_wrapper

        registry = MockToolsRegistry()
        # No mock registered for test_tool

        wrapper = create_mockable_tool_wrapper(
            registry,
            require_mock_when_scenario=False,  # Lenient mode
        )

        request = self._create_request(scenario_metadata={"mode": "mock"})

        execute_called = False
        expected_result = ToolMessage(
            content="fallback_result",
            name="test_tool",
            tool_call_id="call-123",
        )

        async def mock_execute(req):
            nonlocal execute_called
            execute_called = True
            return expected_result

        result = run_async(wrapper(request, mock_execute))

        assert execute_called is True
        assert result == expected_result

    def test_mock_error_returns_error_message(self):
        """Test that mock execution errors return error ToolMessage."""
        from stuntdouble import MockToolsRegistry
        from stuntdouble.wrapper import create_mockable_tool_wrapper

        registry = MockToolsRegistry()

        def failing_mock(**kwargs):
            raise ValueError("Mock failed")

        registry.register(
            "test_tool",
            mock_fn=lambda md: failing_mock,
        )

        wrapper = create_mockable_tool_wrapper(registry)

        request = self._create_request(scenario_metadata={"mode": "mock"})

        async def mock_execute(req):
            raise AssertionError("Execute should not be called")

        result = run_async(wrapper(request, mock_execute))

        assert result.status == "error"
        assert "Mock error" in result.content

    def test_strict_mock_errors_reraises(self):
        """Test that strict_mock_errors=True re-raises mock exceptions."""
        from stuntdouble import MockToolsRegistry
        from stuntdouble.wrapper import create_mockable_tool_wrapper

        registry = MockToolsRegistry()

        def failing_mock(**kwargs):
            raise ValueError("Mock failed")

        registry.register(
            "test_tool",
            mock_fn=lambda md: failing_mock,
        )

        wrapper = create_mockable_tool_wrapper(registry, strict_mock_errors=True)

        request = self._create_request(scenario_metadata={"mode": "mock"})

        async def mock_execute(req):
            raise AssertionError("Execute should not be called")

        with pytest.raises(ValueError, match="Mock failed"):
            run_async(wrapper(request, mock_execute))

    def test_input_not_matched_raises_missing_mock_in_strict_mode(self):
        """Test that InputNotMatchedError from builder triggers MissingMockError."""
        from stuntdouble import (
            MissingMockError,
            MockToolsRegistry,
            create_mockable_tool_wrapper,
        )

        registry = MockToolsRegistry()
        registry.mock("test_tool").when(status="active").returns({"bills": []})

        wrapper = create_mockable_tool_wrapper(registry, require_mock_when_scenario=True)

        request = self._create_request(
            tool_args={"status": "inactive"},
            scenario_metadata={"mode": "mock"},
        )

        async def mock_execute(req):
            raise AssertionError("Execute should not be called")

        with pytest.raises(MissingMockError, match="conditions were not met"):
            run_async(wrapper(request, mock_execute))

    def test_input_not_matched_falls_back_in_lenient_mode(self):
        """Test that InputNotMatchedError falls back to real tool in lenient mode."""
        from langchain_core.messages import ToolMessage

        from stuntdouble import MockToolsRegistry
        from stuntdouble.wrapper import create_mockable_tool_wrapper

        registry = MockToolsRegistry()
        registry.mock("test_tool").when(status="active").returns({"bills": []})

        wrapper = create_mockable_tool_wrapper(registry, require_mock_when_scenario=False)

        request = self._create_request(
            tool_args={"status": "inactive"},
            scenario_metadata={"mode": "mock"},
        )

        expected_result = ToolMessage(
            content="real_result",
            name="test_tool",
            tool_call_id="call-123",
        )

        async def mock_execute(req):
            return expected_result

        result = run_async(wrapper(request, mock_execute))
        assert result == expected_result

    def test_mock_with_dict_result(self):
        """Test that dict mock results are JSON-serialized."""
        from stuntdouble import MockToolsRegistry
        from stuntdouble.wrapper import create_mockable_tool_wrapper

        registry = MockToolsRegistry()
        registry.register(
            "test_tool",
            mock_fn=lambda md: lambda: {"customers": [{"name": "Test"}]},
        )

        wrapper = create_mockable_tool_wrapper(registry)
        request = self._create_request(scenario_metadata={"mode": "mock"})

        async def mock_execute(req):
            raise AssertionError("Execute should not be called")

        result = run_async(wrapper(request, mock_execute))

        assert "customers" in result.content
        assert "Test" in result.content

    def test_mock_with_string_result(self):
        """Test that string mock results are used directly."""
        from stuntdouble import MockToolsRegistry
        from stuntdouble.wrapper import create_mockable_tool_wrapper

        registry = MockToolsRegistry()
        registry.register(
            "test_tool",
            mock_fn=lambda md: lambda: "Simple string result",
        )

        wrapper = create_mockable_tool_wrapper(registry)
        request = self._create_request(scenario_metadata={"mode": "mock"})

        async def mock_execute(req):
            raise AssertionError("Execute should not be called")

        result = run_async(wrapper(request, mock_execute))

        assert result.content == "Simple string result"

    def test_async_mock_function(self):
        """Test that async mock functions are awaited."""
        from stuntdouble import MockToolsRegistry
        from stuntdouble.wrapper import create_mockable_tool_wrapper

        registry = MockToolsRegistry()

        async def async_mock(**kwargs):
            return {"async_result": True}

        registry.register(
            "test_tool",
            mock_fn=lambda md: async_mock,
        )

        wrapper = create_mockable_tool_wrapper(registry)
        request = self._create_request(scenario_metadata={"mode": "mock"})

        async def mock_execute(req):
            raise AssertionError("Execute should not be called")

        result = run_async(wrapper(request, mock_execute))

        assert "async_result" in result.content


class TestWrapperIntegration:
    """Integration tests for wrapper with registry."""

    def _create_request(
        self,
        tool_name: str = "test_tool",
        tool_args: dict | None = None,
        scenario_metadata: dict | None = None,
    ):
        """Create a mock ToolCallRequest using native LangGraph types."""
        from langgraph.prebuilt.tool_node import ToolCallRequest

        tool_call = {
            "name": tool_name,
            "args": tool_args or {},
            "id": "call-123",
        }

        config = {}
        if scenario_metadata is not None:
            config = {"configurable": {"scenario_metadata": scenario_metadata}}

        tool = MagicMock()
        tool.name = tool_name

        runtime = create_mock_tool_runtime(config)

        return ToolCallRequest(
            tool_call=tool_call,
            tool=tool,
            state={},
            runtime=runtime,
        )

    def test_when_predicate_respected(self):
        """Test that registry when predicate is respected."""
        from langchain_core.messages import ToolMessage

        from stuntdouble import MockToolsRegistry
        from stuntdouble.wrapper import create_mockable_tool_wrapper

        registry = MockToolsRegistry()
        registry.register(
            "conditional_tool",
            mock_fn=lambda md: lambda: "mocked",
            when=lambda md: md.get("mode") == "mock",
        )

        wrapper = create_mockable_tool_wrapper(
            registry,
            require_mock_when_scenario=False,
        )

        # When predicate returns True (mode=mock)
        request_mock = self._create_request(
            tool_name="conditional_tool",
            scenario_metadata={"mode": "mock"},
        )

        async def mock_execute(req):
            return ToolMessage(
                content="real",
                name=req.tool_call["name"],
                tool_call_id="123",
            )

        result = run_async(wrapper(request_mock, mock_execute))
        assert result.content == "mocked"

        # When predicate returns False (mode=real)
        request_real = self._create_request(
            tool_name="conditional_tool",
            scenario_metadata={"mode": "real"},
        )

        result = run_async(wrapper(request_real, mock_execute))
        assert result.content == "real"


class TestConfigPassingToMockFactory:
    """Tests for passing config to mock factories."""

    def _create_request(
        self,
        tool_name: str = "test_tool",
        tool_args: dict | None = None,
        scenario_metadata: dict | None = None,
        agent_context: dict | None = None,
    ):
        """Create a mock ToolCallRequest with optional agent_context in config."""
        from langgraph.prebuilt.tool_node import ToolCallRequest

        tool_call = {
            "name": tool_name,
            "args": tool_args or {},
            "id": "call-123",
        }

        config = {}
        configurable = {}
        if scenario_metadata is not None:
            configurable["scenario_metadata"] = scenario_metadata
        if agent_context is not None:
            configurable["agent_context"] = agent_context
        if configurable:
            config = {"configurable": configurable}

        tool = MagicMock()
        tool.name = tool_name

        runtime = create_mock_tool_runtime(config)

        return ToolCallRequest(
            tool_call=tool_call,
            tool=tool,
            state={},
            runtime=runtime,
        )

    def test_old_factory_signature_still_works(self):
        """Test that old mock factories with 1 param still work."""
        from stuntdouble import MockToolsRegistry
        from stuntdouble.wrapper import create_mockable_tool_wrapper

        registry = MockToolsRegistry()

        # Old-style factory: only takes scenario_metadata
        def old_style_factory(scenario_metadata):
            return lambda: {"old_style": True}

        registry.register("test_tool", mock_fn=old_style_factory)

        wrapper = create_mockable_tool_wrapper(registry)
        request = self._create_request(scenario_metadata={"mode": "mock"})

        async def mock_execute(req):
            raise AssertionError("Execute should not be called")

        result = run_async(wrapper(request, mock_execute))

        assert "old_style" in result.content

    def test_new_factory_signature_receives_config(self):
        """Test that new mock factories with 2 params receive config."""
        from stuntdouble import MockToolsRegistry
        from stuntdouble.wrapper import create_mockable_tool_wrapper

        registry = MockToolsRegistry()

        received_config = None

        # New-style factory: takes scenario_metadata and config
        def new_style_factory(scenario_metadata, config=None):
            nonlocal received_config
            received_config = config
            return lambda: {"new_style": True}

        registry.register("test_tool", mock_fn=new_style_factory)

        wrapper = create_mockable_tool_wrapper(registry)
        request = self._create_request(
            scenario_metadata={"mode": "mock"},
            agent_context={"user_id": "user_123"},
        )

        async def mock_execute(req):
            raise AssertionError("Execute should not be called")

        result = run_async(wrapper(request, mock_execute))

        assert "new_style" in result.content
        assert received_config is not None
        assert "configurable" in received_config
        assert received_config["configurable"]["agent_context"]["user_id"] == "user_123"

    def test_factory_with_kwargs_receives_config(self):
        """Test that factory with **kwargs receives config via kwargs."""
        from stuntdouble import MockToolsRegistry
        from stuntdouble.wrapper import create_mockable_tool_wrapper

        registry = MockToolsRegistry()

        received_kwargs = None

        # Factory with **kwargs
        def kwargs_factory(scenario_metadata, **kwargs):
            nonlocal received_kwargs
            received_kwargs = kwargs
            return lambda: {"kwargs_style": True}

        registry.register("test_tool", mock_fn=kwargs_factory)

        wrapper = create_mockable_tool_wrapper(registry)
        request = self._create_request(
            scenario_metadata={"mode": "mock"},
            agent_context={"user_id": "user_456"},
        )

        async def mock_execute(req):
            raise AssertionError("Execute should not be called")

        result = run_async(wrapper(request, mock_execute))

        assert "kwargs_style" in result.content
        # Config should be passed as second positional arg, not in kwargs
        # sig.bind({}, {}) succeeds, so it's called with 2 args

    def test_context_aware_mock_returns_user_specific_data(self):
        """Test that context-aware mocks can return user-specific data."""
        from stuntdouble import (
            MockToolsRegistry,
            create_mockable_tool_wrapper,
            get_configurable_context,
        )

        registry = MockToolsRegistry()

        # Context-aware factory that returns different data per user
        def user_aware_factory(scenario_metadata, config=None):
            ctx = get_configurable_context(config)
            agent_context = ctx.get("agent_context", {})
            user_id = agent_context.get("user_id")

            mock_data = scenario_metadata.get("mocks", {}).get("test_tool", {})
            user_data = mock_data.get(user_id, mock_data.get("default", {}))

            return lambda: user_data

        registry.register("test_tool", mock_fn=user_aware_factory)

        wrapper = create_mockable_tool_wrapper(registry)

        # Test user_123 gets their specific data
        request_user_123 = self._create_request(
            scenario_metadata={
                "mode": "mock",
                "mocks": {
                    "test_tool": {
                        "user_123": {"approval": "Excellent"},
                        "user_456": {"approval": "Poor"},
                        "default": {"approval": "Fair"},
                    }
                },
            },
            agent_context={"user_id": "user_123"},
        )

        async def mock_execute(req):
            raise AssertionError("Execute should not be called")

        result = run_async(wrapper(request_user_123, mock_execute))
        assert "Excellent" in result.content

        # Test user_456 gets their specific data
        request_user_456 = self._create_request(
            scenario_metadata={
                "mode": "mock",
                "mocks": {
                    "test_tool": {
                        "user_123": {"approval": "Excellent"},
                        "user_456": {"approval": "Poor"},
                        "default": {"approval": "Fair"},
                    }
                },
            },
            agent_context={"user_id": "user_456"},
        )

        result = run_async(wrapper(request_user_456, mock_execute))
        assert "Poor" in result.content

        # Test unknown user gets default data
        request_unknown = self._create_request(
            scenario_metadata={
                "mode": "mock",
                "mocks": {
                    "test_tool": {
                        "user_123": {"approval": "Excellent"},
                        "user_456": {"approval": "Poor"},
                        "default": {"approval": "Fair"},
                    }
                },
            },
            agent_context={"user_id": "unknown_user"},
        )

        result = run_async(wrapper(request_unknown, mock_execute))
        assert "Fair" in result.content

    def test_no_arg_tool_mock_with_config(self):
        """Test that no-arg tool mocks can access config for context."""
        from stuntdouble import (
            MockToolsRegistry,
            create_mockable_tool_wrapper,
            get_configurable_context,
        )

        registry = MockToolsRegistry()

        # No-arg tool mock that uses config for user context
        def no_arg_factory(scenario_metadata, config=None):
            ctx = get_configurable_context(config)
            user_id = ctx.get("agent_context", {}).get("user_id", "anonymous")

            # No-arg callable
            def mock_callable():
                return {"user_id": user_id, "message": f"Hello, {user_id}!"}

            return mock_callable

        registry.register("get_current_user", mock_fn=no_arg_factory)

        wrapper = create_mockable_tool_wrapper(registry)

        request = self._create_request(
            tool_name="get_current_user",
            tool_args={},  # No args
            scenario_metadata={"mode": "mock"},
            agent_context={"user_id": "alice"},
        )

        async def mock_execute(req):
            raise AssertionError("Execute should not be called")

        result = run_async(wrapper(request, mock_execute))

        assert "alice" in result.content
        assert "Hello" in result.content


class TestDefaultRegistryAndWrapper:
    """Tests for default_registry and mockable_tool_wrapper."""

    def test_default_registry_exists(self):
        """Test that default_registry is available."""
        from stuntdouble import default_registry

        assert default_registry is not None

    def test_mockable_tool_wrapper_exists(self):
        """Test that mockable_tool_wrapper is available."""
        from stuntdouble import mockable_tool_wrapper

        assert mockable_tool_wrapper is not None
        assert callable(mockable_tool_wrapper)

    def test_mockable_tool_wrapper_uses_default_registry(self):
        """Test that mockable_tool_wrapper uses default_registry."""
        from langchain_core.messages import ToolMessage
        from langgraph.prebuilt.tool_node import ToolCallRequest

        from stuntdouble import default_registry, mockable_tool_wrapper

        # Register a mock on default registry
        default_registry.register(
            "default_registry_tool",
            mock_fn=lambda md: lambda: {"from_default": True},
        )

        try:
            tool_call = {"name": "default_registry_tool", "args": {}, "id": "call-1"}
            tool = MagicMock()
            tool.name = "default_registry_tool"
            runtime = create_mock_tool_runtime({"configurable": {"scenario_metadata": {"mode": "mock"}}})
            request = ToolCallRequest(
                tool_call=tool_call,
                tool=tool,
                state={},
                runtime=runtime,
            )

            async def mock_execute(req):
                return ToolMessage(content="real", name="test", tool_call_id="1")

            result = run_async(mockable_tool_wrapper(request, mock_execute))
            assert "from_default" in result.content
        finally:
            # Clean up
            default_registry.unregister("default_registry_tool")
