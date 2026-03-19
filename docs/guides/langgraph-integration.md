# LangGraph Integration

Per-invocation mocking via `RunnableConfig`—no environment variables, no global state, fully concurrent.

StuntDouble uses LangGraph's native `ToolNode` with an `awrap_tool_call` wrapper for per-invocation mocking.

---

## Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         LangGraph Per-Invocation Flow                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   graph.invoke(                                                             │
│     state,                              ┌─────────────────────────┐         │
│     config={                            │ Check scenario_metadata │         │
│       "configurable": {                 └───────────┬─────────────┘         │
│         "scenario_metadata": {...}                  │                       │
│       }                                    ┌────────┴────────┐              │
│     }                                      ▼                 ▼              │
│   )                                   Has mocks?       No mocks?            │
│                                            │                 │              │
│                                            ▼                 ▼              │
│                                     Return MOCK      Call REAL tool         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

| Benefit | Description |
|---------|-------------|
| ✅ **Concurrent-safe** | Each invocation has its own mocks |
| ✅ **No global state** | No environment variables or singletons |
| ✅ **Production-ready** | Same graph handles mock and real traffic |
| ✅ **Flexible** | Different mocks per request |

---

## ToolNode Wrapper

Uses LangGraph's native `ToolNode` with StuntDouble's `awrap_tool_call` wrapper.

### Prerequisites

The ToolNode Wrapper requires the `awrap_tool_call` parameter on `ToolNode`, which was introduced in **LangGraph 1.0**. Make sure your dependencies meet these minimum versions:

| Package | Minimum Version | Why |
|---------|----------------|-----|
| `langgraph` | **>=1.0.0** | Provides `ToolNode(awrap_tool_call=...)` parameter |
| `langchain-core` | **>=1.2.5** | Required by StuntDouble for `BaseTool`, `RunnableConfig`, and schema inspection |

```bash
# Verify your versions
pip show langgraph langchain-core

# Upgrade if needed
pip install --upgrade "langgraph>=1.0.0" "langchain-core>=1.2.5"

# Or with uv
uv add "langgraph>=1.0.0" "langchain-core>=1.2.5"

# Or with Poetry
poetry add "langgraph>=1.0.0" "langchain-core>=1.2.5"
```

See [Dependencies Reference](../reference/dependencies.md) for full compatibility details.

### Option A: Default Registry (Simplest) ⭐

Use the pre-configured `mockable_tool_wrapper` and `default_registry` for zero-setup mocking:

```python
from langgraph.graph import StateGraph, MessagesState, START
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.messages import HumanMessage
from stuntdouble import (
    mockable_tool_wrapper,      # Pre-configured wrapper
    default_registry,           # Default mock registry
    inject_scenario_metadata,   # Config helper
)

# Your real tools (production code unchanged)
tools = [get_customer_tool, list_bills_tool, create_invoice_tool]

# Step 1: Register mocks on the default registry
default_registry.mock("get_customer").returns({
    "id": "CUST-001",
    "name": "Test Corp",
    "balance": 1500,
})
default_registry.mock("list_bills").returns({
    "bills": [{"id": "B001", "amount": 500}]
})

# Step 2: Build graph with native ToolNode + mockable wrapper
builder = StateGraph(MessagesState)
builder.add_node("agent", agent_node)
builder.add_node("tools", ToolNode(tools, awrap_tool_call=mockable_tool_wrapper))  # ← Native ToolNode!
builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", tools_condition)
builder.add_edge("tools", "agent")
graph = builder.compile()

# Step 3: Invoke WITH mocks
config = inject_scenario_metadata({}, {
    "scenario_id": "langgraph-default-registry-demo"
})
result = await graph.ainvoke({"messages": [HumanMessage("List my bills")]}, config=config)
# → Uses mocked get_customer / list_bills

# Step 4: Invoke WITHOUT mocks (no scenario_metadata = real tools)
result = await graph.ainvoke({"messages": [HumanMessage("List my bills")]})
# → Uses real list_bills tool
```

**Using the fluent builder on default_registry (even simpler):**

```python
from stuntdouble import default_registry, mockable_tool_wrapper

mock = default_registry.mock  # Convenience: mock("tool").returns(...)

# No registry parameter needed — uses default_registry automatically
mock("get_customer").returns({"id": "123", "name": "Test Corp"})
mock("list_bills").returns({"bills": [{"id": "B001", "amount": 500}]})
mock("get_invoice").when(status={"$in": ["paid", "pending"]}).returns({"priority": "low"})

# Verify registration
print(default_registry.list_registered())  # ['get_customer', 'list_bills', 'get_invoice']

# Use the pre-configured wrapper (reads from default_registry)
tool_node = ToolNode(tools, awrap_tool_call=mockable_tool_wrapper)
```

