# ABOUTME: Validates mock signatures and scenario mock inputs against the real tool definitions.
# ABOUTME: Helps catch bad mock configuration before or during graph execution.
"""
Tool parameter validation utilities.

Provides functions to validate that mock case inputs match the expected
parameters of the real tools, helping catch configuration errors early.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from typing import Any

from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)


# =============================================================================
# Mock Function Signature Validation
# =============================================================================


def validate_mock_signature(
    tool: BaseTool,
    mock_fn: Callable[..., Callable[..., Any] | None],
    scenario_metadata: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> tuple[bool, str | None]:
    """
    Validate that a mock function's signature matches the tool's expected parameters.

    This function validates that the callable returned by mock_fn accepts the same
    parameters as the original tool, helping catch configuration errors early.

    Args:
        tool: The BaseTool instance to validate against
        mock_fn: The mock factory function that takes scenario_metadata and
                 optionally config, returning a callable mock function
        scenario_metadata: Optional scenario metadata to pass to mock_fn.
                          If None, an empty dict is used for validation.
        config: Optional RunnableConfig for context-aware mock factories.
                Passed to factories that accept a second parameter.

    Returns:
        Tuple of (is_valid, error_message).
        - (True, None) if signatures match
        - (False, error_message) if there's a mismatch

    Example:
        >>> from langchain_core.tools import tool
        >>> from stuntdouble import validate_mock_signature
        >>>
        >>> @tool
        ... def get_weather(city: str, units: str = "celsius") -> str:
        ...     '''Get weather for a city.'''
        ...     return f"Weather in {city}"
        >>>
        >>> # Good mock - matches signature
        >>> def good_mock(scenario_metadata):
        ...     def mock_fn(city: str, units: str = "celsius"):
        ...         return {"temp": 72}
        ...     return mock_fn
        >>>
        >>> is_valid, error = validate_mock_signature(get_weather, good_mock)
        >>> print(is_valid)  # True
        >>>
        >>> # Bad mock - missing parameter
        >>> def bad_mock(scenario_metadata):
        ...     def mock_fn(city: str):  # Missing 'units'
        ...         return {"temp": 72}
        ...     return mock_fn
        >>>
        >>> is_valid, error = validate_mock_signature(get_weather, bad_mock)
        >>> print(is_valid)  # False
        >>> print(error)  # "Missing parameters: units"
    """
    try:
        # Get the actual mock callable by calling mock_fn
        test_metadata = scenario_metadata if scenario_metadata is not None else {}

        # Use sig.bind() to detect factory signature (same approach as resolve())
        # This handles all edge cases: defaults, *args, **kwargs, etc.
        sig = inspect.signature(mock_fn)
        try:
            sig.bind({}, {})  # Test if function can accept 2 args
            mock_callable = mock_fn(test_metadata, config)  # New signature
        except TypeError:
            mock_callable = mock_fn(test_metadata)  # Old signature

        if not callable(mock_callable):
            return (
                False,
                f"mock_fn did not return a callable, got {type(mock_callable)}",
            )

        # Get tool's expected parameters
        tool_params = _get_tool_parameter_info(tool)

        # Get mock's actual parameters using inspect
        mock_params = _get_callable_parameter_info(mock_callable)

        # Compare parameters
        return _compare_signatures(tool.name, tool_params, mock_params)

    except Exception as e:
        return False, f"Error during signature validation: {e}"


def _get_tool_parameter_info(tool: BaseTool) -> dict[str, dict[str, Any]]:
    """
    Extract detailed parameter info from a tool's schema.

    Handles multiple schema formats:
    - Pydantic v2 models (with model_fields)
    - Pydantic v1 models (with __fields__)
    - JSON Schema dicts (from MCP tools via langchain-mcp-adapters)
    - Fallback to tool.args dict

    Returns:
        Dict mapping param name to {"required": bool, "has_default": bool}
    """
    params: dict[str, dict[str, Any]] = {}

    if hasattr(tool, "args_schema") and tool.args_schema is not None:
        schema = tool.args_schema
        if hasattr(schema, "model_fields"):
            # Pydantic v2
            for name, field in schema.model_fields.items():
                params[name] = {
                    "required": field.is_required(),
                    "has_default": field.default is not None or not field.is_required(),
                }
        elif hasattr(schema, "__fields__"):
            # Pydantic v1
            for name, field in schema.__fields__.items():
                params[name] = {
                    "required": field.required,
                    "has_default": field.default is not None or not field.required,
                }
        elif isinstance(schema, dict):
            # JSON Schema dict (from MCP tools via langchain-mcp-adapters)
            # Format: {"type": "object", "properties": {...}, "required": [...]}
            if schema.get("type") != "object":
                logger.warning(f"Unexpected JSON Schema type: {schema.get('type')}, expected 'object'")
                return params
            properties = schema.get("properties", {})
            required_params = set(schema.get("required", []))
            for name, prop_def in properties.items():
                has_default = "default" in prop_def if isinstance(prop_def, dict) else False
                params[name] = {
                    "required": name in required_params,
                    "has_default": has_default or name not in required_params,
                }
    elif hasattr(tool, "args") and isinstance(tool.args, dict):
        # Fallback to tool.args
        for name in tool.args:
            params[name] = {"required": True, "has_default": False}

    return params


def _get_callable_parameter_info(func: Callable) -> dict[str, dict[str, Any]]:
    """
    Extract parameter info from a callable using inspect.

    Returns:
        Dict mapping param name to {"required": bool, "has_default": bool, "kind": str}
    """
    params: dict[str, dict[str, Any]] = {}

    try:
        sig = inspect.signature(func)
    except (ValueError, TypeError):
        return params

    for name, param in sig.parameters.items():
        # Skip *args and **kwargs
        if param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue

        has_default = param.default is not inspect.Parameter.empty
        params[name] = {
            "required": not has_default,
            "has_default": has_default,
            "kind": param.kind.name,
        }

    return params


def _compare_signatures(
    tool_name: str,
    tool_params: dict[str, dict[str, Any]],
    mock_params: dict[str, dict[str, Any]],
) -> tuple[bool, str | None]:
    """
    Compare tool and mock parameter signatures for exact match.

    Returns:
        Tuple of (is_valid, error_message or None)
    """
    tool_param_names = set(tool_params.keys())
    mock_param_names = set(mock_params.keys())

    errors: list[str] = []

    # Check for missing parameters in mock
    missing = tool_param_names - mock_param_names
    if missing:
        errors.append(f"Missing parameters in mock: {', '.join(sorted(missing))}")

    # Check for extra parameters in mock (that don't have defaults)
    extra = mock_param_names - tool_param_names
    extra_required = [p for p in extra if mock_params[p].get("required", False)]
    if extra_required:
        errors.append(f"Extra required parameters in mock: {', '.join(sorted(extra_required))}")

    # Check required/optional mismatch for matching parameters
    for param_name in tool_param_names & mock_param_names:
        tool_required = tool_params[param_name].get("required", False)
        mock_required = mock_params[param_name].get("required", False)

        # If tool requires it but mock has it optional, that's ok
        # If tool has it optional but mock requires it, that's a problem
        if not tool_required and mock_required:
            errors.append(f"Parameter '{param_name}' is optional in tool but required in mock")

    if errors:
        expected_sig = _format_signature(tool_params)
        actual_sig = _format_signature(mock_params)
        return False, (f"{'; '.join(errors)}\nExpected signature: {expected_sig}\nActual mock signature: {actual_sig}")

    return True, None


def _format_signature(params: dict[str, dict[str, Any]]) -> str:
    """Format parameter info as a signature-like string."""
    parts = []
    for name, info in params.items():
        if info.get("required", False):
            parts.append(name)
        else:
            parts.append(f"{name}=...")
    return f"({', '.join(parts)})"


def validate_mock_parameters(
    tool: BaseTool,
    mock_cases: list[dict[str, Any]],
) -> list[str]:
    """
    Validate that mock case inputs match the tool's expected parameters.

    This helps catch configuration errors where mock cases specify input
    patterns that don't match the actual tool's parameter schema.

    Args:
        tool: The BaseTool instance to validate against
        mock_cases: List of mock case dicts, each with optional "input" key

    Returns:
        List of validation error messages. Empty list means all cases are valid.

    Example:
        >>> from langchain_core.tools import tool
        >>> from stuntdouble import validate_mock_parameters
        >>>
        >>> @tool
        ... def get_weather(city: str, units: str = "celsius") -> str:
        ...     '''Get weather for a city.'''
        ...     return f"Weather in {city}"
        >>>
        >>> mock_cases = [
        ...     {"input": {"city": "NYC"}, "output": {"temp": 72}},
        ...     {"input": {"wrong_param": "value"}, "output": {"temp": 70}},
        ... ]
        >>>
        >>> errors = validate_mock_parameters(get_weather, mock_cases)
        >>> print(errors)
        ["Case 2: Unknown parameter 'wrong_param'. Valid parameters: city, units"]
    """
    errors: list[str] = []

    # Get tool's expected parameters from schema
    expected_params = _get_tool_parameters(tool)
    required_params = _get_required_parameters(tool)

    for i, case in enumerate(mock_cases, start=1):
        case_input = case.get("input")

        # Cases without input are catch-all patterns, skip validation
        if case_input is None:
            continue

        if not isinstance(case_input, dict):
            errors.append(f"Case {i}: 'input' must be a dict, got {type(case_input).__name__}")
            continue

        # Check for unknown parameters
        for param_name in case_input:
            if param_name not in expected_params:
                valid_params = ", ".join(sorted(expected_params))
                errors.append(f"Case {i}: Unknown parameter '{param_name}'. Valid parameters: {valid_params}")

        # Warn about missing required parameters (not an error, just informational)
        missing_required = required_params - set(case_input.keys())
        if missing_required:
            logger.debug(
                f"Case {i} for '{tool.name}' doesn't specify required params: "
                f"{missing_required}. This case may match fewer inputs."
            )

    return errors


def validate_registry_mocks(
    tools: list[BaseTool],
    scenario_metadata: dict[str, Any],
) -> dict[str, list[str]]:
    """
    Validate all mock cases in scenario_metadata against their corresponding tools.

    Args:
        tools: List of tools that may be mocked
        scenario_metadata: The scenario metadata containing mock definitions

    Returns:
        Dict mapping tool names to their validation errors.
        Tools with no errors are not included in the result.

    Example:
        >>> errors = validate_registry_mocks(tools, scenario_metadata)
        >>> if errors:
        ...     for tool_name, tool_errors in errors.items():
        ...         print(f"{tool_name}: {tool_errors}")
    """
    all_errors: dict[str, list[str]] = {}

    mocks = scenario_metadata.get("mocks", {})
    tools_by_name = {t.name: t for t in tools}

    for tool_name, mock_cases in mocks.items():
        tool = tools_by_name.get(tool_name)

        if tool is None:
            all_errors[tool_name] = [f"No tool named '{tool_name}' found in tools list"]
            continue

        # Normalize to list of cases
        if not isinstance(mock_cases, list):
            if isinstance(mock_cases, dict) and ("output" in mock_cases or "input" in mock_cases):
                mock_cases = [mock_cases]
            else:
                mock_cases = [{"output": mock_cases}]

        errors = validate_mock_parameters(tool, mock_cases)
        if errors:
            all_errors[tool_name] = errors

    return all_errors


def _get_tool_parameters(tool: BaseTool) -> set[str]:
    """
    Extract parameter names from a tool's schema.

    Args:
        tool: BaseTool instance

    Returns:
        Set of parameter names the tool accepts
    """
    # Try to get from args_schema (Pydantic model)
    if hasattr(tool, "args_schema") and tool.args_schema is not None:
        schema = tool.args_schema
        if hasattr(schema, "model_fields"):
            # Pydantic v2
            return set(schema.model_fields.keys())
        elif hasattr(schema, "__fields__"):
            # Pydantic v1
            return set(schema.__fields__.keys())

    # Fallback: try to get from tool.args
    if hasattr(tool, "args") and isinstance(tool.args, dict):
        return set(tool.args.keys())

    # Last resort: return empty set
    logger.warning(f"Could not determine parameters for tool '{tool.name}'")
    return set()


def _get_required_parameters(tool: BaseTool) -> set[str]:
    """
    Extract required parameter names from a tool's schema.

    Args:
        tool: BaseTool instance

    Returns:
        Set of required parameter names
    """
    required = set()

    if hasattr(tool, "args_schema") and tool.args_schema is not None:
        schema = tool.args_schema
        if hasattr(schema, "model_fields"):
            # Pydantic v2
            for name, field in schema.model_fields.items():
                if field.is_required():
                    required.add(name)
        elif hasattr(schema, "__fields__"):
            # Pydantic v1
            for name, field in schema.__fields__.items():
                if field.required:
                    required.add(name)

    return required


__all__ = [
    "validate_mock_parameters",
    "validate_mock_signature",
    "validate_registry_mocks",
]
