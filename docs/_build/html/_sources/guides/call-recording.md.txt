# Call Recording Guide

The `CallRecorder` captures all tool calls during test execution, enabling verification of what tools were called, with what arguments, and in what order.

---

## Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Call Recording Flow                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Agent invokes tool                                                        │
│        │                                                                    │
│        ▼                                                                    │
│   mockable_tool_wrapper                                                     │
│        │                                                                    │
│        ├── Record call → CallRecorder                                      │
│        │     • tool_name                                                    │
│        │     • args                                                         │
│        │     • was_mocked                                                   │
│        │     • duration_ms                                                  │
│        │                                                                    │
│        ├── Execute (mock or real tool)                                      │
│        │                                                                    │
│        └── Record result → CallRecorder                                    │
│              • result                                                       │
│              • error (if any)                                               │
│                                                                             │
│   After agent run:                                                          │
│   recorder.assert_called("tool_name")                                      │
│   recorder.assert_called_with("tool_name", arg="value")                    │
│   recorder.assert_call_order("tool_a", "tool_b", "tool_c")                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Quick Start

```python
from stuntdouble import MockToolsRegistry, CallRecorder, create_mockable_tool_wrapper
from langgraph.prebuilt import ToolNode

# Create registry and recorder
registry = MockToolsRegistry()
recorder = CallRecorder()

# Register mocks
registry.mock("get_customer").returns({"id": "123", "name": "Test Corp"})

# Create wrapper WITH recorder
wrapper = create_mockable_tool_wrapper(registry, recorder=recorder)

# Build your graph
tools = [get_customer, list_bills, create_invoice]
tool_node = ToolNode(tools, awrap_tool_call=wrapper)

# ... add to graph and run agent ...

# Verify calls were made
recorder.assert_called("get_customer")
recorder.assert_not_called("delete_account")
recorder.assert_called_once("list_bills")
recorder.assert_called_times("create_invoice", 2)

# Verify arguments
recorder.assert_called_with("get_customer", customer_id="123")
recorder.assert_last_called_with("list_bills", status="active")

# Verify call order
recorder.assert_call_order("get_customer", "list_bills", "create_invoice")

# Inspect recorded calls
print(recorder.summary())
# Output:
# Recorded 4 call(s):
#   1. get_customer [MOCKED] args={'customer_id': '123'}
#   2. list_bills [MOCKED] args={'status': 'active'}
#   3. create_invoice [MOCKED] args={'amount': 500}
#   4. create_invoice [MOCKED] args={'amount': 1200}
```

---

## Setup

### With Custom Registry

```python
from stuntdouble import MockToolsRegistry, CallRecorder, create_mockable_tool_wrapper

registry = MockToolsRegistry()
recorder = CallRecorder()

# Register your mocks
registry.mock("get_customer").returns({"id": "123", "name": "Test Corp"})
registry.mock("list_bills").returns({"bills": []})

# Pass recorder to the wrapper
wrapper = create_mockable_tool_wrapper(registry, recorder=recorder)
```

### Key Point

The recorder is attached to the **wrapper**, not the registry. Every tool call that passes through the wrapper is recorded, whether mocked or real.

---

## Query Methods

| Method | Description | Return Type |
|--------|-------------|-------------|
| `was_called(tool, **args)` | Check if tool was called (optionally with specific args) | `bool` |
| `call_count(tool)` | Get number of calls to a tool | `int` |
| `get_calls(tool=None)` | Get list of `CallRecord` objects | `list[CallRecord]` |
| `get_last_call(tool)` | Get the most recent call | `CallRecord \| None` |
| `get_first_call(tool)` | Get the first call | `CallRecord \| None` |
| `get_args(tool, call_index=-1)` | Get arguments from a specific call | `dict \| None` |
| `get_result(tool, call_index=-1)` | Get result from a specific call | `Any` |
| `summary()` | Human-readable summary of all calls | `str` |
| `clear()` | Reset recorder for next test | `None` |

### Examples

```python
# Check if a tool was called
if recorder.was_called("get_customer"):
    print("Customer was fetched")

# Check with specific arguments
if recorder.was_called("create_invoice", amount=100):
    print("Invoice for $100 was created")

# Get call count
count = recorder.call_count("list_bills")
print(f"list_bills was called {count} times")

# Get all calls for a tool
calls = recorder.get_calls("create_invoice")
for call in calls:
    print(f"Amount: {call.args['amount']}, Result: {call.result}")

# Get specific call arguments
first_args = recorder.get_args("get_customer", call_index=0)
last_result = recorder.get_result("list_bills")

# Get full summary
print(recorder.summary())
```

---

## Assertion Methods

| Method | Description |
|--------|-------------|
| `assert_called(tool)` | Assert tool was called at least once |
| `assert_not_called(tool)` | Assert tool was never called |
| `assert_called_once(tool)` | Assert tool was called exactly once |
| `assert_called_times(tool, n)` | Assert tool was called exactly n times |
| `assert_called_with(tool, **args)` | Assert **any** call matches the arguments |
| `assert_any_call(tool, **args)` | Alias for `assert_called_with()` |
| `assert_last_called_with(tool, **args)` | Assert the **last** call matches the arguments |
| `assert_call_order(*tools)` | Assert tools were called in the given order |