### Option B: Custom Registry (Full Control)

For advanced scenarios where you need multiple registries, custom wrappers, call recording, or signature validation:

```python
from typing import Any, Callable
from langgraph.graph import StateGraph, MessagesState, START
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.messages import HumanMessage
from stuntdouble import (
    MockToolsRegistry,
    create_mockable_tool_wrapper,
    inject_scenario_metadata,
)

# Your real tools
tools = [get_customer_tool, list_bills_tool]

# Step 1: Define mock functions
# Each mock_fn takes scenario_metadata and returns a callable that matches
# the real tool's signature (accepts the same arguments).

def get_customer_mock(scenario_metadata: dict[str, Any]) -> Callable[..., Any]:
    """
    Mock for get_customer tool.
    
    Real tool signature: get_customer(user_id: str) -> dict
    """
    mocks = scenario_metadata.get("mocks", {})
    mock_data = mocks.get("get_customer", [])
    
    if isinstance(mock_data, list) and mock_data:
        data = mock_data[0].get("output", {})
    else:
        data = mock_data if isinstance(mock_data, dict) else {}
    
    # Mock callable matches real tool signature
    def mock_fn(user_id: str) -> dict:
        # Can use input values in response, or return static mock data
        return data or {"id": user_id, "name": "Test Corp", "status": "active"}
    
    return mock_fn

def list_bills_mock(scenario_metadata: dict[str, Any]) -> Callable[..., Any]:
    """
    Mock for list_bills tool.
    
    Real tool signature: list_bills(start_date: str, end_date: str) -> dict
    """
    mocks = scenario_metadata.get("mocks", {})
    mock_data = mocks.get("list_bills", [])
    
    if isinstance(mock_data, list) and mock_data:
        data = mock_data[0].get("output", {})
    else:
        data = {}
    
    bills = data.get("bills", [])
    
    # Mock callable matches real tool signature
    def mock_fn(start_date: str, end_date: str) -> dict:
        # Can filter based on input args if needed
        return {"bills": bills, "start_date": start_date, "end_date": end_date}
    
    return mock_fn

# Step 2: Create registry and register mock functions
registry = MockToolsRegistry()
registry.register("get_customer", mock_fn=get_customer_mock)
registry.register("list_bills", mock_fn=list_bills_mock)

# Step 3: Create wrapper and build graph with native ToolNode
wrapper = create_mockable_tool_wrapper(registry)

builder = StateGraph(MessagesState)
builder.add_node("agent", agent_node)
builder.add_node("tools", ToolNode(tools, awrap_tool_call=wrapper))  # ← Native ToolNode!
builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", tools_condition)
builder.add_edge("tools", "agent")
graph = builder.compile()

# Step 4: Invoke WITH mocks
config = inject_scenario_metadata({}, {
    "mocks": {
        "list_bills": [{"output": {"bills": [{"id": "B001", "amount": 500}]}}]
    }
})
result = await graph.ainvoke(
    {"messages": [HumanMessage("Get customer CUST-001")]},
    config=config
)

# Step 5: Invoke WITHOUT mocks (production mode - no scenario_metadata)
result = await graph.ainvoke(
    {"messages": [HumanMessage("Get customer CUST-001")]}
)
```

### API Reference

```python
# LangGraph package exports
from stuntdouble import (
    # Pre-configured wrapper and registry
    mockable_tool_wrapper,             # Ready-to-use awrap_tool_call wrapper
    default_registry,                  # Default MockToolsRegistry instance

    # Factory functions
    create_mockable_tool_wrapper,      # Create wrapper with custom registry

    # Mock registration
    MockToolsRegistry,                 # Factory-based mock registration
    MockBuilder,                       # Chainable mock builder (also: from stuntdouble import MockBuilder)

    # Fluent builder: mock = default_registry.mock (no standalone mock function)
    # Call recording
    CallRecorder,                      # Records tool calls for verification
    CallRecord,                        # Individual call record

    # Config utilities
    inject_scenario_metadata,          # Add scenario_metadata to config
    get_scenario_metadata,             # Extract from ToolCallRequest
    get_configurable_context,          # Extract configurable dict from RunnableConfig

    # Validation
    validate_mock_parameters,          # Validate mock inputs match tool schema
    validate_mock_signature,           # Validate mock function signature matches tool
    validate_registry_mocks,           # Validate scenario_metadata mock cases

    # Exceptions
    MissingMockError,                  # Raised when mock not found in strict mode
    SignatureMismatchError,            # Raised when mock signature doesn't match tool
    MockAssertionError,                # Raised by CallRecorder assertions
)
```

