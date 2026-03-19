# Architecture Overview

This document describes StuntDouble's internal architecture, components, and how they interact.

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           StuntDouble Architecture                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         Integration Layer                            │   │
│  │  ┌──────────────┐  ┌──────────────────────┐                         │   │
│  │  │   LangGraph  │  │    MCP Mirror        │                         │   │
│  │  │   Module     │  │    Module            │                         │   │
│  │  └──────┬───────┘  └──────────┬───────────┘                         │   │
│  └─────────┼─────────────────────┼─────────────────────────────────────┘   │
│            │                     │                                          │
│            ▼                     ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                           Core Layer                                 │   │
│  │  ┌──────────────┐  ┌──────────────────┐  ┌──────────────────────┐   │   │
│  │  │   Registry   │  │   InputMatcher   │  │   ValueResolver      │   │   │
│  │  │              │  │                  │  │                      │   │   │
│  │  │  Mock        │  │  Pattern-based   │  │  Placeholder         │   │   │
│  │  │  storage &   │  │  input matching  │  │  resolution          │   │   │
│  │  │  retrieval   │  │  ($gt, $in, etc) │  │  ({{now}}, {{uuid}}) │   │   │
│  │  └──────────────┘  └──────────────────┘  └──────────────────────┘   │   │
│  │                                                                       │   │
│  │  ┌──────────────┐  ┌──────────────────┐                              │   │
│  │  │  MockBuilder │  │   CallRecorder   │                              │   │
│  │  │              │  │                  │                              │   │
│  │  │  Fluent API  │  │  Tool call       │                              │   │
│  │  │  for mocks   │  │  recording &     │                              │   │
│  │  │              │  │  assertions      │                              │   │
│  │  └──────────────┘  └──────────────────┘                              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Module Structure

```
stuntdouble/
├── __init__.py          # Top-level public API
├── builder.py           # MockBuilder fluent API
├── exceptions.py        # MockingError, MissingMockError, SignatureMismatchError, MockAssertionError
├── matching.py          # InputMatcher, matches()
├── mcp/                 # MCP client implementation
│   ├── __init__.py        # Re-exports: MCPClient, MCPServerConfig, MCPTool
│   ├── client.py          # MCP transport and tool execution client
│   └── utils.py           # MCP config parsing helpers
├── mock_registry.py     # MockToolsRegistry
├── resolving.py         # ValueResolver, ResolverContext, resolve_output(), has_placeholders()
├── scenario_mocking.py  # DataDrivenMockFactory, register_data_driven()
├── types.py             # MockFn, ScenarioMetadata, WhenPredicate, MockRegistration
├── langgraph/           # ⭐ LangGraph per-invocation mocking (RECOMMENDED)
│   ├── __init__.py        # LangGraph integration re-exports
│   ├── config.py          # inject_scenario_metadata, get_scenario_metadata, get_configurable_context, extract_scenario_metadata_from_config
│   ├── recorder.py        # CallRecorder, CallRecord
│   ├── validation.py      # validate_mock_signature, validate_mock_parameters, validate_registry_mocks
│   └── wrapper.py         # create_mockable_tool_wrapper, default_registry, mockable_tool_wrapper
└── mirroring/           # MCP tool mirroring
    ├── __init__.py        # Re-exports: ToolMirror, mirror, mirror_for_agent, QualityPreset, etc.
    ├── cache.py           # ResponseCache
    ├── discovery.py       # MCPToolDiscoverer
    ├── integrations/      # External adapters
    │   ├── langchain.py     # LangChainAdapter
    │   └── llm.py           # LLM integration
    ├── mirror.py          # ToolMirror class, mirror(), mirror_for_agent()
    ├── mirror_registry.py # MirroredToolRegistry
    ├── models.py          # MockStrategy, ToolDefinition, etc.
    ├── strategies.py      # BaseStrategy, StaticStrategy, DynamicStrategy
    └── generation/       # Mock generation
        ├── base.py        # MockGenerator
        ├── entity.py
        ├── presets.py    # QualityPreset
        └── responses.py
```

