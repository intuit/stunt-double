<div align="center">
  <img src="https://raw.githubusercontent.com/intuit/stunt-double/main/docs/stuntdouble_logo2.png" alt="StuntDouble Logo" width="400"/>

  # StuntDouble

  **Tool Mocking Framework for AI Agent Testing**

  [![PyPI version](https://img.shields.io/pypi/v/stuntdouble)](https://pypi.org/project/stuntdouble/)
  [![Python versions](https://img.shields.io/pypi/pyversions/stuntdouble?logo=python)](https://pypi.org/project/stuntdouble/)
  [![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/intuit/stunt-double/blob/main/LICENSE)

  *Mock your AI agent tools without hitting real APIs*

</div>

---

## What is StuntDouble?

StuntDouble is a Python framework for **mocking AI agent tool calls**. Just like a stunt double performs risky scenes in place of an actor, StuntDouble lets you test your AI agents without the risk, cost, and unpredictability of production APIs.

### Key Features

| Feature | Description |
|---------|-------------|
| **LangGraph Native** | Per-invocation mocking via `RunnableConfig` -- no global state, fully concurrent |
| **Zero Code Changes** | Agent code remains unchanged, production-ready at all times |
| **Data-Driven Mocks** | Define mock cases in JSON -- no hand-written factories needed |
| **Smart Input Matching** | Use operators like `$gt`, `$in`, `$regex` for conditional mocking |
| **Dynamic Outputs** | Placeholders for timestamps (`{{now}}`), input refs (`{{input.id}}`), UUIDs (`{{uuid}}`) |
| **Call Recording** | Capture and assert on tool calls with `CallRecorder` |
| **Signature Validation** | Catch mock/tool parameter mismatches at registration or runtime |

### Why StuntDouble?

| Problem | StuntDouble Solution |
|---------|---------------------|
| High API costs during development | Zero-cost mocking with realistic responses |
| Slow test execution | 100x faster with in-memory mocks |
| Non-deterministic test results | Reproducible, controlled test environments |
| Requires internet connectivity | Fully offline testing capability |
| Changing agent code for tests | One-line wrapping, no code changes needed |

---

## Installation

```shell
uv add stuntdouble
```

Or with pip:

```shell
pip install stuntdouble
```

---

## Quick Start

StuntDouble uses LangGraph's native `ToolNode` with an `awrap_tool_call` wrapper. Mocks are passed per-invocation via `RunnableConfig` -- no environment variables, no global state.

### How It Works

```
  Your Code                        StuntDouble                    Result
  ---------                        -----------                    ------

  graph.invoke(                    +---------------------+
    state,          ------------->|  awrap_tool_call    |
    config={                       |      Wrapper        |
      "configurable": {            |                     |
        "scenario_metadata": {     | scenario_metadata?  |
          "mocks": {...}           |      |              |
        }                          |      v              |
      }                            |  +-------+          |
    }                              |  | YES   |----------+--> Return MOCK
  )                                |  +-------+          |
                                   |      |              |
                                   |  +-------+          |
                                   |  |  NO   |----------+--> Call REAL tool
                                   |  +-------+          |
                                   +---------------------+
```

### Minimal Example

```python
from langgraph.graph import StateGraph, MessagesState, START
from langgraph.prebuilt import ToolNode, tools_condition
from stuntdouble import (
    MockToolsRegistry,
    create_mockable_tool_wrapper,
    inject_scenario_metadata,
)

# Your real tools
tools = [get_customer_tool, list_bills_tool, create_invoice_tool]

# Step 1: Create registry and register mocks
registry = MockToolsRegistry()
registry.register(
    "get_customer",
    mock_fn=lambda md: lambda customer_id, **kw: {
        "id": customer_id,
        "name": "Test Corp",
        "balance": 1500
    }
)

# Step 2: Build graph with native ToolNode + mockable wrapper
wrapper = create_mockable_tool_wrapper(registry)
builder = StateGraph(MessagesState)
builder.add_node("agent", agent_node)
builder.add_node("tools", ToolNode(tools, awrap_tool_call=wrapper))
builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", tools_condition)
builder.add_edge("tools", "agent")
graph = builder.compile()

# Step 3: Invoke WITH mocks
config = inject_scenario_metadata({}, {
    "mocks": {
        "list_bills": [{"output": {"bills": [{"id": "B001", "amount": 500}]}}]
    }
})
result = await graph.ainvoke({"messages": [HumanMessage("List my bills")]}, config=config)
# --> Uses mocked list_bills

# Step 4: Invoke WITHOUT mocks (no scenario_metadata = real tools)
result = await graph.ainvoke({"messages": [HumanMessage("List my bills")]})
# --> Uses real list_bills tool
```

---

## Data-Driven Mocks

Instead of writing mock factory lambdas, use `register_data_driven` to read mock cases directly from `scenario_metadata`:

```python
from stuntdouble import MockToolsRegistry, inject_scenario_metadata

registry = MockToolsRegistry()

# Register data-driven mocks -- no lambdas needed
registry.register_data_driven("list_customers", echo_input=True)
registry.register_data_driven("query_bills", echo_input=True)
registry.register_data_driven("knowledgebase", fallback="No documents found.")

# Mock data lives in scenario_metadata
scenario = {
    "mocks": {
        "list_customers": [
            {"input": {"status": "active"}, "output": [{"id": "C1"}]},
            {"output": []}
        ],
        "query_bills": [{"output": {"total": 42}}],
        "knowledgebase": [
            {"input": {"query": "refund"}, "output": "Refund policy: ..."}
        ]
    }
}

config = inject_scenario_metadata({}, scenario)
result = await graph.ainvoke(state, config=config)
```

### DataDrivenMockFactory Features

| Feature | Description |
|---------|-------------|
| Input matching | Match by exact value or operators (`$gt`, `$in`, `$regex`, etc.) |
| Catch-all cases | Cases without `input` match any call |
| `fallback` | Value returned when no case matches |
| `echo_input` | Return input kwargs as-is when no match |
| `{{input.*}}` placeholders | Reference tool call arguments in output |
| `{{config.*}}` placeholders | Reference values from `RunnableConfig` |
| `{{now}}`, `{{uuid}}` | Dynamic timestamps and UUIDs |

---

## Fluent Builder API

The `registry.mock()` method provides a concise, chainable API for registering mocks:

```python
from stuntdouble import MockToolsRegistry

registry = MockToolsRegistry()

# Static return value
registry.mock("get_weather").returns({"temp": 72, "conditions": "sunny"})

# Custom function
registry.mock("calculate_total").returns_fn(
    lambda items, tax: {"total": sum(items) * (1 + tax)}
)

# Echo input fields into response
registry.mock("update_customer").echoes_input("customer_id").returns({"updated": True})
# Called with customer_id="C1" → {"updated": True, "customer_id": "C1"}

# Conditional mock (scenario predicate)
registry.mock("send_email").when(
    lambda md: md.get("mode") == "test"
).returns({"sent": True})

# Input matching with operators
registry.mock("get_bills").when(status="active").returns({"bills": []})
registry.mock("query").when(amount={"$gt": 1000}).returns({"tier": "high"})

# Full chain: condition + echo + return
registry.mock("update").when(
    lambda md: "update" in md.get("mocks", {})
).echoes_input("customer_id").returns({"updated": True})
```

### Builder Methods

| Method | Type | Description |
|--------|------|-------------|
| `registry.mock(tool_name)` | Entry | Start building a mock, returns `MockBuilder` |
| `.when(predicate, **conditions)` | Chain | Set scenario predicate and/or input conditions |
| `.echoes_input(*fields)` | Chain | Copy input fields into the response dict |
| `.returns(value)` | Terminal | Register mock returning a static value (deep-copied per call) |
| `.returns_fn(fn)` | Terminal | Register mock that calls `fn` with tool kwargs |

---

## Mock Patterns

### Pattern 1: Static Mock (Builder)

```python
registry.mock("get_weather").returns({"temp": 72, "conditions": "sunny"})
```

### Pattern 2: Static Mock (Low-Level)

```python
registry.register(
    "get_weather",
    mock_fn=lambda md: lambda **kwargs: {"temp": 72, "conditions": "sunny"}
)
```

### Pattern 3: Input-Echo Mock

```python
registry.mock("get_customer").echoes_input("customer_id").returns({
    "name": "Test Corp",
    "status": "active"
})
# Called with customer_id="C1" → {"name": "Test Corp", "status": "active", "customer_id": "C1"}
```

### Pattern 4: Data-Driven Mock

```python
registry.register_data_driven("list_bills")

# Mock data comes from scenario_metadata at runtime:
# {"mocks": {"list_bills": [{"output": {"bills": [...]}}]}}
```

### Pattern 5: Conditional Mock (with `when` predicate)

```python
registry.mock("send_email").when(
    lambda md: md.get("mode") == "test"
).returns({"sent": True, "message_id": "mock-123"})
```

### Pattern 6: Context-Aware Mock (Runtime Config Access)

Access runtime context (like user identity from HTTP headers) in your mock factory:

```python
def user_context_mock(scenario_metadata: dict, config: dict = None):
    """Mock factory that extracts user context from RunnableConfig."""
    configurable = (config or {}).get("configurable", {})
    agent_context = configurable.get("agent_context", {})
    user_id = agent_context.get("user_id", "unknown")
    org_id = agent_context.get("org_id", "unknown")

    return lambda: {"user_id": user_id, "org_id": org_id}

registry.register("get_current_user", mock_fn=user_context_mock)
```

Mock factories can accept an **optional second parameter** `config` (the `RunnableConfig`). The signature is detected automatically -- existing factories with only `scenario_metadata` continue to work.

---

## Mock Data Format

StuntDouble uses a JSON format for mock definitions with **operator-based matching** and **dynamic placeholders**.

### Basic Structure

```json
{
  "tool_name": [
    {"input": {"key": "value"}, "output": {"result": "data"}},
    {"output": {"default": "response"}}
  ]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `input` | object | No | Pattern to match. `null` = match any input (catch-all) |
| `output` | any | **Yes** | Value to return when matched (supports placeholders) |

### Input Matching Operators

Use MongoDB-style operators for flexible matching:

| Operator | Description | Example |
|----------|-------------|---------|
| `$eq` | Exact equality (default) | `{"status": {"$eq": "active"}}` |
| `$ne` | Not equal | `{"status": {"$ne": "deleted"}}` |
| `$gt`, `$gte` | Greater than (or equal) | `{"amount": {"$gt": 1000}}` |
| `$lt`, `$lte` | Less than (or equal) | `{"count": {"$lt": 100}}` |
| `$in` | Value in list | `{"status": {"$in": ["active", "pending"]}}` |
| `$nin` | Value not in list | `{"status": {"$nin": ["deleted"]}}` |
| `$contains` | String contains | `{"name": {"$contains": "Corp"}}` |
| `$regex` | Regex pattern | `{"id": {"$regex": "^CUST-\\d+"}}` |
| `$exists` | Key exists | `{"optional_field": {"$exists": true}}` |

**Example with operators:**

```json
{
  "get_bills": [
    {"input": {"status": "overdue", "amount": {"$gt": 5000}}, "output": {"priority": "URGENT"}},
    {"input": {"status": {"$in": ["paid", "pending"]}}, "output": {"priority": "low"}},
    {"output": {"priority": "unknown"}}
  ]
}
```

### Dynamic Placeholders

Use `{{placeholder}}` syntax for dynamic values in outputs:

| Placeholder | Description | Example Output |
|------------|-------------|----------------|
| `{{now}}` | Current ISO timestamp | `2025-01-04T10:30:00` |
| `{{now + Nd}}` | N days from now | `{{now + 7d}}` |
| `{{now - Nd}}` | N days ago | `{{now - 30d}}` |
| `{{today}}` | Current date only | `2025-01-04` |
| `{{input.field}}` | Reference input value | Echoes input |
| `{{config.field}}` | Reference RunnableConfig value | From configurable |
| `{{uuid}}` | Random UUID | `a1b2c3d4-e5f6-...` |
| `{{random_int(min, max)}}` | Random integer | `42` |
| `{{sequence('prefix')}}` | Incrementing ID | `prefix-001`, `prefix-002` |

**Example with placeholders:**

```json
{
  "create_invoice": [{
    "output": {
      "id": "{{uuid}}",
      "created_at": "{{now}}",
      "due_date": "{{now + 30d}}",
      "customer_id": "{{input.customer_id}}",
      "realm_id": "{{config.realm_id}}"
    }
  }]
}
```

---

## Call Recording

The `CallRecorder` captures all tool calls during test execution, enabling verification of what tools were called, with what arguments, and in what order.

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
registry.register_data_driven("get_customer")
registry.register_data_driven("list_bills")

# Create wrapper with recorder
wrapper = create_mockable_tool_wrapper(registry, recorder=recorder)
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

### Query Methods

| Method | Description |
|--------|-------------|
| `was_called(tool, **args)` | Check if tool was called (optionally with specific args) |
| `call_count(tool)` | Get number of calls to a tool |
| `get_calls(tool)` | Get list of `CallRecord` objects |
| `get_last_call(tool)` | Get the most recent call |
| `get_first_call(tool)` | Get the first call |
| `get_args(tool, index=-1)` | Get arguments from a specific call |
| `get_result(tool, index=-1)` | Get result from a specific call |
| `summary()` | Human-readable summary of all calls |
| `clear()` | Reset recorder for next test |

### Assertion Methods

| Method | Description |
|--------|-------------|
| `assert_called(tool)` | Assert tool was called at least once |
| `assert_not_called(tool)` | Assert tool was never called |
| `assert_called_once(tool)` | Assert tool was called exactly once |
| `assert_called_times(tool, n)` | Assert tool was called exactly n times |
| `assert_called_with(tool, **args)` | Assert any call matches the arguments |
| `assert_last_called_with(tool, **args)` | Assert last call matches the arguments |
| `assert_call_order(*tools)` | Assert tools were called in order |

### CallRecord Properties

| Property | Description |
|----------|-------------|
| `tool_name` | Name of the tool |
| `args` | Arguments passed to the tool |
| `result` | Return value (mock or real) |
| `error` | Exception if call failed |
| `was_mocked` | Whether a mock was used |
| `duration_ms` | Call duration in milliseconds |
| `scenario_id` | Scenario ID from metadata |

---

## Mock Signature Validation

StuntDouble can validate that your mock functions have the same parameter signature as the real tools they're mocking.

### Registration-Time Validation

```python
from stuntdouble import MockToolsRegistry

registry = MockToolsRegistry()

# Pass tool= to validate at registration time
try:
    registry.register(
        "get_weather",
        mock_fn=bad_weather_mock,
        tool=get_weather_tool,  # Validates signature immediately
    )
except SignatureMismatchError as e:
    print(f"Registration failed: {e}")
```

### Runtime Validation

```python
# Create wrapper with runtime validation enabled
wrapper = create_mockable_tool_wrapper(
    registry,
    tools=all_tools,           # List of tools for validation lookup
    validate_signatures=True,  # Enable runtime validation (default)
)
```

### Controlling Validation

| What you want | Registration | Wrapper |
|---------------|--------------|---------|
| **No validation** | Omit `tool=` | Set `validate_signatures=False` or omit `tools=` |
| **Registration only** | Pass `tool=real_tool` | Set `validate_signatures=False` or omit `tools=` |
| **Runtime only** | Omit `tool=` | Pass `tools=all_tools` + `validate_signatures=True` |
| **Both** | Pass `tool=real_tool` | Pass `tools=all_tools` + `validate_signatures=True` |

---

## MCP Tool Mirroring

> **Note:** MCP server auto-discovery requires the `stuntdouble.mcp` client module,
> which is not yet published. The mirroring infrastructure (registry, strategies,
> LangChain adapter) is available, but live MCP server connections will raise
> `ImportError` until the MCP client package is shipped.

Auto-discover and mock tools from MCP servers:

```python
from stuntdouble.mirroring import ToolMirror

mirror = ToolMirror()
mirror.mirror(["python", "-m", "myserver"])
tools = mirror.to_langchain_tools()
```

### With LangGraph Integration

```python
from stuntdouble.mirroring import ToolMirror
from stuntdouble import create_mockable_tool_wrapper
from langgraph.prebuilt import ToolNode

mirror = ToolMirror.for_langgraph()
mirror.mirror(["python", "-m", "my_mcp_server"])

tools = mirror.to_langchain_tools()
wrapper = create_mockable_tool_wrapper(mirror.langgraph_registry)
node = ToolNode(tools, awrap_tool_call=wrapper)
```

### HTTP Servers with Authentication

```python
mirror = ToolMirror()
result = mirror.mirror(
    http_url="https://api.example.com/mcp",
    headers={"Authorization": "Bearer your-token-here"}
)
```

---

## API Reference

### Top-Level Imports

```python
from stuntdouble import (
    MockToolsRegistry,              # Mock registry
    MockBuilder,                    # Fluent builder (returned by registry.mock())
    DataDrivenMockFactory,          # Data-driven mock factory
    register_data_driven,           # Convenience registration
    create_mockable_tool_wrapper,   # awrap_tool_call wrapper factory
    inject_scenario_metadata,       # Config helper
    get_scenario_metadata,          # Extract from ToolCallRequest
    CallRecorder,                   # Call recording for verification
    InputMatcher,                   # Operator-based input matching
    ValueResolver,                  # Dynamic placeholder resolution
    resolve_output,                 # Resolve placeholders in output
    MissingMockError,               # No mock found in strict mode
    SignatureMismatchError,         # Mock signature doesn't match tool
    ScenarioMetadata,               # TypedDict for scenario data
    MockFn,                         # Type alias for mock factories
)
```

### Key Functions

| Function | Description |
|----------|-------------|
| `MockToolsRegistry()` | Create a registry for mock functions |
| `registry.mock(tool_name)` | Start fluent builder chain, returns `MockBuilder` |
| `registry.register(tool_name, mock_fn, when=None, tool=None)` | Register a mock factory (low-level). Pass `tool=` for signature validation |
| `registry.register_data_driven(tool_name, fallback=None, echo_input=False)` | Register a data-driven mock |
| `registry.resolve(tool_name, scenario_metadata, config=None)` | Resolve the mock callable at runtime |
| `create_mockable_tool_wrapper(registry, recorder=, tools=, validate_signatures=)` | Create awrap_tool_call wrapper |
| `inject_scenario_metadata(config, metadata)` | Create config with scenario_metadata |
| `CallRecorder()` | Records tool calls for test assertions |

### MCP Tool Mirroring

```python
from stuntdouble.mirroring import ToolMirror
```

| Function | Description |
|----------|-------------|
| `ToolMirror()` | Create mirror instance |
| `ToolMirror.for_langgraph(registry=None)` | Create mirror with LangGraph integration |
| `ToolMirror.with_llm(llm_client, quality="balanced")` | Create mirror with LLM-powered generation |
| `mirror.mirror(server_command=, http_url=, headers=)` | Mirror tools from MCP server |
| `mirror.to_langchain_tools()` | Get LangChain-compatible tools |

---

## Project Structure

```
src/stuntdouble/
├── __init__.py              # Public API exports
├── mock_registry.py         # MockToolsRegistry (runtime mock dispatch)
├── builder.py               # MockBuilder (fluent API for mock registration)
├── data_driven.py           # DataDrivenMockFactory
├── matching.py              # InputMatcher (operator-based matching)
├── resolving.py             # ValueResolver, resolve_output (placeholders)
├── types.py                 # ScenarioMetadata, MockFn, WhenPredicate, etc.
├── exceptions.py            # MissingMockError, SignatureMismatchError, etc.
├── wrapper.py               # create_mockable_tool_wrapper
├── config.py                # inject/get_scenario_metadata
├── recorder.py              # CallRecorder, CallRecord
├── validation.py            # validate_mock_signature, etc.
└── mirroring/               # MCP tool mirroring
    ├── mirror.py                # ToolMirror
    ├── mirror_registry.py       # MirroredToolRegistry (lifecycle manager)
    ├── discovery.py             # MCPToolDiscoverer
    ├── models.py                # ToolDefinition, MirrorMetadata, etc.
    ├── strategies.py            # Static/Dynamic mock strategies
    ├── cache.py                 # ResponseCache
    ├── generation/              # Mock generation (static, dynamic, LLM)
    └── integrations/            # Framework adapters (LangChain, LLM)
```

---

## Troubleshooting

### Mocks Not Working

1. **Check you're using the wrapper:**
   ```python
   from stuntdouble import create_mockable_tool_wrapper
   wrapper = create_mockable_tool_wrapper(registry)
   ToolNode(tools, awrap_tool_call=wrapper)
   ```

2. **Check scenario_metadata is passed:**
   ```python
   from stuntdouble import inject_scenario_metadata
   config = inject_scenario_metadata({}, {"mocks": {...}})
   result = await graph.ainvoke(state, config=config)
   ```

3. **Check mock is registered:**
   ```python
   print(registry.list_registered())  # Should include your tool name
   ```

4. **Check `when` predicate returns True:**
   ```python
   registry.register("tool", mock_fn=..., when=lambda md: md.get("mode") == "test")
   ```

### Import Errors

```bash
pip install --upgrade stuntdouble
```

---

## Documentation

Full documentation with guides, architecture overview, and API reference is available in the [`docs/`](docs/) directory.

---

## Contributing

See [CONTRIBUTING.md](https://github.com/intuit/stunt-double/blob/main/CONTRIBUTING.md) for development setup, testing, and release guidelines.

---

## License

See [![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/intuit/stunt-double/blob/main/LICENSE) file.
