# ABOUTME: Handles reading and writing scenario metadata in LangGraph RunnableConfig objects.
# ABOUTME: Provides helpers that bridge StuntDouble's config format with runtime tool requests.
"""
Scenario metadata configuration utilities.

Provides helper functions for extracting and injecting scenario_metadata
into LangGraph RunnableConfig for use with the mockable tool wrapper.
"""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt.tool_node import ToolCallRequest


def get_scenario_metadata(request: ToolCallRequest) -> dict[str, Any] | None:
    """
    Extract scenario_metadata from a native ToolCallRequest.

    Accesses config via request.runtime.config as per LangGraph 1.0.5 API.

    Args:
        request: Native ToolCallRequest from langgraph.prebuilt.tool_node

    Returns:
        The scenario_metadata dict if present, None otherwise

    Example:
        >>> async def my_wrapper(request: ToolCallRequest, execute):
        ...     metadata = get_scenario_metadata(request)
        ...     if metadata:
        ...         # Handle mocked scenario
        ...         pass
        ...     return await execute(request)
    """
    if not request.runtime or not request.runtime.config:
        return None
    configurable = request.runtime.config.get("configurable", {})
    if not isinstance(configurable, dict):
        return None
    return configurable.get("scenario_metadata")


def inject_scenario_metadata(
    config: RunnableConfig | None,
    metadata: dict[str, Any],
) -> RunnableConfig:
    """
    Create a new RunnableConfig with scenario_metadata injected.

    This is a helper for creating configs to pass to graph.ainvoke()
    that include scenario_metadata for the mockable tool wrapper.

    Args:
        config: Base RunnableConfig to extend (can be None or empty dict)
        metadata: The scenario_metadata dict to inject

    Returns:
        New RunnableConfig with scenario_metadata in configurable

    Example:
        >>> from stuntdouble import inject_scenario_metadata
        >>>
        >>> # Create config with scenario_metadata
        >>> config = inject_scenario_metadata({}, {
        ...     "scenario_id": "test-001",
        ...     "mocks": {
        ...         "get_weather": [{"output": {"temp": 72}}]
        ...     }
        ... })
        >>>
        >>> # Use in graph invocation
        >>> result = await graph.ainvoke(state, config=config)
    """
    base_config = config or {}
    existing_configurable = base_config.get("configurable", {})

    return {
        **base_config,
        "configurable": {
            **existing_configurable,
            "scenario_metadata": metadata,
        },
    }


def extract_scenario_metadata_from_config(
    config: RunnableConfig | None,
) -> dict[str, Any] | None:
    """
    Extract scenario_metadata directly from a RunnableConfig.

    This is useful when you have a config but not a ToolCallRequest,
    such as in middleware or pre-processing steps.

    Args:
        config: RunnableConfig that may contain scenario_metadata

    Returns:
        The scenario_metadata dict if present, None otherwise

    Example:
        >>> config = {"configurable": {"scenario_metadata": {"mode": "mock"}}}
        >>> metadata = extract_scenario_metadata_from_config(config)
        >>> print(metadata)  # {"mode": "mock"}
    """
    if not config:
        return None
    configurable = config.get("configurable", {})
    if not isinstance(configurable, dict):
        return None
    return configurable.get("scenario_metadata")


def get_configurable_context(config: dict[str, Any] | None) -> dict[str, Any]:
    """
    Extract the configurable context from RunnableConfig.

    Returns the full 'configurable' dict from the config, allowing mock factories
    to access any runtime context (agent_context, thread_id, custom fields, etc.).

    This is a generic helper that doesn't assume any specific structure within
    the configurable dict. Consumer applications handle their own extraction
    logic for specific fields.

    Args:
        config: RunnableConfig from LangGraph runtime

    Returns:
        The configurable dict (empty dict if not available)

    Example:
        >>> def my_mock(scenario_metadata: dict, config: dict = None) -> Callable:
        ...     ctx = get_configurable_context(config)
        ...     agent_context = ctx.get("agent_context")
        ...     thread_id = ctx.get("thread_id")
        ...     # Consumer-specific extraction logic here
        ...     return lambda: {"data": "mocked"}
        >>>
        >>> # Access any field your application puts in configurable
        >>> ctx = get_configurable_context(config)
        >>> user_context = ctx.get("user_context")  # Custom field
        >>> session_id = ctx.get("session_id")  # Custom field
    """
    if not config:
        return {}

    configurable = config.get("configurable", {})
    return configurable if isinstance(configurable, dict) else {}


__all__ = [
    "get_scenario_metadata",
    "inject_scenario_metadata",
    "extract_scenario_metadata_from_config",
    "get_configurable_context",
]