All assertion methods raise `MockAssertionError` on failure:

```python
from stuntdouble import MockAssertionError

try:
    recorder.assert_called("nonexistent_tool")
except MockAssertionError as e:
    print(f"Assertion failed: {e}")
```

### Examples

```python
# Basic assertions
recorder.assert_called("get_customer")
recorder.assert_not_called("delete_account")
recorder.assert_called_once("list_bills")
recorder.assert_called_times("create_invoice", 2)

# Argument assertions
recorder.assert_called_with("get_customer", customer_id="123")
recorder.assert_last_called_with("list_bills", status="active", limit=10)

# Order assertions
recorder.assert_call_order("get_customer", "list_bills", "create_invoice")
```

---

## CallRecord Properties

Each recorded call is a `CallRecord` with these properties:

| Property | Type | Description |
|----------|------|-------------|
| `tool_name` | `str` | Name of the tool |
| `args` | `dict` | Arguments passed to the tool |
| `result` | `Any` | Return value (mock or real) |
| `error` | `Exception \| None` | Exception if call failed |
| `timestamp` | `float` | Unix timestamp when the call was recorded |
| `was_mocked` | `bool` | Whether a mock was used |
| `duration_ms` | `float` | Call duration in milliseconds |
| `scenario_id` | `str \| None` | Scenario ID from metadata |

### Inspecting CallRecords

```python
from stuntdouble import CallRecord

# Get all calls for a tool
calls = recorder.get_calls("create_invoice")

for call in calls:
    print(f"Tool: {call.tool_name}")
    print(f"Args: {call.args}")
    print(f"Result: {call.result}")
    print(f"Mocked: {call.was_mocked}")
    print(f"Duration: {call.duration_ms}ms")
    print(f"Error: {call.error}")
    print("---")
```

---

## pytest Integration

### Basic Fixture Pattern

```python
import pytest
from stuntdouble import MockToolsRegistry, CallRecorder, create_mockable_tool_wrapper

@pytest.fixture
def recorder():
    """Fresh recorder for each test."""
    return CallRecorder()

@pytest.fixture
def mock_wrapper(recorder):
    """Create wrapper with mocks and recorder."""
    registry = MockToolsRegistry()
    registry.mock("get_customer").returns({"id": "123", "name": "Test Corp"})
    registry.mock("list_bills").returns({"bills": []})
    return create_mockable_tool_wrapper(registry, recorder=recorder)

async def test_customer_workflow(mock_wrapper, recorder):
    # Build graph with wrapper
    tool_node = ToolNode(tools, awrap_tool_call=mock_wrapper)
    # ... build and run graph ...

    # Verify behavior
    recorder.assert_called("get_customer")
    recorder.assert_called_with("get_customer", customer_id="123")
    assert recorder.get_result("get_customer")["name"] == "Test Corp"
```

### Resetting Between Tests

```python
@pytest.fixture(autouse=True)
def reset_recorder(recorder):
    """Clear recorder between tests."""
    yield
    recorder.clear()
```

### Parametrized Tests

```python
@pytest.mark.parametrize("customer_id,expected_name", [
    ("CUST-001", "Acme Corp"),
    ("CUST-002", "Test Inc"),
])
async def test_get_customer(customer_id, expected_name, recorder):
    registry = MockToolsRegistry()
    registry.mock("get_customer").returns({"id": customer_id, "name": expected_name})
    wrapper = create_mockable_tool_wrapper(registry, recorder=recorder)

    # ... run agent ...

    recorder.assert_called_with("get_customer", customer_id=customer_id)
    result = recorder.get_result("get_customer")
    assert result["name"] == expected_name
```

---

## Advanced Patterns

### Verifying Tool Call Sequences

```python
# Ensure the agent follows the expected workflow
recorder.assert_call_order(
    "get_customer",       # First: fetch customer
    "list_bills",         # Second: get their bills
    "create_invoice"      # Third: create a new invoice
)
```

### Checking Call Counts

```python
# Ensure the agent doesn't make redundant calls
assert recorder.call_count("get_customer") == 1, "Should only fetch customer once"
assert recorder.call_count("create_invoice") <= 3, "Should not create too many invoices"
```

### Verifying Mock vs Real Calls

```python
# Check which calls were mocked and which were real
for call in recorder.get_calls():
    if call.was_mocked:
        print(f"{call.tool_name}: MOCKED → {call.result}")
    else:
        print(f"{call.tool_name}: REAL → {call.result}")
```

### Combining with Signature Validation

```python
wrapper = create_mockable_tool_wrapper(
    registry,
    recorder=recorder,
    tools=all_tools,            # Enable signature validation
    validate_signatures=True,   # Validate mock signatures at runtime
)
```

---

## Thread Safety

`CallRecorder` is thread-safe and suitable for concurrent test execution. All methods use internal locking to protect the call list during concurrent access.

---

## See Also

- [Quickstart Guide](quickstart.md) — Getting started with StuntDouble
- [LangGraph Approach](langgraph-integration.md) — Per-invocation mocking
- [MockBuilder Guide](mock-builder.md) — Fluent mock registration API
- [Signature Validation](signature-validation.md) — Catch mock errors early
- [Context-Aware Mocks](context-aware-mocks.md) — Access runtime config in mocks
