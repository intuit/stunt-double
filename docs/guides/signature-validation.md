# Mock Signature Validation Guide

StuntDouble can validate that your mock functions have the same parameter signature as the real tools they're mocking. This catches configuration errors early—either at registration time (fail-fast) or at runtime (safety net).

---

## Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        REGISTRATION TIME                                     │
│  registry.register("tool_name", mock_fn=..., tool=real_tool)                │
│                                      │                                       │
│                          tool provided?                                      │
│                         /           \                                        │
│                       Yes            No                                      │
│                        │              │                                      │
│            validate_mock_signature()  └──► Register without validation      │
│                        │                                                     │
│                 Valid? ──No──► SignatureMismatchError (fail fast)           │
│                   │                                                          │
│                  Yes                                                         │
│                   ▼                                                          │
│              Registered ✓                                                    │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                           RUNTIME                                            │
│  Tool call intercepted by mockable_tool_wrapper                             │
│                              │                                               │
│               validate_signatures=True AND tool in tools?                    │
│                            /                    \                            │
│                          Yes                     No                          │
│                           │                       │                          │
│               validate_mock_signature()      Execute mock                    │
│                           │                                                  │
│                     Valid? ──No──► Raise SignatureMismatchError             │
│                       │                                                      │
│                      Yes                                                     │
│                       │                                                      │
│                       ▼                                                      │
│                  Execute mock → ToolMessage                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Validation Options

There are two independent validation points with separate controls:

| What you want | Registration | Wrapper |
|---------------|--------------|---------|
| **No validation at all** | Omit `tool=` | Set `validate_signatures=False` or omit `tools=` |
| **Registration only** (fail fast) | Pass `tool=real_tool` | Set `validate_signatures=False` or omit `tools=` |
| **Runtime only** (lazy validation) | Omit `tool=` | Pass `tools=all_tools` + `validate_signatures=True` |
| **Both** (belt and suspenders) | Pass `tool=real_tool` | Pass `tools=all_tools` + `validate_signatures=True` |

---

## Registration-Time Validation

Validates immediately when you register the mock. Throws `SignatureMismatchError` if signatures don't match:

```python
from stuntdouble import MockToolsRegistry, SignatureMismatchError

registry = MockToolsRegistry()

# This mock is missing the 'units' parameter
def bad_weather_mock(scenario_metadata):
    def mock_fn(city: str):  # Missing 'units' parameter!
        return {"temp": 72}
    return mock_fn

try:
    registry.register(
        "get_weather",
        mock_fn=bad_weather_mock,
        tool=get_weather_tool,  # ← Passing tool enables validation
    )
except SignatureMismatchError as e:
    print(f"Registration failed: {e}")
    # "Mock for 'get_weather' has mismatched signature.
    #  Missing parameters in mock: units"
```

### How to Enable

Pass the `tool=` parameter to `registry.register()`:

```python
# ✅ Validation enabled — catches errors at registration
registry.register("get_weather", mock_fn=my_mock, tool=get_weather_tool)

# ❌ No validation — errors found later at runtime (or never)
registry.register("get_weather", mock_fn=my_mock)
```

---

## Runtime Validation

Validates each time a mock is about to be executed. On failure, the wrapper raises `SignatureMismatchError`:

```python
from langgraph.prebuilt import ToolNode
from stuntdouble import MockToolsRegistry, create_mockable_tool_wrapper

registry = MockToolsRegistry()
registry.register("get_weather", mock_fn=weather_mock)  # No tool= means no registration validation

# Create wrapper with runtime validation enabled
wrapper = create_mockable_tool_wrapper(
    registry,
    tools=all_tools,           # ← List of tools for validation lookup
    validate_signatures=True,  # ← Enable runtime validation (default)
)

# If mock signature doesn't match at runtime:
# → Raises SignatureMismatchError before the mock executes
node = ToolNode(all_tools, awrap_tool_call=wrapper)
```

### How to Enable

Pass `tools=` and `validate_signatures=True` to `create_mockable_tool_wrapper()`:

```python
# ✅ Runtime validation enabled
wrapper = create_mockable_tool_wrapper(
    registry,
    tools=all_tools,
    validate_signatures=True,  # Default is True when tools= is provided
)

# ❌ Runtime validation disabled
wrapper = create_mockable_tool_wrapper(
    registry,
    validate_signatures=False,
)
```

---

## Validating Scenario Metadata Cases

Use `validate_registry_mocks()` to validate `scenario_metadata["mocks"]` cases against the real tool parameter names before invoking the graph:

```python
from stuntdouble import validate_registry_mocks

errors = validate_registry_mocks(all_tools, scenario_metadata)
if errors:
    raise ValueError(errors)
```

This is especially useful for data-driven mocks where cases are supplied at runtime.

---

## Strict Mock Errors

By default, exceptions raised during mock execution are caught and returned as `ToolMessage(status="error")`, allowing evaluation batch runs to continue collecting results. For unit tests where broken mocks should fail fast, enable `strict_mock_errors`:

```python
wrapper = create_mockable_tool_wrapper(
    registry,
    strict_mock_errors=True,   # Re-raise mock execution errors
)
```

| Mode | `strict_mock_errors` | Behavior on mock exception |
|------|---------------------|---------------------------|
| **Lenient** (default) | `False` | Returns `ToolMessage(status="error")`, agent continues |
| **Strict** | `True` | Re-raises the exception, test fails immediately |

---

## Opting Out

