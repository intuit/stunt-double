# MockBuilder: Fluent Mock Registration

The `MockBuilder` provides a chainable API for registering mocks, making common mocking patterns more concise and readable.

---

## Quick Start

```python
from stuntdouble import MockToolsRegistry

registry = MockToolsRegistry()

# Simple static mock
registry.mock("get_customer").returns({"id": "123", "name": "Test Corp"})

# Conditional mock with input matching
registry.mock("list_bills").when(status="active").returns({"bills": [{"id": "B001"}]})

# Echo input fields back in response
registry.mock("create_user").echoes_input("user_id", "email").returns({"status": "created"})
```

---

## Using the Default Registry

For quick testing and prototyping, you can use `default_registry.mock()` from `stuntdouble.langgraph` without an explicit registry:

```python
from stuntdouble import default_registry

# No registry parameter needed—uses default_registry
default_registry.mock("get_customer").returns({"id": "123", "name": "Mocked"})

# Conditional mock
default_registry.mock("list_bills").when(status="active").returns({"bills": []})

# Echo input
default_registry.mock("create_invoice").echoes_input("customer_id").returns({"status": "created"})

# Verify registration
assert default_registry.is_registered("get_customer")
assert default_registry.is_registered("list_bills")
assert default_registry.is_registered("create_invoice")
print(default_registry.list_registered())
# ['get_customer', 'list_bills', 'create_invoice']
```

This is ideal when using the pre-configured `mockable_tool_wrapper`:

```python
from langgraph.prebuilt import ToolNode
from stuntdouble import default_registry, mockable_tool_wrapper

# Register mocks (automatically on default_registry)
default_registry.mock("get_customer").returns({"id": "123", "name": "Test Corp"})
default_registry.mock("list_bills").returns({"bills": []})

# Use the pre-configured wrapper (reads from default_registry)
tool_node = ToolNode(tools, awrap_tool_call=mockable_tool_wrapper)
```

---

## API Reference

```python
from stuntdouble import MockToolsRegistry

registry = MockToolsRegistry()

# Fluent API via registry
registry.mock(tool_name: str) -> MockBuilder

# Default registry (no explicit registry needed)
from stuntdouble import default_registry
default_registry.mock(tool_name: str) -> MockBuilder
```

---

## Methods

| Method | Description | Example |
|--------|-------------|---------|
| `.returns(value)` | Register mock that returns a static value | `reg.mock("tool").returns({"data": 1})` |
| `.returns_fn(fn)` | Register mock that uses a callable | `reg.mock("tool").returns_fn(lambda **kw: {...})` |
| `.when(predicate=None, **conditions)` | Add a scenario predicate, input conditions, or both | `reg.mock("tool").when(status="active")` |
| `.echoes_input(*fields)` | Echo input fields in response | `reg.mock("tool").echoes_input("id", "name")` |

---

## Examples

### Static Return Value

```python
from stuntdouble import MockToolsRegistry

registry = MockToolsRegistry()
registry.mock("get_weather").returns({"temp": 72, "conditions": "sunny"})
```

Or with default registry:

```python
from stuntdouble import default_registry

default_registry.mock("get_weather").returns({"temp": 72, "conditions": "sunny"})
```

### Conditional Mocking

```python
# Gate on scenario metadata
registry.mock("send_email").when(
    lambda md: md.get("mode") == "test"
).returns({"sent": True})

# Match specific input values
registry.mock("get_customer").when(customer_id="VIP-001").returns({"tier": "platinum"})

# Match with operators
registry.mock("list_bills").when(status={"$in": ["paid", "pending"]}).returns({"priority": "low"})

# Multiple conditions (AND logic)
registry.mock("get_bills").when(status="overdue", amount={"$gt": 5000}).returns({"priority": "URGENT"})

# Combine with operators
registry.mock("get_invoice").when(
    status={"$in": ["paid", "pending"]},
    amount={"$gt": 100}
).returns({"priority": "high"})
```

### Input Echoing

```python
# Echo specific input fields in response
registry.mock("create_invoice").echoes_input("customer_id", "amount").returns({"status": "created"})

# This creates a mock that returns:
# {
#     "customer_id": <input value>,
#     "amount": <input value>,
#     "status": "created"
# }
```

### Custom Callable

