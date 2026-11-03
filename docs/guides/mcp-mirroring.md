# MCP Tool Mirroring Guide

Auto-generate mock implementations from MCP server tool schemas. ToolMirror discovers tools from an MCP server and creates mock implementations without manual coding.

---

## Installation

Install the optional MCP support before using live mirroring:

```bash
pip install "stuntdouble[mcp]"
```

---

## Overview

MCP (Model Context Protocol) Tool Mirroring allows you to:

1. **Discover** tools from any MCP server (stdio or HTTP)
2. **Generate** mock implementations automatically from schemas
3. **Use** the mocked tools in your AI agent tests

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         MCP Mirroring Flow                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   1. Discovery                  2. Generation               3. Usage       │
│   ────────────                  ─────────────               ──────         │
│                                                                             │
│   ┌─────────────┐          ┌─────────────────┐        ┌──────────────┐     │
│   │ MCP Server  │          │ MockGenerator   │        │ AI Agent     │     │
│   │             │          │                 │        │              │     │
│   │ tools/list  │──────▶   │ Schema analysis │──────▶ │ bind_tools() │     │
│   │             │          │ Type inference  │        │              │     │
│   │ - tool_a    │          │ Mock creation   │        │ or           │     │
│   │ - tool_b    │          │                 │        │ ToolNode()   │     │
│   │ - tool_c    │          │ Optional: LLM   │        │              │     │
│   └─────────────┘          └─────────────────┘        └──────────────┘     │
│                                                                             │
│   Supported transports: stdio (subprocess), HTTP (remote server)           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### When to Use Mirroring

| Scenario | Recommendation |
|----------|----------------|
| Testing agent with MCP tools | ✅ Mirror tools for fast, offline testing |
| CI/CD pipelines | ✅ Use `ToolMirror.for_ci()` for deterministic mocks |
| Development without MCP server | ✅ Mirror once, develop offline |
| Need realistic mock data | ✅ Use `ToolMirror.with_llm()` |
| Production | ❌ Use real MCP tools |

---

## Quick Start

### Streamable HTTP endpoints

Use `streamable-http` explicitly for modern MCP endpoints. Existing URL-only calls
continue to select legacy HTTP+SSE; stdio commands are unchanged.

```python
import os
from stuntdouble.mirroring import ToolMirror

mirror = ToolMirror.for_langgraph(quality="fast")
mirror.mirror(
    http_url=os.environ["MCP_ENDPOINT_URL"],  # Exact endpoint supplied by the gateway
    transport="streamable-http",
    server_name="evaluation-tools",
    headers={"Authorization": f"Bearer {os.environ['MCP_TOKEN']}"},
    read_timeout=30,
)
tools = mirror.to_langchain_tools()
```

No `/sse`, `/messages`, or `/mcp` suffix is appended to this endpoint. Install
`stuntdouble[mcp]` for the official MCP SDK, which handles negotiation, initialized
notifications, JSON/SSE responses and session headers. Discovery follows all
`tools/list` pages. Duplicate or already registered names are rejected on this new
transport path; explicitly unregister a tool before replacing it.

The synchronous API owns its SDK session on a managed worker loop, including
initialization and cleanup. It can be called from a thread with a running event loop,
but still blocks that caller. To keep an async application responsive, use:

```python
import asyncio

await asyncio.to_thread(
    mirror.mirror,
    http_url=os.environ["MCP_ENDPOINT_URL"],
    transport="streamable-http",
    headers={"Authorization": f"Bearer {os.environ['MCP_TOKEN']}"},
)
```

Use a fresh mirror for this alternative example. Timeouts apply per request;
failed calls are not automatically retried. OAuth login and token refresh are the
caller's responsibility. HTTP errors report status codes without including server
bodies or credentials. Session termination is best effort; cleanup failures are
logged without replacing the request outcome.

### Import a registry catalog with backends offline