---

## Core Components

### 1. InputMatcher

Handles operator-based pattern matching for conditional mocking.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          InputMatcher Flow                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Pattern                     Actual Input                    Result        │
│   ───────                     ────────────                    ──────        │
│                                                                             │
│   {"status": "active"}   ───▶ {"status": "active"}      ───▶  ✓ Match      │
│                                                                             │
│   {"amount": {"$gt": 100}}──▶ {"amount": 150}           ───▶  ✓ Match      │
│                                                                             │
│   {"id": {"$regex": "^C"}}──▶ {"id": "CUST-123"}        ───▶  ✓ Match      │
│                                                                             │
│   {"tags": {"$in": [...]}}──▶ {"tags": "billing"}       ───▶  ✓ Match      │
│                                                                             │
│   null (catch-all)       ───▶ (any input)               ───▶  ✓ Match      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Supported Operators:**

| Operator | Description | Example |
|----------|-------------|---------|
| `$eq` | Exact equality | `{"status": {"$eq": "active"}}` |
| `$ne` | Not equal | `{"status": {"$ne": "deleted"}}` |
| `$gt`, `$gte` | Greater than | `{"amount": {"$gt": 1000}}` |
| `$lt`, `$lte` | Less than | `{"count": {"$lte": 10}}` |
| `$in` | Value in list | `{"status": {"$in": ["a", "b"]}}` |
| `$nin` | Not in list | `{"status": {"$nin": ["deleted"]}}` |
| `$contains` | String contains | `{"name": {"$contains": "Corp"}}` |
| `$regex` | Regex match | `{"id": {"$regex": "^CUST-\\d+"}}` |
| `$exists` | Key exists | `{"optional": {"$exists": true}}` |

### 2. ValueResolver

Resolves dynamic placeholders in mock outputs.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ValueResolver Flow                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Template Output                    Context           Resolved Output      │
│   ───────────────                    ───────           ───────────────      │
│                                                                             │
│   {                                  input: {          {                    │
│     "id": "{{uuid}}",                  customer_id:      "id": "a1b2...",   │
│     "created": "{{now}}",              "CUST-123"        "created": "2026.. │
│     "due": "{{now + 30d}}",          }                   "due": "2026-03..  │
│     "customer": "{{input.customer_id}}"                  "customer": "CUST- │
│   }                                                    }                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Supported Placeholders:**

| Category | Placeholder | Output |
|----------|-------------|--------|
| **Timestamps** | `{{now}}` | `2026-02-12T10:30:00` |
| | `{{today}}` | `2026-02-12` |
| | `{{now + 7d}}` | 7 days from now |
| | `{{now - 30d}}` | 30 days ago |
| | `{{start_of_month}}` | First day of month |
| **Input Refs** | `{{input.field}}` | Value from input |
| | `{{input.field \| default(x)}}` | With default |
| **Generators** | `{{uuid}}` | Random UUID |
| | `{{random_int(1, 100)}}` | Random integer |
| | `{{sequence('INV')}}` | `INV-001`, `INV-002`... |
| | `{{choice('a', 'b')}}` | Random choice |

### 3. MockBuilder

Fluent API for mock registration that works with any registry.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        MockBuilder Chain                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   mock("get_customer", registry)                                           │
│       │                                                                     │
│       ▼                                                                     │
│   .when(status="active", amount={"$gt": 100})   ← Input conditions        │
│       │                                                                     │
│       ▼                                                                     │
│   .echoes_input("customer_id")                   ← Echo input fields       │
│       │                                                                     │
│       ▼                                                                     │
│   .returns({"tier": "gold"})                     ← Static return value     │
│       │                                                                     │
│       ▼                                                                     │
│   → Registered on registry                                                 │
│                                                                             │
│   Alternative terminal methods:                                             │
│   .returns_fn(lambda **kw: {...})                ← Custom callable         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4. CallRecorder