| Function | Description |
|----------|-------------|
| `mockable_tool_wrapper` | Pre-configured wrapper for `ToolNode(tools, awrap_tool_call=...)` using `default_registry` |
| `default_registry` | Default `MockToolsRegistry` used by `mockable_tool_wrapper` |
| `create_mockable_tool_wrapper(registry, recorder=, tools=, validate_signatures=, require_mock_when_scenario=, strict_mock_errors=)` | Create wrapper with custom registry, optional recorder, validation, and error-handling controls |
| `default_registry.mock(tool_name)` | Convenience returning `MockBuilder`. Use `mock = default_registry.mock` for shorthand. |
| `MockBuilder(tool_name, registry)` | Chainable builder: `.when()`, `.returns()`, `.returns_fn()`, `.echoes_input()` |
| `MockToolsRegistry()` | Create a registry for mock functions |
| `registry.register(tool_name, mock_fn, when=None, tool=None)` | Register a mock function. Pass `tool=` for signature validation. |
| `CallRecorder()` | Records tool calls for test assertions |
| `CallRecord` | Individual call record with `tool_name`, `args`, `result`, `was_mocked`, etc. |
| `inject_scenario_metadata(config, metadata)` | Create config with scenario_metadata |
| `get_configurable_context(config)` | Extract the `configurable` dict from RunnableConfig for context-aware mocks |
| `validate_mock_signature(tool, mock_fn, scenario_metadata, config)` | Validate mock function signature matches tool |
| `validate_registry_mocks(tools, scenario_metadata)` | Validate `scenario_metadata["mocks"]` against tool parameters |

### Troubleshooting

#### Mocks Not Working

1. **Check you're using the wrapper:**
   ```python
   # Default registry approach
   from stuntdouble import mockable_tool_wrapper
   ToolNode(tools, awrap_tool_call=mockable_tool_wrapper)  # ← Required!

   # Or custom registry approach
   wrapper = create_mockable_tool_wrapper(registry)
   ToolNode(tools, awrap_tool_call=wrapper)  # ← Required!
   ```

2. **Check scenario_metadata is passed:**
   ```python
   config = inject_scenario_metadata({}, {"mocks": {...}})
   result = await graph.ainvoke(state, config=config)
   ```

3. **Check mock is registered:**
   ```python
   # Default registry
   from stuntdouble import default_registry
   print(default_registry.list_registered())  # Should include your tool name

   # Custom registry
   print(registry.list_registered())  # Should include your tool name
   ```

4. **Check `when` predicate returns True:**
   ```python
   # If using `when=`, ensure it returns True for your scenario
   default_registry.register("tool", mock_fn=..., when=lambda md: md.get("mode") == "test")
   ```

### CallRecorder: Tool Call Verification

The `CallRecorder` captures all tool calls during test execution, enabling verification of what tools were called, with what arguments, and how many times.

#### Quick Start

```python
from stuntdouble import (
    MockToolsRegistry,
    CallRecorder,
    create_mockable_tool_wrapper,
)
from langgraph.prebuilt import ToolNode

# Create registry and recorder
registry = MockToolsRegistry()
recorder = CallRecorder()

# Register mocks
mock = registry.mock
mock("get_customer").returns({"id": "123", "name": "Test Corp"})

# Create wrapper with recorder
wrapper = create_mockable_tool_wrapper(registry, recorder=recorder)

# Build your graph
tools = [get_customer, list_bills, create_invoice]
tool_node = ToolNode(tools, awrap_tool_call=wrapper)

# ... run your agent ...

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
```

#### API Reference

```python
from stuntdouble import CallRecorder, CallRecord, MockAssertionError

recorder = CallRecorder()
```

#### Query Methods

| Method | Description | Example |
|--------|-------------|---------|
| `was_called(tool, **args)` | Check if tool was called (optionally with specific args) | `recorder.was_called("get_customer", customer_id="123")` |
| `call_count(tool)` | Get number of calls to a tool | `recorder.call_count("list_bills")` |
| `get_calls(tool=None)` | Get list of `CallRecord` objects | `recorder.get_calls("get_customer")` |
| `get_last_call(tool)` | Get the most recent call | `recorder.get_last_call("list_bills")` |
| `get_first_call(tool)` | Get the first call | `recorder.get_first_call("get_customer")` |
| `get_args(tool, index=-1)` | Get arguments from a specific call | `recorder.get_args("get_customer", 0)` |
| `get_result(tool, index=-1)` | Get result from a specific call | `recorder.get_result("create_invoice")` |
| `summary()` | Human-readable summary of all calls | `print(recorder.summary())` |
| `clear()` | Reset recorder for next test | `recorder.clear()` |

