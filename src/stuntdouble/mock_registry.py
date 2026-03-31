# ABOUTME: Stores mock registrations and resolves the right mock callable for each tool invocation.
# ABOUTME: Supports plain factories, conditional mocking, and data-driven mock registration on one registry.
"""
MockToolsRegistry - Mocked tool registration for per-invocation mocking.

This mock registry stores mocked tools that create callable mocks bound to specific
scenario metadata at runtime. This design ensures:
- No global mutable state affects concurrent runs
- Each invocation gets its own mock callable
- Mocking behavior is determined by scenario_metadata in RunnableConfig
- Mock factories can optionally receive runtime config for context-aware mocking

Mock Factory Signatures:
    Mock factories can use either of these signatures (detected automatically):
    - Old: mock_fn(scenario_metadata) -> mock_callable
    - New: mock_fn(scenario_metadata, config) -> mock_callable

    The new signature allows access to RunnableConfig for extracting runtime context
    like user identity from HTTP headers, useful for no-argument tools.

This registry is used by the mockable tool wrapper (stuntdouble.wrapper).
"""

from __future__ import annotations

import inspect
import logging
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from stuntdouble.types import MockFn, MockRegistration, WhenPredicate

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

    from stuntdouble.builder import MockBuilder

logger = logging.getLogger(__name__)