Records tool calls for test assertions and verification.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       CallRecorder Architecture                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   mockable_tool_wrapper                                                     │
│        │                                                                    │
│        ├── Before execution: Record call start                             │
│        │   CallRecord(tool_name, args, timestamp)                          │
│        │                                                                    │
│        ├── Execute tool (mock or real)                                      │
│        │                                                                    │
│        └── After execution: Update record                                  │
│            CallRecord.result, .was_mocked, .duration_ms                    │
│                                                                             │
│   Thread-safe: Internal locking for concurrent access                      │
│                                                                             │
│   Assertions:                                                               │
│   ├── assert_called(tool)                                                  │
│   ├── assert_called_with(tool, **args)                                     │
│   ├── assert_call_order(tool_a, tool_b, ...)                               │
│   └── assert_called_times(tool, n)                                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5. MockToolsRegistry (LangGraph)

Factory-based mock storage for per-invocation mocking.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MockToolsRegistry Architecture                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Registration (startup)               Resolution (per-request)            │
│   ──────────────────────               ────────────────────────            │
│                                                                             │
│   registry.register(                   mock_fn = registry.resolve(         │
│     "tool_name",                         "tool_name",                       │
│     factory=...,          ────▶          scenario_metadata                  │
│     when=...                           )                                    │
│   )                                                                         │
│                                             │                               │
│   ┌──────────────────┐                      ▼                               │
│   │ _registrations   │              ┌───────────────┐                       │
│   │ ├─ tool_name     │              │ when(md)?     │                       │
│   │ │  ├─ factory    │              │   │           │                       │
│   │ │  └─ when       │              │   ├─ YES ──▶ factory(md) ──▶ mock_fn │
│   │ └─ ...           │              │   └─ NO  ──▶ None (use real tool)   │
│   └──────────────────┘              └───────────────┘                       │
│                                                                             │
│   Key Properties:                                                           │
│   • Thread-safe (read-mostly, writes locked)                               │
│   • No mutation after graph compilation                                    │
│   • Each invocation gets isolated mock callable                            │
│   • Supports signature validation via tool= parameter                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## LangGraph Integration Flow

StuntDouble uses the wrapper approach with native `ToolNode` and `awrap_tool_call`:

### Wrapper Pattern ⭐ (Recommended)