#### Assertion Methods

All assertion methods raise `MockAssertionError` on failure.

| Method | Description | Example |
|--------|-------------|---------|
| `assert_called(tool)` | Assert tool was called at least once | `recorder.assert_called("get_customer")` |
| `assert_not_called(tool)` | Assert tool was never called | `recorder.assert_not_called("delete_account")` |
| `assert_called_once(tool)` | Assert tool was called exactly once | `recorder.assert_called_once("list_bills")` |
| `assert_called_times(tool, n)` | Assert tool was called exactly n times | `recorder.assert_called_times("create_invoice", 2)` |
| `assert_called_with(tool, **args)` | Assert any call matches the arguments | `recorder.assert_called_with("get_customer", customer_id="123")` |
| `assert_last_called_with(tool, **args)` | Assert last call matches the arguments | `recorder.assert_last_called_with("list_bills", status="active")` |
| `assert_call_order(*tools)` | Assert tools were called in order | `recorder.assert_call_order("get_customer", "list_bills")` |

#### CallRecord Properties

Each recorded call is a `CallRecord` with these properties:

| Property | Description | Example |
|----------|-------------|---------|
| `tool_name` | Name of the tool | `"get_customer"` |
| `args` | Arguments passed to the tool | `{"customer_id": "123"}` |
| `result` | Return value (mock or real) | `{"id": "123", "name": "Test Corp"}` |
| `error` | Exception if call failed | `None` or `ValueError(...)` |
| `was_mocked` | Whether a mock was used | `True` or `False` |
| `duration_ms` | Call duration in milliseconds | `5.2` |
| `timestamp` | Unix timestamp when call was made | `1704567890.123` |
| `scenario_id` | Scenario ID from metadata | `"test-001"` or `None` |

#### Examples

##### Basic Verification

```python
recorder = CallRecorder()
wrapper = create_mockable_tool_wrapper(registry, recorder=recorder)

# After running agent
recorder.assert_called("get_customer")
recorder.assert_not_called("delete_account")
assert recorder.call_count("list_bills") == 1
```

##### Argument Verification

```python
# Verify any call matches
recorder.assert_called_with("get_customer", customer_id="123")

# Verify last call matches
recorder.assert_last_called_with("list_bills", status="active", limit=10)

# Check if called with specific args
if recorder.was_called("create_invoice", amount=100):
    print("Invoice created for $100")
```

##### Call Order Verification

```python
# Verify tools were called in specific order
recorder.assert_call_order("get_customer", "list_bills", "create_invoice")
```

##### Inspecting Calls

```python
# Get all calls for a tool
calls = recorder.get_calls("create_invoice")
for call in calls:
    print(f"Amount: {call.args['amount']}, Result: {call.result}")

# Get specific call arguments
first_args = recorder.get_args("get_customer", index=0)
last_result = recorder.get_result("list_bills")

# Get full summary
print(recorder.summary())
# Output:
# Recorded 4 call(s):
#   1. get_customer [MOCKED] args={'customer_id': '123'}
#   2. list_bills [MOCKED] args={'status': 'active'}
#   3. create_invoice [MOCKED] args={'amount': 500}
#   4. create_invoice [MOCKED] args={'amount': 1200}
```

##### Testing with pytest

```python
import pytest
from stuntdouble import (
    MockToolsRegistry,
    CallRecorder,
    create_mockable_tool_wrapper,
)

@pytest.fixture
def recorder():
    return CallRecorder()

@pytest.fixture
def mock_wrapper(recorder):
    registry = MockToolsRegistry()
    registry.mock("get_customer").returns({"id": "123", "name": "Test Corp"})
    return create_mockable_tool_wrapper(registry, recorder=recorder)

def test_customer_workflow(mock_wrapper, recorder):
    # Build graph with wrapper
    tool_node = ToolNode(tools, awrap_tool_call=mock_wrapper)
    # ... run agent ...
    
    # Verify behavior
    recorder.assert_called("get_customer")
    recorder.assert_called_with("get_customer", customer_id="123")
    assert recorder.get_result("get_customer")["name"] == "Test Corp"
```

#### Thread Safety

`CallRecorder` is thread-safe and suitable for concurrent test execution. All methods use internal locking to protect the call list during concurrent access.

---

## Shared Concepts

The following concepts apply to the ToolNode Wrapper approach.

### MockBuilder: Fluent Mock Registration

