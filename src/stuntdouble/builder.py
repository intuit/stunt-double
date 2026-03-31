# ABOUTME: Defines the fluent MockBuilder API for registering mocks with chained calls.
# ABOUTME: Turns concise when/returns-style declarations into registry-backed mock factories.
"""
Fluent mock builder API for concise mock registration.

Provides a chainable API as an alternative to raw registry.register() calls:

    registry.mock("get_customer").returns({"id": "123", "name": "Test Corp"})
    registry.mock("send_email").when(mode="test").returns({"sent": True})
    registry.mock("update").echoes_input("customer_id").returns({"updated": True})
    registry.mock("calc").returns_fn(lambda items: {"total": sum(items)})
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from stuntdouble.exceptions import InputNotMatchedError
from stuntdouble.matching import InputMatcher

if TYPE_CHECKING:
    from stuntdouble.mock_registry import MockToolsRegistry


class MockBuilder:
    """
    Chainable builder for registering mocks on a MockToolsRegistry.

    Created via ``registry.mock(tool_name)``.

    Example:
        >>> registry = MockToolsRegistry()
        >>> registry.mock("get_weather").returns({"temp": 72})
        >>> registry.mock("get_customer").echoes_input("customer_id").returns({"name": "Test"})
        >>> registry.mock("search").when(query={"$contains": "bill"}).returns({"results": []})
    """

    def __init__(self, tool_name: str, registry: MockToolsRegistry) -> None:
        self._tool_name = tool_name
        self._registry = registry
        self._input_conditions: dict[str, Any] | None = None
        self._when_predicate: Callable[[dict[str, Any]], bool] | None = None
        self._echo_fields: list[str] = []

    def when(
        self,
        predicate: Callable[[dict[str, Any]], bool] | None = None,
        **conditions: Any,
    ) -> MockBuilder:
        """
        Set conditions for when this mock applies.

        Can be used in two ways:

        1. **Input matching** (kwargs) -- mock only fires when tool call
           arguments match these conditions (supports operators like $gt, $in):

               registry.mock("get_bills").when(status="active").returns(...)

        2. **Scenario predicate** (callable) -- mock only fires when the
           predicate returns True for the scenario_metadata:

               registry.mock("tool").when(lambda md: md.get("mode") == "test").returns(...)

        Both can be combined. The scenario predicate gates whether the mock
        is resolved at all; input conditions filter inside the mock callable.
        """
        if predicate is not None:
            self._when_predicate = predicate
        if conditions:
            self._input_conditions = conditions
        return self

    def echoes_input(self, *fields: str) -> MockBuilder:
        """
        Copy specified input fields into the response dict.

        Only applies when used with ``.returns(dict)``.

        Example:
            >>> registry.mock("update_customer").echoes_input("customer_id", "name").returns({"updated": True})
            >>> # Called with customer_id="C1", name="Acme"
            >>> # Returns {"updated": True, "customer_id": "C1", "name": "Acme"}
        """
        self._echo_fields = list(fields)
        return self

    def returns(self, value: Any) -> None:
        """
        Register a mock that returns a static value.

        This is the terminal method -- it registers the mock on the registry.

        Example:
            >>> registry.mock("get_weather").returns({"temp": 72, "conditions": "sunny"})
        """
        input_conditions = self._input_conditions
        echo_fields = self._echo_fields
        matcher = InputMatcher() if input_conditions else None
        tool_name = self._tool_name

        def mock_fn(scenario_metadata: dict[str, Any]) -> Callable[..., Any]:
            def mock_callable(**kwargs: Any) -> Any:
                if matcher and input_conditions:
                    if not matcher.matches(input_conditions, kwargs):
                        raise InputNotMatchedError(
                            tool_name,
                            message=(
                                f"Mock input conditions not met for tool '{tool_name}': "
                                f"expected {input_conditions}, got {kwargs}"
                            ),
                        )

                result = copy.deepcopy(value)
                if echo_fields and isinstance(result, dict):
                    for field in echo_fields:
                        if field in kwargs:
                            result[field] = kwargs[field]
                return result

            return mock_callable

        self._registry.register(
            self._tool_name,
            mock_fn=mock_fn,
            when=self._when_predicate,
        )

    def returns_fn(self, fn: Callable[..., Any]) -> None:
        """
        Register a mock that calls ``fn`` with the tool's keyword arguments.

        This is the terminal method -- it registers the mock on the registry.

        Example:
            >>> registry.mock("calculate_total").returns_fn(
            ...     lambda items, tax_rate: {"total": sum(i["price"] for i in items) * (1 + tax_rate)}
            ... )
        """

        def mock_fn(scenario_metadata: dict[str, Any]) -> Callable[..., Any]:
            return fn

        self._registry.register(
            self._tool_name,
            mock_fn=mock_fn,
            when=self._when_predicate,
        )


__all__ = ["MockBuilder"]