```python
import time

# Use a function for dynamic responses
def dynamic_mock(**kwargs):
    return {"id": kwargs.get("id"), "timestamp": time.time()}

registry.mock("create_record").returns_fn(dynamic_mock)

# With calculation logic
registry.mock("calculate_total").returns_fn(
    lambda items, tax_rate: {"total": sum(i["price"] for i in items) * (1 + tax_rate)}
)
```

### Chaining Methods

```python
# Chain multiple configuration methods
(registry.mock("get_bills")
    .when(status="overdue")
    .echoes_input("customer_id")
    .returns({"priority": "high", "action": "notify"}))
```

### Scenario Predicates and Input Conditions

```python
registry.mock("create_invoice").when(
    lambda md: md.get("tenant") == "sandbox",
    amount={"$gt": 1000},
).returns({"status": "queued"})
```

The scenario predicate controls whether the mock is resolved at all. Input conditions are then checked against the actual tool-call kwargs when the mock executes.

---

## Notes and Limits

- `.returns()` and `.returns_fn()` are terminal methods. They register the mock immediately.
- `MockBuilder` registers one mock per tool name. Calling `registry.mock("tool")` again overwrites the previous registration.
- Placeholder resolution such as `{{now}}` and `{{input.customer_id}}` belongs to the data-driven mock flow, not `MockBuilder`.

---

## Integration Examples

### With LangGraph Per-Invocation Mocking

```python
from stuntdouble import MockToolsRegistry, create_mockable_tool_wrapper
from langgraph.prebuilt import ToolNode

registry = MockToolsRegistry()

# Register mocks using builder
registry.mock("get_customer").returns({"id": "123", "name": "Test Corp"})
registry.mock("list_bills").when(status="active").returns({"bills": [{"id": "B001"}]})

# Create wrapper and use with ToolNode
wrapper = create_mockable_tool_wrapper(registry)
tool_node = ToolNode(tools, awrap_tool_call=wrapper)
```

### With Default Registry (Simplest)

```python
from stuntdouble import default_registry, mockable_tool_wrapper
from langgraph.prebuilt import ToolNode

# Register mocks on default_registry
default_registry.mock("get_customer").returns({"id": "123", "name": "Test Corp"})
default_registry.mock("list_bills").when(status="active").returns({"bills": [{"id": "B001"}]})

# Use pre-configured wrapper
tool_node = ToolNode(tools, awrap_tool_call=mockable_tool_wrapper)
```

---

## Input Condition Behavior

When using `.when(**conditions)`, the mock raises `InputNotMatchedError` if the tool call arguments don't match. This prevents non-matching calls from silently returning `None` as a successful tool result.

```python
from stuntdouble import MockToolsRegistry
from stuntdouble.exceptions import InputNotMatchedError

registry = MockToolsRegistry()
registry.mock("get_bills").when(status="active").returns({"bills": []})

fn = registry.resolve("get_bills", {})

fn(status="active")     # -> {"bills": []}
fn(status="inactive")   # -> raises InputNotMatchedError
```

The wrapper catches `InputNotMatchedError` and routes it through the standard no-mock handling:
- **Strict mode** (`require_mock_when_scenario=True`): raises `MissingMockError` with a descriptive message about which conditions failed
- **Lenient mode** (`require_mock_when_scenario=False`): falls back to the real tool

### Builder vs. Data-Driven

The builder registers **one mock per tool**. Calling `registry.mock("tool")` twice overwrites the first registration. For multi-case matching (multiple input/output pairs for the same tool), use `register_data_driven` with scenario_metadata instead:

```python
# Builder: one mock, one response per tool (simple cases)
registry.mock("get_weather").returns({"temp": 72})

# Data-driven: multiple cases per tool (complex scenarios)
registry.register_data_driven("query_bills")
# Cases come from scenario_metadata at runtime:
# {"mocks": {"query_bills": [
#     {"input": {"status": "overdue"}, "output": {"bills": [...]}},
#     {"input": {"status": "paid"}, "output": {"bills": [...]}},
#     {"output": {"bills": []}}
# ]}}
```

---

## See Also

- [Quickstart Guide](quickstart.md) - Getting started with StuntDouble
- [LangGraph Approach](langgraph-integration.md) - LangGraph-specific mocking patterns
- [Matchers and Resolvers](matchers-and-resolvers.md) - Input matching operators and placeholders
- [Call Recording](call-recording.md) - Verify tool calls in tests