The `MockBuilder` provides a fluent, chainable API for registering mocks. See the [MockBuilder Guide](../guides/mock-builder.md) for complete documentation and examples.

Quick example with explicit registry:

```python
from stuntdouble import MockToolsRegistry

registry = MockToolsRegistry()
mock = registry.mock

# Simple static mock
mock("get_customer").returns({"id": "123", "name": "Test Corp"})

# Conditional mock with input matching
mock("list_bills").when(status="active").returns({"bills": [{"id": "B001"}]})

# Echo input fields in response
mock("update_customer").echoes_input("customer_id", "name").returns({"updated": True})

# Custom mock function
mock("calculate_total").returns_fn(
    lambda items, tax_rate: {"total": sum(i["price"] for i in items) * (1 + tax_rate)}
)

# Combine conditions with operators
mock("get_invoice").when(
    status={"$in": ["paid", "pending"]},
    amount={"$gt": 100}
).returns({"priority": "high"})
```

Quick example with default registry:

```python
from stuntdouble import default_registry

mock = default_registry.mock  # Uses default_registry

# Register mocks
mock("get_customer").returns({"id": "123", "name": "Mocked"})
mock("list_bills").when(status="active").returns({"bills": []})

# Verify
assert default_registry.is_registered("get_customer")
```

→ [Full MockBuilder Guide](../guides/mock-builder.md)

### Mocked Tool Patterns

Mocked tools are functions that receive `scenario_metadata` and return a mock callable. Below are all supported patterns with sample inputs and outputs.

#### Pattern 1: Static Mock

Always returns the same response regardless of input.

```python
# Sample input:  get_weather(city="NYC")
# Sample output: {"temp": 72, "conditions": "sunny"}

registry.register(
    "get_weather",
    mock_fn=lambda md: lambda **kwargs: {"temp": 72, "conditions": "sunny"}
)
```

#### Pattern 2: Input-Echo Mock

Response includes values from the tool input.

```python
# Sample input:  get_customer(customer_id="CUST-123")
# Sample output: {"id": "CUST-123", "name": "Test Corp", "status": "active"}

registry.register(
    "get_customer",
    mock_fn=lambda md: lambda customer_id, **kw: {
        "id": customer_id,  # Echo the input
        "name": "Test Corp",
        "status": "active"
    }
)
```

#### Pattern 3: Mocks-Based Mock (Data-Driven)

Mock data comes from the `scenario_metadata.mocks` structure. Write a factory that extracts data from `scenario_metadata`:

```python
from typing import Callable

def list_bills_mock(scenario_metadata: dict) -> Callable:
    mocks = scenario_metadata.get("mocks", {})
    mock_data = mocks.get("list_bills", [])
    
    if isinstance(mock_data, list) and mock_data:
        data = mock_data[0].get("output", {})
    else:
        data = {}
    
    return lambda **kwargs: data

registry.register("list_bills", mock_fn=list_bills_mock)
```

#### Pattern 4: Conditional Mock (with `when` predicate)

Only mock under certain conditions; otherwise call the real tool.

```python
# Sample scenario_metadata (MOCKED):
#   {"mode": "test", "mocks": {"send_email": [{"output": {"sent": true}}]}}
#
# Sample scenario_metadata (NOT MOCKED - calls real tool):
#   {"mode": "production"}
#
# Sample input:  send_email(to="user@example.com", body="Hello")
# Sample output: {"sent": True, "message_id": "mock-123"}

registry.register(
    "send_email",
    mock_fn=lambda md: lambda **kw: {"sent": True, "message_id": "mock-123"},
    when=lambda md: md.get("mode") == "test"  # Only mock in test mode
)
```

#### Pattern 5: Dynamic Placeholders

Outputs can include dynamic placeholders for timestamps, UUIDs, and input references. Use data-driven mocks via `register_data_driven()` / `DataDrivenMockFactory`, or implement placeholder resolution in your own mock factory. See [Mock Format Reference](../reference/mock-format.md) for supported placeholder syntax.

**Supported placeholders:**

| Placeholder | Description | Example Output |
|------------|-------------|----------------|
| `{{now}}` | Current ISO timestamp | `2026-02-12T10:30:00` |
| `{{now + Nd}}` | N days from now | `{{now + 7d}}` → 7 days later |
| `{{now - Nd}}` | N days ago | `{{now - 30d}}` → 30 days ago |
| `{{today}}` | Current date only | `2026-02-12` |
| `{{input.field}}` | Reference input value | Echoes input |
| `{{uuid}}` | Random UUID | `a1b2c3d4-e5f6-...` |
| `{{random_int(min, max)}}` | Random integer | `42` |
| `{{sequence('prefix')}}` | Incrementing ID | `prefix-001`, `prefix-002` |

