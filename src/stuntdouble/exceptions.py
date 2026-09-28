"""
StuntDouble exceptions.
"""

from __future__ import annotations


class MockingError(Exception):
    """Base exception for mocking-related errors."""

    pass


class MockNotFoundError(MockingError):
    """Raised when no mock is available for a tool."""

    pass


class MockRegistryError(MockingError):
    """Raised when there's an error with the mock registry."""

    pass


class MissingMockError(MockingError):
    """
    Raised when scenario_metadata is present but no mock is registered for a tool.

    Attributes:
        tool_name: Name of the tool that was missing a mock
        message: Descriptive error message
    """

    def __init__(self, tool_name: str, message: str | None = None):
        self.tool_name = tool_name
        if message is None:
            message = (
                f"scenario_metadata present but no mock registered for tool '{tool_name}'. "
                f"Register a mock with: registry.register('{tool_name}', mock_fn=...)"
            )
        super().__init__(message)


class MockFactoryError(MockingError):
    """
    Raised when a registered mock factory raises while the mock is being resolved.

    The original exception is chained as ``__cause__``. Without this the failure
    looked like "no mock registered", which points at the wrong problem.

    Attributes:
        tool_name: Name of the tool whose factory failed
        cause: The exception the factory raised
    """

    def __init__(self, tool_name: str, cause: BaseException):
        self.tool_name = tool_name
        self.cause = cause
        super().__init__(f"Mock factory for tool '{tool_name}' raised {type(cause).__name__}: {cause}")


class SignatureMismatchError(MockingError):
    """
    Raised when mock function signature doesn't match tool signature.

    Attributes:
        tool_name: Name of the tool with signature mismatch
        expected: String representation of expected signature
        actual: String representation of actual mock signature
    """

    def __init__(self, tool_name: str, expected: str, actual: str):
        self.tool_name = tool_name
        self.expected = expected
        self.actual = actual
        super().__init__(f"Mock for '{tool_name}' has mismatched signature.\nExpected: {expected}\nActual: {actual}")


class InputNotMatchedError(MockingError):
    """
    Raised when a mock's input conditions are not met for a tool call.

    This signals that the mock was resolved but doesn't apply to this
    specific set of tool call arguments. The wrapper uses this to
    distinguish "mock exists but conditions didn't match" from "mock
    returned None as a legitimate value."

    Attributes:
        tool_name: Name of the tool whose conditions didn't match
    """

    def __init__(self, tool_name: str, message: str | None = None):
        self.tool_name = tool_name
        if message is None:
            message = (
                f"Mock input conditions not met for tool '{tool_name}'. "
                f"No matching case found for the provided arguments."
            )
        super().__init__(message)


class MockAssertionError(MockingError):
    """
    Raised when a mock assertion fails.

    Attributes:
        message: Descriptive error message about the assertion failure
    """

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


__all__ = [
    "MockingError",
    "MockNotFoundError",
    "MockRegistryError",
    "MissingMockError",
    "MockFactoryError",
    "InputNotMatchedError",
    "MockAssertionError",
    "SignatureMismatchError",
]