[MCP Gateway Registry](https://github.com/agentic-community/mcp-gateway-registry)
exposes stored, caller-filtered definitions at `GET /api/tool-catalog`. This is a
REST discovery path and **does not require Streamable HTTP or live backend servers**.
The registry itself must be available.

This integration requires no gateway code changes when that endpoint returns the
stored input schemas. Gateway versions that return `input_schema: {}` for a stored
tool lose the schema before SD receives it. SD rejects such entries before
registering any mocks. Use direct Streamable HTTP discovery while the backend is
available, or use a registry release that preserves stored schemas. A tool with no
arguments should still provide an explicit object schema such as
`{"type": "object", "properties": {}}`.

```python
mirror = ToolMirror.for_langgraph(quality="fast")
result = mirror.mirror(
    registry_url=os.environ["MCP_REGISTRY_URL"],  # Base URL; deployment prefixes retained
    headers={"Authorization": f"Bearer {os.environ['MCP_TOKEN']}"},
    read_timeout=30,
)
print(result["mirrored_count"], result["tools"], result["servers"])
```

`registry_url` is mutually exclusive with MCP connection options (`server_command`,
`http_url`, `transport`, and `server_name`). Catalog discovery validates the complete
`tools` array before registration, rejects redirects and authentication failures,
and does not cache responses between callers. An empty authorized catalog returns
zero tools. Use a fresh `ToolMirror` for each identity/credential context and for
each refreshed catalog snapshot: mirroring is additive, not a live permission sync.
Reusing a catalog mirror with different credentials or a different registry is rejected.

Tools from different servers can share a name. Resolve these collisions explicitly:

```python
mirror = ToolMirror.for_ci()
mirror.mirror(
    registry_url=os.environ["MCP_REGISTRY_URL"],
    headers={"Authorization": f"Bearer {os.environ['MCP_TOKEN']}"},
    tool_name_map={
        ("/crm", "search"): "crm_search",
        ("/billing", "search"): "billing_search",
    },
    tools=["crm_search", "billing_search"],  # Filters use the mapped names
)
definition = mirror.registry.get_tool_definition("crm_search")
print(definition.input_schema, definition.metadata["server_path"])
```

Map keys use exact catalog `(server_path, tool_name)` values. Unknown mappings,
duplicate names and conflicts with existing registrations fail rather than
silently replacing tools. `tools=[]` selects no catalog tools; missing requested
names are errors. Generation failures are raised and new catalog registrations are
rolled back.

Definitions retain descriptions, original names, server paths, fetch time, schema
fingerprints and available-version metadata. Available versions do not establish
which backend version produced a schema. A stored catalog also does not define
virtual-server aliases or guarantee the current live inventory. Mirror the virtual
endpoint directly when you need its exposed names.

`to_langchain_tools()` preserves raw JSON Schema (including nested constraints and
references) for model binding. Raw dictionary schemas do not perform runtime input
validation. The lower-level `LangChainAdapter` retains its previous shallow Pydantic
conversion by default; `preserve_json_schema=True` selects exact schema preservation.
Saved metadata retains definitions; it does not serialize executable mock functions.

Generated responses are scaffolding. Use `mirror.customize()` or existing
data-driven scenarios to define meaningful expected outputs. Mocked LangGraph calls
go through `create_mockable_tool_wrapper(mirror.langgraph_registry)` and do not call
the gateway. This tests agent behavior, not gateway authorization. `MockToolsRegistry`
is an in-process collection and is distinct from the network registry service.

See [integration scope and upstream dependencies](mcp-gateway-integration-scope.md)
for the SD changes and the separate gateway follow-ups.

### Basic Mirroring (stdio)

```python
from stuntdouble.mirroring import ToolMirror

# Create mirror instance
mirror = ToolMirror()

# Mirror tools from MCP server (subprocess)
mirror.mirror(["python", "-m", "my_mcp_server"])

# Get LangChain-compatible tools
tools = mirror.to_langchain_tools()

# Use with agent
agent = llm.bind_tools(tools)
response = agent.invoke("Create an invoice for customer CUST-001")
```

### HTTP Server Mirroring

```python
from stuntdouble.mirroring import ToolMirror

mirror = ToolMirror()

# Mirror from HTTP MCP server
mirror.mirror(http_url="http://localhost:8080/mcp")

tools = mirror.to_langchain_tools()
```

### One-Line Convenience Functions

```python
from stuntdouble.mirroring import mirror, mirror_for_agent

# One-line mirroring (returns result dict)
result = mirror(["python", "-m", "my_server"])
print(f"Mirrored {result['mirrored_count']} tools: {result['tools']}")

# Mirror and get tools ready for agent
tools = mirror_for_agent(llm, ["python", "-m", "my_server"])
agent = llm.bind_tools(tools)
```

---

## LLM-Powered Generation

For realistic, contextual mock data, use an LLM to generate responses:

```python
from langchain_openai import ChatOpenAI
from stuntdouble.mirroring import ToolMirror

llm = ChatOpenAI(model="gpt-4o")
mirror = ToolMirror.with_llm(llm)

mirror.mirror(["python", "-m", "financial_mcp"])
tools = mirror.to_langchain_tools()

# Tools return realistic, contextual mock data
# e.g., create_invoice returns realistic invoice data
```

### Quality Presets

```python
from stuntdouble.mirroring import ToolMirror, QualityPreset

# High quality - uses LLM for all responses
mirror = ToolMirror.with_llm(llm, quality=QualityPreset.HIGH)

# Balanced quality - parameter-aware static generation
mirror = ToolMirror.with_llm(llm, quality=QualityPreset.BALANCED)

# Fast - static responses only (no LLM calls)
mirror = ToolMirror.for_ci()
```

---

## HTTP Authentication

Mirror tools from remote MCP servers that require authentication:

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
    headers={
        "X-API-Key": "abc123",
        "X-Client-ID": "my-app"
    }
)

