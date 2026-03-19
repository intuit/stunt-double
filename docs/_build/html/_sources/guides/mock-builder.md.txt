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

## Advanced Mock Function Patterns

Beyond the basics, `MockBuilder` supports patterns for complex business logic, error simulation, and context-aware mocking.

### Complex Logic with `returns_fn()`

When your mock needs branching logic, pass a callable to `returns_fn()`. Here a billing calculator computes totals from structured input:

```python
registry.mock("calculate_total").returns_fn(
    lambda items, tax_rate=0.0: {
        "subtotal": sum(item["price"] * item["qty"] for item in items),
        "tax": sum(item["price"] * item["qty"] for item in items) * tax_rate,
        "total": sum(item["price"] * item["qty"] for item in items) * (1 + tax_rate),
        "item_count": len(items),
    }
)
```

The callable receives the same keyword arguments the real tool would. Use this whenever a static `.returns()` value isn't expressive enough.

### Error Simulation

Mock tools that return errors to verify your agent handles failures gracefully:

```python
# Simulate a service outage
registry.mock("send_email").returns({"error": "Service unavailable", "status": 503})

# Simulate rate limiting
registry.mock("call_api").returns_fn(
    lambda **kwargs: {"error": "Rate limit exceeded", "retry_after": 30}
)

# Simulate partial failure
registry.mock("batch_update").returns_fn(
    lambda records: {
        "succeeded": [r["id"] for r in records[:3]],
        "failed": [{"id": r["id"], "error": "Conflict"} for r in records[3:]],
    }
)
```

This is especially useful for testing retry logic, fallback paths, and user-facing error messages in your agent.

### Scenario Predicates with `when()`

Pass a lambda predicate to `.when()` to gate mocks on scenario metadata. This enables feature-flag style mocking:

```python
# Mock only when scenario has a specific flag
registry.mock("get_pricing").when(
    lambda metadata: metadata.get("feature_flags", {}).get("new_pricing") is True
).returns({"plan": "v2", "price": 29.99})

# Default pricing when flag is off
registry.mock("get_pricing").returns({"plan": "v1", "price": 19.99})
```

Scenario predicates are checked first. If the predicate doesn't match, the next registered mock for that tool is tried. This lets you layer conditional mocks with a fallback default.

### Combining `when()` + `echoes_input()` + `returns()`

All three methods can be chained together. Input conditions, echoed fields, and static return values are merged into the final response:

```python
registry.mock("create_user").when(
    role={"$in": ["admin", "superadmin"]}
).echoes_input("email", "role").returns({
    "id": "USR-001",
    "status": "active",
    "permissions": ["read", "write", "delete"],
    "created_at": "2025-01-01T00:00:00Z",
})
# Input: {"email": "admin@acme.com", "role": "admin"}
# Output: {"id": "USR-001", "status": "active", "permissions": [...],
#          "created_at": "...", "email": "admin@acme.com", "role": "admin"}
```

The echoed fields (`email`, `role`) are merged into the static return value. If an input doesn't match the `.when()` conditions, `InputNotMatchedError` is raised as usual.

### Mock Factory with `registry.register()` for Full Control

When you need access to `scenario_metadata` at mock-creation time, use the lower-level `register()` method directly:

```python
def tenant_aware_mock(scenario_metadata: dict, config: dict = None):
    """Mock that varies behavior based on scenario metadata."""
    tenant = scenario_metadata.get("tenant", "default")

    if tenant == "enterprise":
        return lambda account_id: {
            "account_id": account_id,
            "features": ["sso", "audit_log", "custom_roles"],
            "max_users": 10000,
        }
    else:
        return lambda account_id: {
            "account_id": account_id,
            "features": ["basic_auth"],
            "max_users": 5,
        }

registry.register("get_account_features", mock_fn=tenant_aware_mock)
```

`register()` gives you a two-phase mock: the outer function receives `scenario_metadata` and returns the actual mock callable. This is the most powerful pattern when you need runtime context to determine mock behavior.

---

## See Also

- [Quickstart Guide](quickstart.md) - Getting started with StuntDouble
- [LangGraph Approach](langgraph-integration.md) - LangGraph-specific mocking patterns
- [Matchers and Resolvers](matchers-and-resolvers.md) - Input matching operators and placeholders
- [Call Recording](call-recording.md) - Verify tool calls in tests