Uses native `ToolNode` with `awrap_tool_call` wrapper.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      LangGraph Wrapper Flow                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   1. SETUP (once at startup)                                               │
│   ──────────────────────────                                               │
│                                                                             │
│   from stuntdouble import (                                      │
│       mockable_tool_wrapper, default_registry                              │
│   )                                                                         │
│                                                                             │
│   default_registry.register("tool_a", mock_fn=..., when=...)               │
│   default_registry.register("tool_b", mock_fn=...)                         │
│                                                                             │
│   graph = StateGraph(...)                                                   │
│   graph.add_node("tools", ToolNode(                                        │
│       tools,                                                                │
│       awrap_tool_call=mockable_tool_wrapper  ◀─── Native ToolNode!         │
│   ))                                                                        │
│   graph.compile()                                                           │
│                                                                             │
│   2. INVOCATION (per-request)                                              │
│   ───────────────────────────                                              │
│                                                                             │
│   config = inject_scenario_metadata({}, {"mocks": {...}})                  │
│   result = graph.ainvoke(state, config=config)                             │
│                                                                             │
│   3. EXECUTION (inside awrap_tool_call)                                    │
│   ─────────────────────────────────────                                    │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │ mockable_tool_wrapper intercepts tool call                           │  │
│   │     │                                                                │  │
│   │     ▼                                                                │  │
│   │ Extract scenario_metadata from config                                │  │
│   │     │                                                                │  │
│   │     ▼                                                                │  │
│   │ Resolve mock from registry for tool                                  │  │
│   │     │                                                                │  │
│   │     ├─── mock exists ──▶ Record call → Return mock output           │  │
│   │     └─── no mock ──────▶ Record call → Call original tool           │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## MCP Mirroring Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        ToolMirror Architecture                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   1. DISCOVERY                                                              │
│   ────────────                                                              │
│                                                                             │
│   mirror.mirror(["python", "-m", "my_mcp_server"])                         │
│       │                                                                     │
│       ▼                                                                     │
│   ┌──────────────────────────────────────────────────────────────────┐     │
│   │ MCPToolDiscoverer                                                 │     │
│   │                                                                   │     │
│   │  1. Start MCP server subprocess (stdio) or connect (HTTP)        │     │
│   │  2. Send tools/list request                                      │     │
│   │  3. Parse tool definitions (name, description, schema)           │     │
│   │  4. Analyze input schemas for types and constraints              │     │
│   │                                                                   │     │
│   │  HTTP supports custom headers for authentication:                │     │
│   │  mirror.mirror(http_url="...", headers={"Authorization": "..."}) │     │
│   └──────────────────────────────────────────────────────────────────┘     │
│       │                                                                     │
│       ▼                                                                     │
│   ┌──────────────────────────────────────────────────────────────────┐     │
│   │ Tool Definitions                                                  │     │
│   │  ├─ create_invoice: {amount: number, customer_id: string, ...}   │     │
│   │  ├─ get_customer: {customer_id: string}                          │     │
│   │  └─ list_bills: {status?: string, limit?: number}                │     │
│   └──────────────────────────────────────────────────────────────────┘     │
│                                                                             │
│   2. GENERATION                                                             │
│   ─────────────                                                             │
│                                                                             │
│   ┌──────────────────────────────────────────────────────────────────┐     │
│   │ MockGenerator                                                     │     │
│   │                                                                   │     │
│   │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐   │     │
│   │  │ StaticGen   │  │ SchemaGen   │  │ LLMGen (optional)       │   │     │
│   │  │             │  │             │  │                         │   │     │
│   │  │ Preset      │  │ Type-aware  │  │ Contextual, realistic   │   │     │
│   │  │ responses   │  │ generation  │  │ data from LLM           │   │     │
│   │  └─────────────┘  └─────────────┘  └─────────────────────────┘   │     │
│   └──────────────────────────────────────────────────────────────────┘     │
│       │                                                                     │
│       ▼                                                                     │
│   ┌──────────────────────────────────────────────────────────────────┐     │
│   │ MirroredToolRegistry                                              │     │
│   │  • Registers mock functions and metadata                          │     │
│   │  • Stores metadata (server name, schema version, etc.)           │     │
│   └──────────────────────────────────────────────────────────────────┘     │
│                                                                             │
│   3. USAGE                                                                  │
│   ───────                                                                   │
│                                                                             │
│   tools = mirror.to_langchain_tools()                                      │
│       │                                                                     │
│       ▼                                                                     │
│   LangChain StructuredTool instances ready for agent.bind_tools()          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Thread Safety

| Component | Thread Safety | Notes |
|-----------|--------------|-------|
| `mockable_tool_wrapper` | ✅ Safe | Uses per-request context from config |
| `default_registry` | ✅ Safe | Singleton, read-mostly with lock |
| `MockToolsRegistry` | ✅ Safe | Read-mostly; writes use lock |
| `CallRecorder` | ✅ Safe | Internal locking for concurrent access |
| `MockBuilder` | ✅ Safe | Immutable builder chain |
| `InputMatcher` | ✅ Safe | Stateless |
| `ValueResolver` | ⚠️ Context-bound | `ResolverContext` is per-request |
| `ToolMirror` | ✅ Safe | Per-instance state |

---

## Extension Points

1. **Custom Mock Functions** — Implement any `Callable[[dict], Callable]` for custom mock logic
2. **Context-Aware Factories** — Add `config` parameter for runtime context access
3. **Custom Operators** — Extend `InputMatcher` (in `stuntdouble.matching`) for new matching patterns
4. **Custom Placeholders** — Extend `ValueResolver` for new dynamic values
5. **Custom Generation** — Implement `MockGenerator` subclass for custom data generation
6. **Custom Registries** — Provide a registry-like object with a compatible `register()` API if you need custom mock storage
