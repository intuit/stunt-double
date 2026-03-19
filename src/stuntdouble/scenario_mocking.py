"""
Data-driven mock factories for scenario_metadata-based mocking.

Provides a generic mock factory that reads mock cases from scenario_metadata
at runtime, eliminating the need for hand-written per-tool mock factories.

Each tool's mock data lives in scenario_metadata["mocks"][tool_name] as a list
of {input, output} cases. The factory handles input matching, placeholder
resolution, fallback values, and echo_input mode automatically.

Placeholders in outputs are resolved at call time:
- {{input.field}} references tool call arguments (kwargs)
- {{config.field}} references values from RunnableConfig
- {{now}}, {{uuid}}, etc. generate dynamic values
"""

from __future__ import annotations

import copy
import logging
from collections.abc import Callable
from typing import Any

from stuntdouble.exceptions import InputNotMatchedError
from stuntdouble.matching import InputMatcher
from stuntdouble.resolving import ResolverContext, ValueResolver

logger = logging.getLogger(__name__)


def _extract_config_data(config: dict[str, Any] | None) -> dict[str, Any]:
    """
    Extract a flat dict of values from RunnableConfig for placeholder resolution.

    Merges configurable["config_data"] (explicit) and configurable (implicit)
    so that {{config.field}} can reference either source.
    """
    if not config:
        return {}
    configurable = config.get("configurable", {})
    # Explicit config_data takes precedence over raw configurable keys
    data: dict[str, Any] = dict(configurable)
    data.update(configurable.get("config_data", {}))
    return data


class DataDrivenMockFactory:
    """
    Mock factory that reads cases from scenario_metadata at runtime.

    Designed to replace hand-written mock factories. Each instance is bound
    to a single tool_name and, when called with scenario_metadata (and
    optionally RunnableConfig), returns a mock callable that matches inputs
    and resolves outputs.

    Args:
        tool_name: Name of the tool (key in scenario_metadata["mocks"])
        fallback: Value returned when no case matches. If None and no match,
                  returns the first case's output as a last resort.
        echo_input: If True, the mock callable returns the input kwargs as-is
                    when no cases match. Useful for passthrough tools.

    Example:
        >>> factory = DataDrivenMockFactory("get_weather", fallback={"temp": 0})
        >>> scenario = {"mocks": {"get_weather": [
        ...     {"input": {"city": "NYC"}, "output": {"temp": 72}},
        ...     {"output": {"temp": 65}}  # catch-all
        ... ]}}
        >>> mock_fn = factory(scenario)
        >>> mock_fn(city="NYC")
        {'temp': 72}

    With config placeholders:
        >>> scenario = {"mocks": {"get_user": [
        ...     {"output": {"user": "{{config.user_id}}", "ts": "{{now}}"}}
        ... ]}}
        >>> config = {"configurable": {"user_id": "U-123"}}
        >>> mock_fn = factory(scenario, config)
        >>> mock_fn()
        {'user': 'U-123', 'ts': '2025-...'}
    """

    def __init__(
        self,
        tool_name: str,
        fallback: Any = None,
        echo_input: bool = False,
    ) -> None:
        self.tool_name = tool_name
        self.fallback = fallback
        self.echo_input = echo_input
        self._matcher = InputMatcher()
        self._resolver = ValueResolver()

    def __call__(
        self,
        scenario_metadata: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> Callable[..., Any] | None:
        """
        Create a mock callable from scenario_metadata.

        Args:
            scenario_metadata: Scenario data containing mock cases.
            config: Optional RunnableConfig for {{config.*}} placeholders.

        Returns None if scenario_metadata has no mock data for this tool,
        signaling the registry to skip mocking and call the real tool.
        """
        cases = scenario_metadata.get("mocks", {}).get(self.tool_name)
        if cases is None:
            return None

        # Normalize to list of cases
        if not isinstance(cases, list):
            if isinstance(cases, dict) and ("output" in cases or "input" in cases):
                cases = [cases]
            else:
                cases = [{"output": cases}]

        matcher = self._matcher
        resolver = self._resolver
        fallback = self.fallback
        echo_input = self.echo_input
        tool_name = self.tool_name
        config_data = _extract_config_data(config)

        def mock_callable(**kwargs: Any) -> Any:
            context = ResolverContext(input_data=kwargs, config_data=config_data)

            for case in cases:
                case_input = case.get("input")
                if case_input is None:
                    # Catch-all case
                    output = case.get("output", case)
                    return resolver.resolve_dynamic_values(copy.deepcopy(output), context)

                if matcher.matches(case_input, kwargs):
                    output = case.get("output", case)
                    return resolver.resolve_dynamic_values(copy.deepcopy(output), context)

            # No match found
            if echo_input:
                return kwargs

            if fallback is not None:
                return copy.deepcopy(fallback)

            raise InputNotMatchedError(
                tool_name,
                message=(
                    f"No matching mock case for tool '{tool_name}' and no fallback configured. "
                    f"Add a catch-all case (one without an 'input' key) or set fallback=... "
                    f"when registering the data-driven mock."
                ),
            )

        return mock_callable

    def when_predicate(self, scenario_metadata: dict[str, Any]) -> bool:
        """Return True if scenario_metadata contains mock data for this tool."""
        return self.tool_name in scenario_metadata.get("mocks", {})

    def __repr__(self) -> str:
        opts = []
        if self.fallback is not None:
            opts.append(f"fallback={self.fallback!r}")
        if self.echo_input:
            opts.append("echo_input=True")
        extra = f", {', '.join(opts)}" if opts else ""
        return f"DataDrivenMockFactory({self.tool_name!r}{extra})"


def register_data_driven(
    registry: Any,
    tool_name: str,
    *,
    fallback: Any = None,
    echo_input: bool = False,
) -> DataDrivenMockFactory:
    """
    Register a data-driven mock for a tool on the given registry.

    Convenience function that creates a DataDrivenMockFactory and registers
    it with the registry in one call.

    Args:
        registry: A MockToolsRegistry instance
        tool_name: Name of the tool to mock
        fallback: Value returned when no case matches
        echo_input: If True, return input kwargs when no match

    Returns:
        The created DataDrivenMockFactory instance

    Example:
        >>> from stuntdouble import MockToolsRegistry, register_data_driven
        >>> registry = MockToolsRegistry()
        >>> register_data_driven(registry, "query_bills", echo_input=True)
        >>> register_data_driven(registry, "search", fallback="No results.")
    """
    factory = DataDrivenMockFactory(tool_name, fallback=fallback, echo_input=echo_input)
    registry.register(tool_name, mock_fn=factory, when=factory.when_predicate)
    return factory


__all__ = [
    "DataDrivenMockFactory",
    "register_data_driven",
]
