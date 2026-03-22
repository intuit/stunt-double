"""
Call recording and verification utilities for mock testing.

Provides CallRecorder for capturing tool calls during test execution,
enabling verification of what tools were called with what arguments.

Example:
    >>> from stuntdouble import (
    ...     CallRecorder,
    ...     create_mockable_tool_wrapper,
    ...     default_registry,
    ... )
    >>>
    >>> # Create recorder and wrapper
    >>> recorder = CallRecorder()
    >>> wrapper = create_mockable_tool_wrapper(default_registry, recorder=recorder)
    >>>
    >>> # ... run your agent ...
    >>>
    >>> # Verify calls
    >>> assert recorder.was_called("get_customer")
    >>> assert recorder.call_count("list_bills") == 2
    >>> recorder.assert_called_with("create_invoice", amount=100)
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from stuntdouble.exceptions import MockAssertionError


@dataclass
class CallRecord:
    """
    Record of a single tool call.

    Attributes:
        tool_name: Name of the tool that was called
        args: Keyword arguments passed to the tool
        result: Return value from the tool (mock or real)
        error: Exception raised during call, if any
        timestamp: Unix timestamp when call was made
        duration_ms: Duration of the call in milliseconds
        was_mocked: Whether the call was handled by a mock
        scenario_id: Scenario ID if scenario_metadata was present
    """

    tool_name: str
    args: dict[str, Any]
    result: Any = None
    error: Exception | None = None
    timestamp: float = field(default_factory=time.time)
    duration_ms: float = 0.0
    was_mocked: bool = False
    scenario_id: str | None = None

    def __repr__(self) -> str:
        status = "mocked" if self.was_mocked else "real"
        error_str = f", error={self.error}" if self.error else ""
        return f"CallRecord(tool='{self.tool_name}', status={status}, args={list(self.args.keys())}{error_str})"


class CallRecorder:
    """
    Records tool calls for verification in tests.

    Thread-safe recorder that captures all tool calls passing through
    the mockable_tool_wrapper, enabling test assertions about which
    tools were called, with what arguments, and how many times.

    Example:
        >>> recorder = CallRecorder()
        >>> wrapper = create_mockable_tool_wrapper(registry, recorder=recorder)
        >>>
        >>> # After running agent
        >>> recorder.assert_called("get_customer")
        >>> recorder.assert_called_with("list_bills", status="active")
        >>> recorder.assert_called_times("create_invoice", 2)
        >>> recorder.assert_not_called("delete_account")

    Thread Safety:
        All methods are thread-safe. The recorder uses a lock to protect
        the internal call list during concurrent access.

    Performance:
        The recorder maintains an index by tool name for O(1) lookups.
        Suitable for high-volume test scenarios with many tool calls.
    """

    def __init__(self) -> None:
        """Initialize an empty call recorder."""
        self._calls: list[CallRecord] = []
        self._calls_by_tool: dict[str, list[CallRecord]] = {}
        self._lock = threading.Lock()

    # =========================================================================
    # RECORDING METHODS - Used internally by the wrapper
    # =========================================================================

    def record(
        self,
        tool_name: str,
        args: dict[str, Any],
        result: Any = None,
        error: Exception | None = None,
        duration_ms: float = 0.0,
        was_mocked: bool = False,
        scenario_id: str | None = None,
    ) -> CallRecord:
        """
        Record a tool call.

        This method is called internally by the wrapper to record each call.

        Args:
            tool_name: Name of the tool
            args: Arguments passed to the tool
            result: Return value from the tool
            error: Exception if call failed
            duration_ms: Call duration in milliseconds
            was_mocked: Whether a mock was used
            scenario_id: Scenario ID from scenario_metadata

        Returns:
            The created CallRecord
        """
        record = CallRecord(
            tool_name=tool_name,
            args=args.copy() if args else {},
            result=result,
            error=error,
            duration_ms=duration_ms,
            was_mocked=was_mocked,
            scenario_id=scenario_id,
        )

        with self._lock:
            self._calls.append(record)
            # Maintain index for O(1) lookups by tool name
            if tool_name not in self._calls_by_tool:
                self._calls_by_tool[tool_name] = []
            self._calls_by_tool[tool_name].append(record)

        return record

    def clear(self) -> None:
        """Clear all recorded calls."""
        with self._lock:
            self._calls.clear()
            self._calls_by_tool.clear()

    # =========================================================================
    # QUERY METHODS - Inspect recorded calls
    # =========================================================================

    @property
    def calls(self) -> list[CallRecord]:
        """Get a copy of all recorded calls."""
        with self._lock:
            return self._calls.copy()

    def get_calls(self, tool_name: str | None = None) -> list[CallRecord]:
        """
        Get recorded calls, optionally filtered by tool name.

        Uses indexed lookup for O(1) access when filtering by tool name.

        Args:
            tool_name: Optional tool name to filter by

        Returns:
            List of matching CallRecords
        """
        with self._lock:
            if tool_name is None:
                return self._calls.copy()
            # O(1) lookup using index instead of O(n) linear search
            return self._calls_by_tool.get(tool_name, []).copy()

    def call_count(self, tool_name: str | None = None) -> int:
        """
        Get the number of recorded calls.

        Uses indexed lookup for O(1) access when counting by tool name.

        Args:
            tool_name: Optional tool name to filter by

        Returns:
            Number of calls matching the filter
        """
        with self._lock:
            if tool_name is None:
                return len(self._calls)
            # O(1) lookup using index instead of creating a filtered copy
            return len(self._calls_by_tool.get(tool_name, []))

    def was_called(self, tool_name: str, **expected_args: Any) -> bool:
        """
        Check if a tool was called, optionally with specific arguments.

        Args:
            tool_name: Name of the tool to check
            **expected_args: Optional arguments that must match

        Returns:
            True if the tool was called (with matching args if specified)

        Example:
            >>> recorder.was_called("get_customer")  # Any call
            True
            >>> recorder.was_called("get_customer", customer_id="123")
            True
        """
        calls = self.get_calls(tool_name)

        if not calls:
            return False

        if not expected_args:
            return True

        # Check if any call matches the expected args
        for call in calls:
            if self._args_match(call.args, expected_args):
                return True

        return False

    def get_last_call(self, tool_name: str | None = None) -> CallRecord | None:
        """
        Get the most recent call, optionally for a specific tool.

        Args:
            tool_name: Optional tool name to filter by

        Returns:
            The most recent CallRecord, or None if no calls
        """
        calls = self.get_calls(tool_name)
        return calls[-1] if calls else None

    def get_first_call(self, tool_name: str | None = None) -> CallRecord | None:
        """
        Get the first call, optionally for a specific tool.

        Args:
            tool_name: Optional tool name to filter by

        Returns:
            The first CallRecord, or None if no calls
        """
        calls = self.get_calls(tool_name)
        return calls[0] if calls else None

    def get_args(self, tool_name: str, call_index: int = -1) -> dict[str, Any] | None:
        """
        Get the arguments from a specific call.

        Args:
            tool_name: Name of the tool
            call_index: Index of the call (-1 for last, 0 for first)

        Returns:
            Arguments dict, or None if no such call
        """
        calls = self.get_calls(tool_name)
        if not calls:
            return None
        try:
            return calls[call_index].args.copy()
        except IndexError:
            return None

    def get_result(self, tool_name: str, call_index: int = -1) -> Any:
        """
        Get the result from a specific call.

        Args:
            tool_name: Name of the tool
            call_index: Index of the call (-1 for last, 0 for first)

        Returns:
            Result value, or None if no such call
        """
        calls = self.get_calls(tool_name)
        if not calls:
            return None
        try:
            return calls[call_index].result
        except IndexError:
            return None

    # =========================================================================
    # ASSERTION METHODS - For test verification
    # =========================================================================

    def assert_called(self, tool_name: str) -> None:
        """
        Assert that a tool was called at least once.

        Args:
            tool_name: Name of the tool

        Raises:
            AssertionError: If the tool was not called
        """
        if not self.was_called(tool_name):
            all_tools = list(set(c.tool_name for c in self.calls))
            raise MockAssertionError(
                f"Expected '{tool_name}' to be called, but it was not.\nTools that were called: {all_tools}"
            )

    def assert_not_called(self, tool_name: str) -> None:
        """
        Assert that a tool was never called.

        Args:
            tool_name: Name of the tool

        Raises:
            AssertionError: If the tool was called
        """
        calls = self.get_calls(tool_name)
        if calls:
            raise MockAssertionError(
                f"Expected '{tool_name}' to not be called, "
                f"but it was called {len(calls)} time(s).\n"
                f"Call args: {[c.args for c in calls]}"
            )

    def assert_called_once(self, tool_name: str) -> None:
        """
        Assert that a tool was called exactly once.

        Args:
            tool_name: Name of the tool

        Raises:
            AssertionError: If call count is not exactly 1
        """
        count = self.call_count(tool_name)
        if count != 1:
            raise MockAssertionError(f"Expected '{tool_name}' to be called once, but it was called {count} time(s).")

    def assert_called_times(self, tool_name: str, expected_count: int) -> None:
        """
        Assert that a tool was called a specific number of times.

        Args:
            tool_name: Name of the tool
            expected_count: Expected number of calls

        Raises:
            AssertionError: If call count doesn't match
        """
        count = self.call_count(tool_name)
        if count != expected_count:
            raise MockAssertionError(
                f"Expected '{tool_name}' to be called {expected_count} time(s), but it was called {count} time(s)."
            )

    def assert_called_with(self, tool_name: str, **expected_args: Any) -> None:
        """
        Assert that a tool was called with specific arguments.

        The assertion passes if ANY call to the tool matches the expected args.
        Partial matching is supported - only the specified args are checked.

        Args:
            tool_name: Name of the tool
            **expected_args: Arguments that must be present with matching values

        Raises:
            AssertionError: If no call matches the expected arguments

        Example:
            >>> recorder.assert_called_with("get_customer", customer_id="123")
            >>> recorder.assert_called_with("list_bills", status="active", limit=10)
        """
        if not expected_args:
            return self.assert_called(tool_name)

        calls = self.get_calls(tool_name)

        if not calls:
            raise MockAssertionError(
                f"Expected '{tool_name}' to be called with {expected_args}, but it was never called."
            )

        # Check if any call matches
        for call in calls:
            if self._args_match(call.args, expected_args):
                return  # Found a match

        # No match found - show what was actually called
        actual_calls = [c.args for c in calls]
        raise MockAssertionError(
            f"Expected '{tool_name}' to be called with {expected_args}, "
            f"but no matching call was found.\n"
            f"Actual calls: {actual_calls}"
        )

    def assert_last_called_with(self, tool_name: str, **expected_args: Any) -> None:
        """
        Assert that the last call to a tool had specific arguments.

        Args:
            tool_name: Name of the tool
            **expected_args: Arguments that must match

        Raises:
            AssertionError: If the last call doesn't match
        """
        last_call = self.get_last_call(tool_name)

        if last_call is None:
            raise MockAssertionError(f"Expected '{tool_name}' to be called, but it was never called.")

        if not self._args_match(last_call.args, expected_args):
            raise MockAssertionError(
                f"Expected last call to '{tool_name}' to have args {expected_args}, but got {last_call.args}."
            )

    def assert_any_call(self, tool_name: str, **expected_args: Any) -> None:
        """
        Alias for assert_called_with for compatibility with unittest.mock.

        Args:
            tool_name: Name of the tool
            **expected_args: Arguments that must match
        """
        self.assert_called_with(tool_name, **expected_args)

    def assert_call_order(self, *tool_names: str) -> None:
        """
        Assert that tools were called in a specific order.

        Args:
            *tool_names: Tool names in expected order

        Raises:
            AssertionError: If the call order doesn't match

        Example:
            >>> recorder.assert_call_order("get_customer", "list_bills", "create_invoice")
        """
        if not tool_names:
            return

        actual_order = [c.tool_name for c in self.calls]

        # Find the subsequence
        expected_idx = 0
        for actual_name in actual_order:
            if expected_idx < len(tool_names) and actual_name == tool_names[expected_idx]:
                expected_idx += 1

        if expected_idx != len(tool_names):
            raise MockAssertionError(f"Expected call order {list(tool_names)}, but actual order was {actual_order}.")

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    def _args_match(self, actual_args: dict[str, Any], expected_args: dict[str, Any]) -> bool:
        """
        Check if actual arguments match expected arguments.

        Partial matching - only checks keys present in expected_args.

        Args:
            actual_args: Actual arguments from the call
            expected_args: Expected arguments to match

        Returns:
            True if all expected args match actual args
        """
        for key, expected_value in expected_args.items():
            if key not in actual_args:
                return False
            if actual_args[key] != expected_value:
                return False
        return True

    def summary(self) -> str:
        """
        Get a human-readable summary of recorded calls.

        Returns:
            Summary string
        """
        if not self._calls:
            return "No calls recorded."

        lines = [f"Recorded {len(self._calls)} call(s):"]
        for i, call in enumerate(self._calls):
            status = "MOCKED" if call.was_mocked else "REAL"
            lines.append(f"  {i + 1}. {call.tool_name} [{status}] args={call.args}")

        return "\n".join(lines)

    def __len__(self) -> int:
        """Return total number of recorded calls."""
        with self._lock:
            return len(self._calls)

    def __repr__(self) -> str:
        """String representation."""
        return f"CallRecorder(calls={len(self)})"



__all__ = [
    "CallRecord",
    "CallRecorder",
]