Skip all validation when you trust your mocks or during development:

```python
# Skip registration validation
registry.register("get_weather", mock_fn=weather_mock)  # No tool=

# Skip runtime validation
wrapper = create_mockable_tool_wrapper(
    registry,
    validate_signatures=False,  # ← Disable runtime validation
)
```

---

## What Gets Validated

The `validate_mock_signature` function checks:

1. **Missing parameters**: Mock is missing parameters the tool expects
2. **Extra required parameters**: Mock requires parameters the tool doesn't have
3. **Required/optional mismatch**: Tool has optional param but mock requires it

```python
# Tool signature: get_weather(city: str, units: str = "celsius")

# ✅ Valid - exact match
def mock_fn(city: str, units: str = "celsius"): ...

# ✅ Valid - optional params can have different defaults
def mock_fn(city: str, units: str = "fahrenheit"): ...

# ❌ Invalid - missing 'units' parameter
def mock_fn(city: str): ...

# ❌ Invalid - extra required parameter
def mock_fn(city: str, units: str = "celsius", extra: str): ...

# ❌ Invalid - 'units' should be optional but mock requires it
def mock_fn(city: str, units: str): ...
```

---

## MCP Tool Support

Signature validation works with MCP tools loaded via `langchain-mcp-adapters`. These tools provide JSON Schema dicts instead of Pydantic models, and StuntDouble handles both formats:

| Schema Format | Source | Handling |
|---------------|--------|----------|
| Pydantic model | LangChain native tools | Standard `model_fields` inspection |
| JSON Schema dict | MCP tools via langchain-mcp-adapters | Parses `properties` and `required` fields |

```python
# MCP tools work seamlessly with validation
from langchain_mcp_adapters.client import MultiServerMCPClient

client = MultiServerMCPClient({"mcp-server": {"url": "http://localhost:8080/mcp"}})
mcp_tools = await client.get_tools()  # Tools have JSON Schema args_schema

# StuntDouble validates against JSON Schema automatically
wrapper = create_mockable_tool_wrapper(
    registry,
    tools=mcp_tools,          # ← MCP tools with JSON Schema
    validate_signatures=True,  # ← Works with JSON Schema dicts
)
```

---

## Complete Example

### Belt-and-Suspenders Validation

```python
from stuntdouble import (
    MockToolsRegistry,
    create_mockable_tool_wrapper,
    SignatureMismatchError,
)

# Your real tools
all_tools = [get_weather_tool, get_customer_tool, list_bills_tool]

registry = MockToolsRegistry()

# Registration-time validation (fail fast)
try:
    registry.mock("get_weather").returns({"temp": 72, "conditions": "sunny"})
    # Note: .returns() creates a lambda that accepts **kwargs, so signature
    # validation needs the tool= parameter for manual factories

    # Manual factory with validation
    def weather_mock(md):
        def fn(city: str, units: str = "celsius"):
            return {"temp": 72, "conditions": "sunny", "city": city, "units": units}
        return fn

    registry.register("get_weather", mock_fn=weather_mock, tool=get_weather_tool)
except SignatureMismatchError as e:
    print(f"Fix your mock: {e}")

# Runtime validation (safety net)
wrapper = create_mockable_tool_wrapper(
    registry,
    tools=all_tools,
    validate_signatures=True,
)

tool_node = ToolNode(all_tools, awrap_tool_call=wrapper)
```

### pytest Integration

```python
import pytest
from stuntdouble import MockToolsRegistry, SignatureMismatchError

def test_mock_signature_validation():
    """Test that invalid mock signatures are caught."""
    registry = MockToolsRegistry()

    def bad_mock(md):
        def fn(city: str):  # Missing 'units' parameter
            return {"temp": 72}
        return fn

    with pytest.raises(SignatureMismatchError, match="Missing parameters"):
        registry.register("get_weather", mock_fn=bad_mock, tool=get_weather_tool)

def test_valid_mock_signature():
    """Test that valid mock signatures pass validation."""
    registry = MockToolsRegistry()

    def good_mock(md):
        def fn(city: str, units: str = "celsius"):
            return {"temp": 72, "city": city, "units": units}
        return fn

    # Should not raise
    registry.register("get_weather", mock_fn=good_mock, tool=get_weather_tool)
    assert registry.is_registered("get_weather")
```

---

## API Reference

```python
from stuntdouble import (
    validate_mock_signature,    # Validate mock function signature matches tool
    validate_mock_parameters,   # Validate mock inputs match tool schema
    validate_registry_mocks,    # Validate scenario_metadata mocks against tools
    SignatureMismatchError,     # Raised when mock signature doesn't match tool
)
```

| Function | Description |
|----------|-------------|
| `validate_mock_signature(tool, mock_fn, scenario_metadata, config)` | Validate that a mock function's parameters match the real tool's signature |
| `validate_mock_parameters(tool, cases)` | Validate that mock input patterns match the tool's input schema |
| `validate_registry_mocks(tools, scenario_metadata)` | Validate all runtime mock cases against the provided tools |
| `SignatureMismatchError` | Exception raised when validation fails |

---

## See Also

- [Quickstart Guide](quickstart.md) — Getting started with StuntDouble
- [LangGraph Approach](langgraph-integration.md) — Per-invocation mocking
- [Call Recording](call-recording.md) — Verify tool calls in tests
- [Mock Input Validation Reference](../reference/schema-validation.md) — Validate scenario metadata and tool parameters