# Multiple custom headers
result = mirror.mirror(
    http_url="http://internal.company.com/mcp",
    headers={
        "Authorization": "Bearer token",
        "X-Request-ID": "unique-id",
        "X-Environment": "production"
    }
)

tools = mirror.to_langchain_tools()
```

### Security Features

Headers are automatically included in all HTTP requests:
- SSE connection establishment (`GET /sse`)
- JSON-RPC message calls (`POST /messages`)

StuntDouble provides built-in security:

| Feature | Description |
|---------|-------------|
| **Header Validation** | Headers must be a dict with string keys/values |
| **Sensitive Data Protection** | Headers are redacted in logs and errors |
| **Protocol Compliance** | `Content-Type: application/json` auto-enforced |
| **Transport Validation** | Warning if headers specified for stdio |

---

## Customizing Mock Data

Override generated mock data for specific tools:

```python
from stuntdouble.mirroring import ToolMirror

mirror = ToolMirror()
mirror.mirror(["python", "-m", "my_server"])

# Customize specific tool responses
mirror.customize("get_customer", {
    "id": "CUST-001",
    "name": "Custom Test Corp",
    "tier": "platinum"
})

# List all mirrored tools
print(mirror.list_mirrors())
# [MirrorInfo(...), MirrorInfo(...), ...]

tools = mirror.to_langchain_tools()
```

---

## CI/CD Optimization

For CI/CD pipelines, use the optimized factory:

```python
from stuntdouble.mirroring import ToolMirror

# Optimized for CI: deterministic, no LLM calls, fast
mirror = ToolMirror.for_ci()
mirror.mirror(["python", "-m", "my_server"])
tools = mirror.to_langchain_tools()
```

### Caching

Enable caching for faster subsequent runs:

```python
mirror = ToolMirror().enable_caching(ttl_minutes=30)
mirror.mirror(["python", "-m", "my_server"])
# Second call uses cached tool definitions
mirror.mirror(["python", "-m", "my_server"])
```

---

## API Reference

### ToolMirror Class

| Method | Description |
|--------|-------------|
| `ToolMirror()` | Create mirror with default settings |
| `ToolMirror.with_llm(llm, quality=)` | Create with LLM-powered generation |
| `ToolMirror.for_ci()` | Create mirror optimized for CI/CD |
| `ToolMirror.for_langgraph(registry=None, quality=)` | Create mirror that also registers mirrored mocks in a LangGraph registry |
| `mirror.enable_caching(ttl_minutes=)` | Enable response caching |
| `mirror.enable_llm(llm)` | Add LLM generation to existing mirror |

### Mirroring Methods

| Method | Description |
|--------|-------------|
| `mirror.mirror(server_command=, http_url=, headers=)` | Mirror tools from MCP server |
| `mirror.to_langchain_tools()` | Convert to LangChain StructuredTool format |
| `mirror.customize(tool_name, data)` | Override mock data for a tool |
| `mirror.list_mirrors()` | List mirrored tools as `MirrorInfo` objects |
| `mirror.list_mirrors_by_server(server_name)` | Filter mirrored tools by source server |
| `mirror.get_stats()` | Return cache and generation statistics |
| `mirror.unregister(tool_name)` | Remove a mirrored tool |

### Convenience Functions

```python
from stuntdouble.mirroring import mirror, mirror_for_agent

# Mirror and get result dict
result = mirror(server_command=["python", "-m", "server"])
# Returns: {'mirrored_count': 5, 'tools': [...], 'server_name': '...'}

# Mirror and get tools ready for agent
tools = mirror_for_agent(llm, server_command=["python", "-m", "server"])
```

---

## Integration with Approaches

MCP Tool Mirroring works with both StuntDouble approaches:

- **[LangGraph Approach](langgraph-integration.md#using-mirrored-tools)** — Use mirrored tools with LangGraph's per-invocation mocking

---

## See Also

- [LangGraph Approach](langgraph-integration.md) — Per-invocation mocking
- [Quickstart Guide](quickstart.md) — Getting started