See [Mock Format Reference](../reference/mock-format.md) for all placeholders.

#### Pattern 6: Context-Aware Mock (Runtime Config Access)

Access runtime context (like user identity from HTTP headers) in your mock factory. This is especially useful for **no-argument tools** that need to return user-specific data.

```python
from stuntdouble import get_configurable_context

# Sample RunnableConfig (passed by your application):
#   {
#     "configurable": {
#       "agent_context": {
#         "auth_header": {
#           "user_id": "USER-123",
#           "org_id": "ORG-456"
#         }
#       }
#     }
#   }
#
# Sample input:  get_current_user()  # No arguments!
# Sample output: {"user_id": "USER-123", "org_id": "ORG-456"}

def user_context_mock(scenario_metadata: dict, config: dict = None):
    """Mock factory that extracts user context from RunnableConfig."""
    ctx = get_configurable_context(config)

    # Application-specific extraction (your app knows its structure)
    agent_context = ctx.get("agent_context", {})
    auth_header = agent_context.get("auth_header", {})
    user_id = auth_header.get("user_id", "unknown")
    org_id = auth_header.get("org_id", "unknown")

    # Return the mock callable
    return lambda: {"user_id": user_id, "org_id": org_id}

registry.register("get_current_user", mock_fn=user_context_mock)
```

**Key Points:**
- Mock factories can accept an **optional second parameter** `config` (the `RunnableConfig`)
- Use `get_configurable_context(config)` to safely extract the `configurable` dict
- **Backward compatible**: Existing factories with only `scenario_metadata` continue to work
- The `config` parameter is detected via signature inspection—no registration changes needed

**When to Use:**
- No-argument tools that need runtime context (user ID, tenant ID, etc.)
- Mocks that need to vary based on request headers
- Multi-tenant testing scenarios

→ [Full Context-Aware Mocks Guide](../guides/context-aware-mocks.md)

---

### scenario_metadata Structure

```python
scenario_metadata = {
    # Optional: Scenario identifier
    "scenario_id": "test-001",
    
    # Optional: Mode indicator
    "mode": "test",
    
    # Mock definitions by tool name
    "mocks": {
        "tool_name": [
            {
                "input": {...},   # Optional: Input pattern to match
                "output": {...}   # Required: Output to return
            },
            {
                "output": {...}   # Catch-all (no input pattern)
            }
        ]
    }
}
```

---

### Input Matching

Match inputs with operators for conditional responses:

```python
scenario_metadata = {
    "mocks": {
        "get_bills": [
            {"input": {"status": "overdue", "amount": {"$gt": 5000}}, "output": {"priority": "URGENT"}},
            {"input": {"status": {"$in": ["paid", "pending"]}}, "output": {"priority": "low"}},
            {"output": {"priority": "normal"}}  # Catch-all
        ]
    }
}
```

See [Mock Format Reference](../reference/mock-format.md) for all operators and [Matchers and Resolvers Guide](../guides/matchers-and-resolvers.md) for detailed examples.

---

### Dynamic Placeholders

Outputs can include dynamic placeholders:

```python
scenario_metadata = {
    "mocks": {
        "create_invoice": [{
            "output": {
                "id": "{{uuid}}",
                "created_at": "{{now}}",
                "due_date": "{{now + 30d}}",
                "customer_id": "{{input.customer_id}}"
            }
        }]
    }
}
```

See [Mock Format Reference](../reference/mock-format.md) for all placeholders.

---

### Custom Mocked Tools

StuntDouble's LangGraph mocking uses **mocked tools**. The format of your mock data is defined by the mocked tool function—not by the framework.

#### Mocked Tool Signature

Standard (1-parameter) and context-aware (2-parameter) signatures:

```python
from typing import Any, Callable

# Standard factory: receives scenario_metadata only
def my_mocked_tool(scenario_metadata: dict[str, Any]) -> Callable[..., Any] | None:
    """
    Args:
        scenario_metadata: The scenario configuration for this invocation
        
    Returns:
        A callable mock function, or None to skip mocking (use real tool)
    """
    # 1. Extract your mock data from scenario_metadata
    # 2. Return a callable that handles tool invocations
    # 3. Return None if mocking shouldn't apply
    pass

# Context-aware factory: receives scenario_metadata AND config
def my_context_mock(scenario_metadata: dict[str, Any], config: dict = None) -> Callable[..., Any] | None:
    """
    Args:
        scenario_metadata: The scenario configuration for this invocation
        config: The RunnableConfig with runtime context (optional)
        
    Returns:
        A callable mock function, or None to skip mocking (use real tool)
    """
    ctx = get_configurable_context(config)
    # Use ctx for runtime context like user identity, headers, etc.
    pass
```