class MockToolsRegistry:
    """
    Thread-safe mock registry with mocked tool resolution.

    The mock registry stores mock definitions by tool name. Each definition includes:
    - mock_fn: A function that takes scenario_metadata and returns a mock callable
    - when: An optional predicate that determines if mocking applies for a scenario

    This design allows the same mock registry to be used concurrently by multiple
    graph invocations, each with different scenario_metadata.

    Example:
        >>> mock_registry = MockToolsRegistry()
        >>>
        >>> # Register a simple mocked tool
        >>> mock_registry.register(
        ...     "get_weather",
        ...     mock_fn=lambda md: lambda city: {"temp": 72, "city": city}
        ... )
        >>>
        >>> # Register with conditional mocking
        >>> mock_registry.register(
        ...     "bills_query",
        ...     mock_fn=lambda md: lambda **kw: md["mocks"]["bills_query"][0]["output"],
        ...     when=lambda md: "bills_query" in md.get("mocks", {})
        ... )
        >>>
        >>> # Resolve at runtime
        >>> mock_fn = mock_registry.resolve("get_weather", {"mode": "mock"})
        >>> mock_fn(city="NYC")  # Returns {"temp": 72, "city": "NYC"}

    Thread Safety:
        - Reads use no locking (dict operations are atomic in CPython)
        - Writes use a lock to prevent race conditions during registration
        - Once registered, mocked tools are not mutated

    Concurrency:
        - Mock registry is read-mostly after initialization
        - If used concurrently with modifications, writes are guarded by lock
        - Recommended: construct once at startup, don't mutate after graph compilation
    """

    def __init__(self) -> None:
        """Initialize empty mock registry."""
        self._registrations: dict[str, MockRegistration] = {}
        self._lock = threading.Lock()
        logger.debug("MockToolsRegistry initialized")

    def register(
        self,
        tool_name: str,
        mock_fn: MockFn,
        when: WhenPredicate | None = None,
        tool: BaseTool | None = None,
    ) -> None:
        """
        Register a mocked tool for a tool.

        Args:
            tool_name: Name of the tool to mock (must match tool.name in LangGraph)
            mock_fn: Function that takes scenario_metadata dict and returns a
                    callable mock function. The mock function should accept the
                    same parameters as the real tool.
            when: Optional predicate function that takes scenario_metadata and
                  returns True if mocking should apply for this tool in this
                  scenario. If None, mocking always applies when resolved.
            tool: Optional BaseTool instance. If provided, validates that mock_fn's
                  signature matches the tool's expected parameters. Raises
                  SignatureMismatchError if validation fails.

        Example:
            >>> # Simple static mocked tool
            >>> mock_registry.register(
            ...     "get_user",
            ...     mock_fn=lambda md: lambda user_id: {"id": user_id, "name": "Test"}
            ... )
            >>>
            >>> # Mocked tool using mocks from scenario_metadata
            >>> mock_registry.register(
            ...     "list_customers",
            ...     mock_fn=lambda md: lambda **kw: md["mocks"]["list_customers"][0]["output"],
            ...     when=lambda md: "list_customers" in md.get("mocks", {})
            ... )
            >>>
            >>> # Register with signature validation
            >>> mock_registry.register(
            ...     "get_weather",
            ...     mock_fn=weather_mock,
            ...     tool=get_weather_tool,  # Validates signature at registration
            ... )

        Raises:
            ValueError: If tool_name is empty or mock_fn is not callable
            SignatureMismatchError: If tool is provided and mock signature doesn't match
        """
        if not tool_name:
            raise ValueError("tool_name cannot be empty")
        if not callable(mock_fn):
            raise ValueError(f"mock_fn must be callable, got {type(mock_fn)}")
        if when is not None and not callable(when):
            raise ValueError(f"when must be callable or None, got {type(when)}")

        # Validate signature if tool is provided
        if tool is not None:
            from stuntdouble.exceptions import SignatureMismatchError
            from stuntdouble.validation import validate_mock_signature

            is_valid, error_msg = validate_mock_signature(tool, mock_fn)
            if not is_valid:
                # Parse expected/actual from error message or generate them
                raise SignatureMismatchError(
                    tool_name=tool_name,
                    expected=f"(tool '{tool.name}' parameters)",
                    actual=error_msg or "unknown",
                )

        registration: MockRegistration = {
            "mock_fn": mock_fn,
            "when": when,
        }

        with self._lock:
            self._registrations[tool_name] = registration

        logger.debug(f"Registered mock for '{tool_name}' (conditional={'yes' if when else 'no'})")

    def unregister(self, tool_name: str) -> bool:
        """
        Remove a mock registration.

        Args:
            tool_name: Name of the tool to unregister

        Returns:
            True if removed, False if not found
        """
        with self._lock:
            if tool_name in self._registrations:
                del self._registrations[tool_name]
                logger.debug(f"Unregistered mock for '{tool_name}'")
                return True
        return False

    def resolve(
        self,
        tool_name: str,
        scenario_metadata: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> Callable[..., Any] | None:
        """
        Resolve the mock callable for a tool given scenario metadata.

        Resolution logic:
        1. If tool_name not registered -> returns None
        2. If `when` predicate exists and returns False -> returns None
        3. Otherwise -> calls mock_fn(scenario_metadata, config) or mock_fn(scenario_metadata)
           depending on factory signature, and returns the callable

        Args:
            tool_name: Name of the tool to resolve mock for
            scenario_metadata: The scenario configuration for this run
            config: Optional RunnableConfig for accessing runtime context (headers, etc.)
                   Passed to mock factories that accept a second parameter.

        Returns:
            A callable mock function if resolved, None if:
            - Tool not registered
            - `when` predicate returned False

        Example:
            >>> mock_fn = mock_registry.resolve("get_weather", {"mode": "mock"})
            >>> if mock_fn:
            ...     result = mock_fn(city="NYC")
            ... else:
            ...     # Call real tool
            ...     result = real_tool.invoke({"city": "NYC"})
            >>>
            >>> # With config for context-aware mocks
            >>> mock_fn = mock_registry.resolve("get_user", scenario_metadata, config)
        """
        registration = self._registrations.get(tool_name)

        if registration is None:
            logger.debug(f"No mock registered for '{tool_name}'")
            return None

        # Check when predicate if present
        when_fn = registration["when"]
        if when_fn is not None:
            try:
                should_mock = when_fn(scenario_metadata)
                if not should_mock:
                    logger.debug(f"Mock for '{tool_name}' skipped: when predicate returned False")
                    return None
            except Exception as e:
                logger.warning(f"Mock for '{tool_name}': when predicate raised {e}, skipping mock")
                return None

        # Call mock_fn to create the mock callable
        mock_fn = registration["mock_fn"]
        try:
            # Use sig.bind() for safe signature detection
            # This handles all edge cases: defaults, *args, **kwargs, etc.
            sig = inspect.signature(mock_fn)
            try:
                sig.bind({}, {})  # Test if function can accept 2 args
                # Function CAN accept 2 args - use new signature
                mock_callable = mock_fn(scenario_metadata, config)  # type: ignore[call-arg]
            except TypeError:
                # Function cannot accept 2 args - use old signature
                mock_callable = mock_fn(scenario_metadata)  # type: ignore[call-arg]

            logger.debug(f"Resolved mock for '{tool_name}'")
            return mock_callable
        except Exception as e:
            logger.error(
                f"Mock factory for '{tool_name}' raised exception: {e}",
                exc_info=True,
            )
            return None

    def get_mock_fn(self, tool_name: str) -> MockFn | None:
        """
        Get the mock factory function for a tool.

        This is useful for introspection, such as validating mock signatures
        without triggering the full resolution logic.

        Args:
            tool_name: Name of the tool

        Returns:
            The mock factory function, or None if not registered
        """
        registration = self._registrations.get(tool_name)
        return registration["mock_fn"] if registration else None

    def is_registered(self, tool_name: str) -> bool:
        """
        Check if a tool has a mock registered.

        Args:
            tool_name: Name of the tool

        Returns:
            True if tool has a mock registration
        """
        return tool_name in self._registrations

    def list_registered(self) -> list[str]:
        """
        List all registered tool names.

        Returns:
            List of tool names with registrations
        """
        return list(self._registrations.keys())

    def clear(self) -> None:
        """Remove all registrations."""
        with self._lock:
            count = len(self._registrations)
            self._registrations.clear()
        logger.info(f"Cleared {count} mock registrations")

    def __len__(self) -> int:
        """Return number of registered mocks."""
        return len(self._registrations)

    def __contains__(self, tool_name: str) -> bool:
        """Support 'in' operator."""
        return tool_name in self._registrations

    def register_data_driven(
        self,
        tool_name: str,
        *,
        fallback: Any = None,
        echo_input: bool = False,
    ) -> None:
        """
        Register a data-driven mock for a tool.

        Creates a DataDrivenMockFactory that reads mock cases from
        scenario_metadata["mocks"][tool_name] at runtime. Eliminates
        the need for hand-written mock factory functions.

        Args:
            tool_name: Name of the tool to mock
            fallback: Value returned when no mock case matches input
            echo_input: If True, return input kwargs when no match

        Example:
            >>> registry = MockToolsRegistry()
            >>> registry.register_data_driven("query_bills", echo_input=True)
            >>> registry.register_data_driven("search", fallback="No results.")
        """
        from stuntdouble.scenario_mocking import DataDrivenMockFactory

        factory = DataDrivenMockFactory(tool_name, fallback=fallback, echo_input=echo_input)
        self.register(tool_name, mock_fn=factory, when=factory.when_predicate)

    def mock(self, tool_name: str) -> MockBuilder:
        """
        Start building a mock registration using the fluent API.

        Args:
            tool_name: Name of the tool to mock (must match tool.name in LangGraph)

        Returns:
            A MockBuilder for chaining

        Example:
            >>> registry = MockToolsRegistry()
            >>> registry.mock("get_weather").returns({"temp": 72})
            >>> registry.mock("list_bills").when(status="active").returns({"bills": []})
            >>> registry.mock("update").echoes_input("customer_id").returns({"ok": True})
            >>> registry.mock("calc").returns_fn(lambda x, y: {"sum": x + y})
        """
        from stuntdouble.builder import MockBuilder

        return MockBuilder(tool_name, self)

    def __repr__(self) -> str:
        """String representation."""
        return f"MockToolsRegistry(count={len(self._registrations)})"


__all__ = ["MockToolsRegistry"]
