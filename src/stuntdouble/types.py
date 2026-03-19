"""
Shared type definitions for the StuntDouble mocking system.

Types are self-contained with no dependencies on existing StuntDouble models.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, TypedDict, runtime_checkable


class ScenarioMetadata(TypedDict, total=False):
    """
    Type definition for scenario metadata passed via RunnableConfig.

    The system treats this as an opaque JSON object. These are recommended
    conventions but not enforced by the mocking system.

    Attributes:
        scenario_id: Unique identifier for the scenario
        mode: Operating mode - "mock", "real", or custom values
        mocks: Tool-specific mock data keyed by tool name

    Example:
        {
            "scenario_id": "test-001",
            "mode": "mock",
            "mocks": {
                "get_weather": [{"output": {"temp": 72, "conditions": "sunny"}}]
            }
        }
    """

    scenario_id: str
    mode: str
    mocks: dict[str, Any]


# Type alias for mock function
# Supports both old and new signatures:
# - Old: mock_fn(scenario_metadata) -> mock_callable
# - New: mock_fn(scenario_metadata, config) -> mock_callable
# The sig.bind() approach in resolve() handles both at runtime.
MockFn = (
    Callable[[dict[str, Any]], Callable[..., Any] | None]
    | Callable[[dict[str, Any], dict[str, Any] | None], Callable[..., Any] | None]
)

# Type alias for "when" predicate function
# when(scenario_metadata) -> should_mock
WhenPredicate = Callable[[dict[str, Any]], bool]


@runtime_checkable
class ToolProtocol(Protocol):
    """
    Protocol defining the minimum interface for a tool.

    This allows StuntDouble to work with any tool implementation
    that satisfies this interface, not just LangChain BaseTool.
    """

    name: str
    description: str

    def invoke(self, input: dict[str, Any], config: Any = None) -> Any:
        """Synchronous invocation."""
        ...

    async def ainvoke(self, input: dict[str, Any], config: Any = None) -> Any:
        """Asynchronous invocation."""
        ...


@runtime_checkable
class ToolWithSchema(ToolProtocol, Protocol):
    """
    Extended protocol for tools with args_schema.

    LangChain StructuredTool and similar tools implement this interface.
    """

    args_schema: Any  # Typically a Pydantic model class


class MockRegistration(TypedDict):
    """
    Internal type for storing mock registrations.

    Attributes:
        mock_fn: Function that creates mock callable from scenario metadata
        when: Optional predicate to determine if mocking should apply
    """

    mock_fn: MockFn
    when: WhenPredicate | None


__all__ = [
    "ScenarioMetadata",
    "MockFn",
    "WhenPredicate",
    "ToolProtocol",
    "ToolWithSchema",
    "MockRegistration",
]