#### Example: Custom Key Name

Use `"responses"` instead of `"mocks"`:

```python
# Sample scenario_metadata: {"responses": {"my_tool": {"data": "custom"}}}
# Sample input:  my_tool(query="test")
# Sample output: {"data": "custom"}

def responses_factory(tool_name: str):
    def factory(scenario_metadata: dict) -> Callable | None:
        responses = scenario_metadata.get("responses", {})
        tool_data = responses.get(tool_name)
        
        if tool_data is None:
            return None  # No mock, use real tool
        
        return lambda **kwargs: tool_data
    
    return factory

registry.register("my_tool", mock_fn=responses_factory("my_tool"))
```

#### Example: Stateful Factory

Return sequences of responses (first call, second call, etc.):

```python
# Sample scenario_metadata: {"sequences": {"api_call": [{"attempt": 1}, {"attempt": 2}, {"attempt": 3}]}}
# Sample input:  api_call(url="https://api.com")
# Call 1 output: {"attempt": 1}
# Call 2 output: {"attempt": 2}
# Call 3 output: {"attempt": 3}
# Call 4 output: {"attempt": 3}  (stays on last)

def sequence_factory(tool_name: str):
    def factory(scenario_metadata: dict) -> Callable | None:
        sequence = scenario_metadata.get("sequences", {}).get(tool_name, [])
        if not sequence:
            return None
        
        call_count = [0]
        
        def sequenced_mock(**kwargs):
            idx = min(call_count[0], len(sequence) - 1)
            call_count[0] += 1
            return sequence[idx]
        
        return sequenced_mock
    
    return factory

registry.register("api_call", mock_fn=sequence_factory("api_call"))
```

#### Example: Tenant-Aware Factory

Use runtime config for multi-tenant mocking:

```python
# Sample RunnableConfig: {"configurable": {"agent_context": {"tenant_id": "tenant-a"}}}
# Sample input:  get_tenant_config()
# Sample output: {"plan": "enterprise", "max_users": 1000}

from stuntdouble import get_configurable_context

def tenant_factory(scenario_metadata: dict, config: dict = None):
    ctx = get_configurable_context(config)
    tenant_id = ctx.get("agent_context", {}).get("tenant_id", "default")

    tenant_configs = {
        "tenant-a": {"plan": "enterprise", "max_users": 1000},
        "tenant-b": {"plan": "startup", "max_users": 10},
        "default": {"plan": "free", "max_users": 1},
    }

    data = tenant_configs.get(tenant_id, tenant_configs["default"])
    return lambda: data

registry.register("get_tenant_config", mock_fn=tenant_factory)
```

---

### Best Practices

#### 1. Register at Startup

```python
registry = MockToolsRegistry()

# Register all mocks before graph compilation
registry.register("tool_a", mock_fn=tool_a_mock)
registry.register("tool_b", mock_fn=tool_b_mock)

# Then build graph
wrapper = create_mockable_tool_wrapper(registry)
builder.add_node("tools", ToolNode(tools, awrap_tool_call=wrapper))
```

#### 2. Keep Mocked Tools Pure

```python
# Good: Fresh callable each time
mock_fn=lambda md: lambda **kw: {"data": md.get("value")}

# Bad: Side effects
def mocked_tool(md):
    print("Creating mock")  # Side effect!
    return lambda **kw: {...}
```

#### 3. Enable Logging for Debugging

```python
import logging
logging.getLogger("stuntdouble").setLevel(logging.DEBUG)
```

---

### Mock Signature Validation

StuntDouble can validate that your mock functions have the same parameter signature as the real tools they mock. This catches configuration errors early.

#### Validation Points

| Point | Control | Behavior on Mismatch |
|-------|---------|---------------------|
| **Registration** | Pass `tool=` to `registry.register()` | Raises `SignatureMismatchError` immediately |
| **Runtime** | Pass `tools=` and `validate_signatures=True` to wrapper | Raises `SignatureMismatchError` |

#### Controlling Validation

There are two independent validation points with separate controls:

| What you want | Registration | Wrapper |
|---------------|--------------|---------|
| **No validation at all** | Omit `tool=` | Set `validate_signatures=False` or omit `tools=` |
| **Registration only** (fail fast) | Pass `tool=real_tool` | Set `validate_signatures=False` or omit `tools=` |
| **Runtime only** (lazy validation) | Omit `tool=` | Pass `tools=all_tools` + `validate_signatures=True` |
| **Both** (belt and suspenders) | Pass `tool=real_tool` | Pass `tools=all_tools` + `validate_signatures=True` |

