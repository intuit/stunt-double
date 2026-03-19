"""
Mockable tool wrapper for conditional mocking based on scenario_metadata.

Provides the create_mockable_tool_wrapper factory function that creates
a wrapper suitable for use with native ToolNode's awrap_tool_call parameter.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, cast

from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool
from langgraph.prebuilt.tool_node import (
    AsyncToolCallWrapper,
    ToolCallRequest,
)
from langgraph.types import Command

from stuntdouble.exceptions import InputNotMatchedError, MissingMockError
from stuntdouble.mock_registry import MockToolsRegistry

from stuntdouble.config import get_scenario_metadata

if TYPE_CHECKING:
    from stuntdouble.recorder import CallRecorder

logger = logging.getLogger(__name__)


def create_mockable_tool_wrapper(
    registry: MockToolsRegistry,
    *,
    require_mock_when_scenario: bool = True,
    strict_mock_errors: bool = False,
    tools: list[BaseTool] | None = None,
    validate_signatures: bool = True,
    recorder: CallRecorder | None = None,
) -> AsyncToolCallWrapper:
    """
    Create a tool wrapper for conditional mocking based on scenario_metadata.

    The wrapper checks for scenario_metadata in config.configurable and
    conditionally routes tool calls to registered mocks.

    Flow:
    1. Check if scenario_metadata exists in runtime.config.configurable
    2. If no scenario_metadata → execute real tool via execute(request)
    3. If scenario_metadata present:
       a. Try to resolve mock from registry
       b. If tools provided and validate_signatures=True → validate mock signature
       c. If mock exists and valid → execute mock and return ToolMessage
       d. If no mock → raise MissingMockError or fallback to real tool

    Args:
        registry: MockToolsRegistry with registered mock factories
        require_mock_when_scenario: If True (default), raise MissingMockError
            when scenario_metadata is present but no mock exists for a tool.
            If False, fall back to executing the real tool.
        strict_mock_errors: If True, re-raise exceptions from mock execution
            instead of catching them and returning ToolMessage(status="error").
            Useful in unit tests where you want fast failure on broken mocks.
            If False (default), mock errors are caught and returned as error
            ToolMessages, which is suitable for evaluation batch runs.
        tools: Optional list of BaseTool instances. If provided with
            validate_signatures=True, the wrapper validates that mock function
            signatures match the original tool signatures at runtime.
        validate_signatures: If True (default) and tools are provided, validates
            mock signatures at runtime. On validation failure, logs an error
            and falls back to the real tool.
        recorder: Optional CallRecorder for recording tool calls. When provided,
            all tool calls (mocked and real) will be recorded for later
            verification in tests.

    Returns:
        Async wrapper function suitable for native ToolNode.awrap_tool_call

    Example:
        >>> from langgraph.prebuilt import ToolNode
        >>> from stuntdouble import (
        ...     MockToolsRegistry,
        ...     create_mockable_tool_wrapper,
        ...     CallRecorder,
        ... )
        >>>
        >>> registry = MockToolsRegistry()
        >>> registry.register(
        ...     "get_weather",
        ...     mock_fn=lambda md: lambda city: {"temp": 72, "city": city}
        ... )
        >>>
        >>> # With recording
        >>> recorder = CallRecorder()
        >>> wrapper = create_mockable_tool_wrapper(registry, recorder=recorder)
        >>> node = ToolNode(tools, awrap_tool_call=wrapper)
        >>>
        >>> # When invoked with scenario_metadata in config, mocks are used
        >>> config = {"configurable": {"scenario_metadata": {"mode": "mock"}}}
        >>> result = await graph.ainvoke(state, config=config)
        >>>
        >>> # Verify calls
        >>> recorder.assert_called("get_weather")

    Strict Mode (require_mock_when_scenario=True):
        In evaluation scenarios, you typically want all tool calls to be mocked.
        Strict mode catches configuration errors by raising MissingMockError
        when a tool is called but no mock is registered.

        >>> wrapper = create_mockable_tool_wrapper(registry, require_mock_when_scenario=True)
        >>> # If "unknown_tool" is called with scenario_metadata -> MissingMockError

    Lenient Mode (require_mock_when_scenario=False):
        Useful during development or hybrid testing where some tools should
        use real implementations even when scenario_metadata is present.

        >>> wrapper = create_mockable_tool_wrapper(registry, require_mock_when_scenario=False)
        >>> # If "unknown_tool" is called with scenario_metadata -> real tool executes

    Signature Validation:
        When tools are provided with validate_signatures=True, the wrapper
        validates mock signatures at runtime to catch configuration errors.

        >>> wrapper = create_mockable_tool_wrapper(
        ...     registry,
        ...     tools=all_tools,
        ...     validate_signatures=True,
        ... )
        >>> # If mock signature doesn't match tool -> logs error, uses real tool
    """
    # Build tools lookup map for runtime signature validation
    tools_by_name: dict[str, BaseTool] = {}
    if tools is not None:
        tools_by_name = {t.name: t for t in tools}

    async def mockable_tool_wrapper(
        request: ToolCallRequest,
        execute: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
    ) -> ToolMessage | Command:
        """
        Wrapper that conditionally mocks tools based on scenario_metadata in config.

        Args:
            request: Native ToolCallRequest with tool call context
            execute: Callback to execute the real tool

        Returns:
            ToolMessage or Command from mock or real tool execution

        Raises:
            MissingMockError: If require_mock_when_scenario=True and no mock found
        """
        # Extract fields from native ToolCallRequest
        tool_call = request.tool_call
        tool_name = tool_call["name"]
        tool_args = tool_call.get("args", {})
        tool_call_id = tool_call["id"]
        scenario_metadata = get_scenario_metadata(request)
        scenario_id = (
            scenario_metadata.get("scenario_id", "unknown")
            if scenario_metadata
            else None
        )

        # Helper to record calls - wrapped in try-except to never mask original errors
        def _record_call(
            result: Any = None,
            error: Exception | None = None,
            was_mocked: bool = False,
            start_time: float | None = None,
        ) -> None:
            if recorder is not None:
                try:
                    duration_ms = (
                        (time.time() - start_time) * 1000
                        if start_time is not None
                        else 0.0
                    )
                    recorder.record(
                        tool_name=tool_name,
                        args=tool_args,
                        result=result,
                        error=error,
                        duration_ms=duration_ms,
                        was_mocked=was_mocked,
                        scenario_id=scenario_id,
                    )
                except Exception as recording_error:
                    # Log but don't raise - recording should never interfere
                    # with actual tool execution or error propagation
                    logger.warning(
                        f"Failed to record call for '{tool_name}': {recording_error}"
                    )

        # No scenario_metadata → use real tool
        if not scenario_metadata:
            logger.debug(f"No scenario_metadata, executing real tool '{tool_name}'")
            start_time = time.time()
            try:
                result = await execute(request)
                _record_call(result=result, was_mocked=False, start_time=start_time)
                return result
            except Exception as e:
                _record_call(error=e, was_mocked=False, start_time=start_time)
                raise

        # Extract config for passing to mock factories (enables context-aware mocks)
        # Cast RunnableConfig (TypedDict) to plain dict for registry API compatibility
        config: dict[str, Any] | None = (
            cast(dict[str, Any], request.runtime.config) if request.runtime else None
        )

        # Try to resolve mock from registry
        mock_callable = registry.resolve(tool_name, scenario_metadata, config)
        no_match_reason: str | None = None

        if mock_callable is not None:
            # Runtime signature validation if tools are provided
            if validate_signatures and tool_name in tools_by_name:
                from stuntdouble.validation import validate_mock_signature

                tool = tools_by_name[tool_name]
                mock_fn = registry.get_mock_fn(tool_name)
                if mock_fn:
                    is_valid, error_msg = validate_mock_signature(
                        tool, mock_fn, scenario_metadata, config
                    )
                    if not is_valid:
                        from stuntdouble.exceptions import SignatureMismatchError

                        logger.error(
                            f"Mock signature mismatch for '{tool_name}': {error_msg}"
                        )
                        raise SignatureMismatchError(
                            tool_name=tool_name,
                            expected=f"tool '{tool_name}' parameters",
                            actual=error_msg or "unknown mismatch",
                        )

            logger.info(f"Using mock for tool '{tool_name}' (scenario: {scenario_id})")

            start_time = time.time()
            try:
                mock_result = mock_callable(**tool_args)

                if hasattr(mock_result, "__await__"):
                    mock_result = await mock_result

                content = _format_mock_result(mock_result)

                tool_message = ToolMessage(
                    content=content,
                    name=tool_name,
                    tool_call_id=tool_call_id,
                    status="success",
                )

                _record_call(result=mock_result, was_mocked=True, start_time=start_time)
                return tool_message

            except InputNotMatchedError as e:
                no_match_reason = str(e)
                logger.info(
                    f"Mock conditions not met for '{tool_name}' "
                    f"(scenario: {scenario_id}): {e}"
                )
                _record_call(error=e, was_mocked=True, start_time=start_time)
                # Fall through to "no mock" handling below

            except Exception as e:
                if strict_mock_errors:
                    _record_call(error=e, was_mocked=True, start_time=start_time)
                    raise
                logger.exception(
                    f"Error in mock for tool '{tool_name}' (scenario: {scenario_id}): {e}"
                )
                _record_call(error=e, was_mocked=True, start_time=start_time)
                return ToolMessage(
                    content=f"Mock error: {str(e)}",
                    name=tool_name,
                    tool_call_id=tool_call_id,
                    status="error",
                )

        # No mock registered for this tool, or mock conditions not met
        if require_mock_when_scenario:
            if no_match_reason:
                logger.error(
                    f"Mock for tool '{tool_name}' registered but conditions not met "
                    f"(scenario: {scenario_id})"
                )
                raise MissingMockError(
                    tool_name,
                    message=(
                        f"Mock for tool '{tool_name}' is registered but its input conditions "
                        f"were not met: {no_match_reason}. Add a catch-all case or adjust "
                        f"your mock conditions."
                    ),
                )
            logger.error(
                f"No mock registered for tool '{tool_name}' but scenario_metadata present "
                f"(scenario: {scenario_id})"
            )
            raise MissingMockError(tool_name)
        else:
            logger.warning(
                f"No mock for '{tool_name}' with scenario_metadata present "
                f"(scenario: {scenario_id}), falling back to real tool"
            )
            start_time = time.time()
            try:
                result = await execute(request)
                _record_call(result=result, was_mocked=False, start_time=start_time)
                return result
            except Exception as e:
                _record_call(error=e, was_mocked=False, start_time=start_time)
                raise

    return mockable_tool_wrapper


def _format_mock_result(result: Any) -> str:
    """
    Format mock result as ToolMessage content.

    Args:
        result: Raw result from mock function

    Returns:
        String content suitable for ToolMessage
    """
    if isinstance(result, str):
        return result
    elif isinstance(result, dict) or isinstance(result, list):
        try:
            return json.dumps(result, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(result)
    else:
        return str(result)


# ============================================================================
# DEFAULT REGISTRY AND PRE-CONFIGURED WRAPPER
# ============================================================================

# Default registry for simple use cases where a single global registry is sufficient
default_registry = MockToolsRegistry()

# Pre-configured wrapper using the default registry.
# Users can import and use this directly without creating their own registry.
mockable_tool_wrapper = create_mockable_tool_wrapper(default_registry)


__all__ = [
    "create_mockable_tool_wrapper",
    "get_scenario_metadata",
    "default_registry",
    "mockable_tool_wrapper",
]