#### Example: Registration-Time Validation

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

#### Example: Runtime Validation

Validates each time a mock is about to be executed. On failure, raises `SignatureMismatchError`:

```python
from stuntdouble import create_mockable_tool_wrapper

# Create wrapper with runtime validation
wrapper = create_mockable_tool_wrapper(
    registry,
    tools=all_tools,           # ← List of tools for validation
    validate_signatures=True,  # ← Enable runtime validation (default)
)

# If mock signature doesn't match at runtime:
# → Raises SignatureMismatchError before the mock executes
```

#### What Gets Validated

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

#### Opting Out

```python
# Skip registration validation
registry.register("get_weather", mock_fn=my_mock)  # No tool=

# Skip runtime validation
wrapper = create_mockable_tool_wrapper(
    registry,
    validate_signatures=False,  # ← Disable runtime validation
)
```

#### MCP Tool Support

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

→ [Full Signature Validation Guide](../guides/signature-validation.md)

---

## Using Mirrored Tools

MCP Tool Mirroring auto-generates mock tools from MCP server schemas. These mirrored tools integrate seamlessly with LangGraph's per-invocation mocking.

### Quick Start with Mirroring

```python
from stuntdouble.mirroring import ToolMirror
from stuntdouble import (
    MockToolsRegistry,
    create_mockable_tool_wrapper,
    inject_scenario_metadata,
)
from langgraph.prebuilt import ToolNode

# 1. Mirror tools from MCP server
mirror = ToolMirror()
mirror.mirror(["python", "-m", "my_mcp_server"])
tools = mirror.to_langchain_tools()

# 2. Create registry and wrapper
registry = MockToolsRegistry()
wrapper = create_mockable_tool_wrapper(registry)

# 3. Build graph with mirrored tools
builder = StateGraph(MessagesState)
builder.add_node("agent", agent_node)
builder.add_node("tools", ToolNode(tools, awrap_tool_call=wrapper))
builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", tools_condition)
builder.add_edge("tools", "agent")
graph = builder.compile()

# 4. Invoke - mirrored tools return generated mock data
result = await graph.ainvoke({"messages": [HumanMessage("Create an invoice")]})
```

### LangGraph-Optimized Mirroring

Use `ToolMirror.for_langgraph()` for a mirror pre-configured for LangGraph integration:

```python
from stuntdouble.mirroring import ToolMirror

# Optimized for LangGraph: generates mock functions compatible with registry
mirror = ToolMirror.for_langgraph()
mirror.mirror(["python", "-m", "my_mcp_server"])
tools = mirror.to_langchain_tools()
```

### Mirroring with HTTP Authentication

Mirror from remote MCP servers behind authentication:

```python
from stuntdouble.mirroring import ToolMirror

mirror = ToolMirror()

# Bearer token authentication
result = mirror.mirror(
    http_url="https://api.example.com/mcp",
    headers={"Authorization": "Bearer your-token-here"}
)

# API key authentication
result = mirror.mirror(
    http_url="http://localhost:8080",
    headers={"X-API-Key": "abc123", "X-Client-ID": "my-app"}
)

tools = mirror.to_langchain_tools()
```

### Mirroring with LangGraph Registry Integration

For advanced scenarios, mirror tools directly into the LangGraph mock registry:

```python
from stuntdouble.mirroring import ToolMirror
from stuntdouble import MockToolsRegistry

# Create registry first
registry = MockToolsRegistry()

# Mirror tools and register them in the LangGraph registry
mirror = ToolMirror.for_langgraph(registry=registry)
mirror.mirror(["python", "-m", "my_server"])

# Registry now contains mock functions for all mirrored tools
print(registry.list_registered())
# ['create_invoice', 'get_customer', 'list_bills', ...]
```

### Combining with Custom Mocks

Override specific mirrored tools with custom behavior:

```python
from stuntdouble.mirroring import ToolMirror
from stuntdouble import MockToolsRegistry

registry = MockToolsRegistry()

# Mirror all tools
mirror = ToolMirror.for_langgraph(registry=registry)
mirror.mirror(["python", "-m", "my_server"])

# Override specific tool with custom mock
registry.mock("get_customer").returns({
    "id": "CUST-001",
    "name": "Test Corp",
    "tier": "platinum"
})

# get_customer uses custom mock, others use generated mocks
```

→ See the [MCP Tool Mirroring Guide](../guides/mcp-mirroring.md) for complete documentation.

