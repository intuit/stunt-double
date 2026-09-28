---
name: stuntdouble-adoption
description: Integrates StuntDouble per-invocation tool mocking into an existing LangGraph (1.0+) agent — discovers the tools and ToolNode, scaffolds a mocking package, wires the awrap_tool_call wrapper behind a feature flag, generates JSON scenarios, and produces a passing pytest suite with CallRecorder assertions. Use when asked to add StuntDouble, mock tools in LangGraph, enable per-request/scenario mocking, or set up deterministic tool mocking for agent tests and evals.
---

# StuntDouble adoption for LangGraph agents

Takes an agent from "no mocking" to a wired, tested setup in one session. Mocks are selected **per invocation** by `scenario_metadata` in the `RunnableConfig`; without it, real tools run. Zero production impact when the feature flag is off.

A complete, runnable result of this workflow lives in [`reference/`](reference/). Read it once before starting; adapt it, don't copy it blindly.

## Prerequisites

- `langgraph >= 1.0.0` (`ToolNode(..., awrap_tool_call=)` is the integration point) and `langchain-core >= 1.2.5`
- Python `>= 3.12`
- The agent builds its tool node with `ToolNode` (or a thin wrapper around one)
- The user has named the agent directory (`AGENT_DIR`). All edits stay inside it.

If LangGraph is older, upgrade it first and stop if the upgrade is non-trivial — that is the user's call.

## Code style

Match the target codebase. Do not add comments denser than the surrounding file, defensive `try/except` where the codebase has none, or `Any` casts to silence types. Keep imports at the top of modules.

## Workflow

Copy this checklist into the conversation and tick items as you go:

```
StuntDouble adoption:
- [ ] 1. Install + create mocking package
- [ ] 2. Discover tools, signatures, sources
- [ ] 3. Pick an authoring mode per tool
- [ ] 4. Registry module
- [ ] 5. Wire ToolNode behind a feature flag
- [ ] 6. Get scenario_metadata into the RunnableConfig
- [ ] 7. Scenario files
- [ ] 8. Tests (must pass with no LLM credentials)
- [ ] 9. Smoke test
- [ ] 10. Eval pipeline hookup (optional)
```

### 1. Install and create the mocking package

```bash
uv add stuntdouble          # or: pip install stuntdouble / poetry add stuntdouble
uv add --dev pytest pytest-asyncio
```

Create, next to the agent module:

```
AGENT_DIR/<package>/mocking/
├── __init__.py      # re-exports build_registry
├── mocks.py         # hand-written factories only
└── registry.py      # build_registry() -> MockToolsRegistry
AGENT_DIR/scenarios/           # JSON scenario files
AGENT_DIR/tests/test_mocked_agent.py
```

See [`reference/mocking/`](reference/mocking/) for the shape of each file.

### 2. Discover tools, signatures and sources

1. Find `ToolNode(` in the graph builder and trace where its `tools` list comes from.
2. For each tool, record its **name** (`tool.name`, case-sensitive) and **parameters**:
   - `@tool`-decorated function → the function's parameters (skip `InjectedState`, `InjectedToolCallId`, `RunnableConfig`, `ToolRuntime` params; the LLM never supplies those)
   - `BaseTool` subclass → `_run` / `_arun` parameters minus `self` and `run_manager`
   - MCP tool (via `langchain-mcp-adapters`) → `tool.args_schema` JSON properties
3. Classify each tool's **source**: local or MCP. MCP tools are loaded at runtime; if the same name also exists as a local fallback with a different schema, mocks for the MCP schema must be registered only when the MCP tools actually loaded (see step 4).

Write the inventory down before writing any mock:

```
# tool_name        | params (name: type = default)                         | source
# get_customer     | customer_id: str                                       | local
# list_bills       | customer_id: str, status: str = "all"                  | local
# create_invoice   | customer_id: str, amount: float, due_date: str | None = None | local
```

This inventory is the source of truth for every `mock_fn` signature. Dropping a parameter, renaming one, or replacing `RAGInputState` with `dict` are the classic mistakes.

### 3. Pick an authoring mode per tool

| Tool needs | Use | Where |
|---|---|---|
| Fixed or input-dependent output, no logic | `registry.register_data_driven(name, fallback=...)` — cases live in scenario JSON | `registry.py` only |
| Logic, computed values, raising errors, or runtime context (`user_id`, headers) | Hand-written factory `def name_mock(scenario_metadata, config=None) -> mock_fn` | `mocks.py` + `registry.py` |
| One-off stub inside a unit test | `registry.mock(name).returns(...)` / `.when(...)` | the test |

Default to data-driven. Factory patterns (simple, conditional on `scenario_metadata`, input matching, placeholders, context-aware, error injection, async) are in [PATTERNS.md](PATTERNS.md).

**Signature gate:** the inner `mock_fn` of every hand-written factory must accept exactly the parameters from the step-2 inventory. Open the real tool side-by-side and check names, defaults and order before moving on.

### 4. Registry module

`registry.py` exposes one function that builds a populated `MockToolsRegistry`. Pass `tool=` for hand-written factories so a signature drift fails at startup:

```python
def build_registry(mcp_tools: list | None = None) -> MockToolsRegistry:
    registry = MockToolsRegistry()
    registry.register_data_driven("list_bills", fallback={"bills": []})
    registry.register("get_customer", mock_fn=get_customer_mock, tool=get_customer)
    if mcp_tools:  # MCP-schema mocks only when those tools were actually loaded
        registry.register("search_docs", mock_fn=search_docs_mock)
    return registry
```

`register()` replaces an existing registration for the same name silently — register each tool once.

### 5. Wire the ToolNode behind a feature flag

```python
def build_tool_node(*, enable_mocks: bool | None = None, recorder: CallRecorder | None = None) -> ToolNode:
    if enable_mocks is None:
        enable_mocks = settings.enable_tool_mocks      # or os.getenv("STUNTDOUBLE_ENABLED")
    if not enable_mocks:
        return ToolNode(tools)
    wrapper = create_mockable_tool_wrapper(build_registry(), recorder=recorder)
    return ToolNode(tools, awrap_tool_call=wrapper)
```

- Default the flag to **off**; turn it on in local/test/eval settings.
- If the project wraps `ToolNode` in a custom node, that node must pass `awrap_tool_call` through to the `ToolNode` it constructs.
- Keep `require_mock_when_scenario=True` (default). A scenario that names no case for a tool the agent calls should fail with `MissingMockError`, not silently hit the real API.
- `tools=..., validate_signatures=True` on the wrapper rejects `**kwargs` mocks (data-driven and `MockBuilder`) — prefer `tool=` at registration (step 4).

Full example: [`reference/agent.py`](reference/agent.py).

### 6. Get `scenario_metadata` into the `RunnableConfig`

The wrapper reads `config["configurable"]["scenario_metadata"]`. Pick the path that matches how the agent is served:

**LangGraph Server / `langgraph dev`** — nothing to implement; callers pass it in the run config:

```json
{"assistant_id": "agent", "input": {...}, "config": {"configurable": {"scenario_metadata": {...}}}}
```

**Custom HTTP service (FastAPI etc.)** — read a header and inject:

```python
from stuntdouble import inject_scenario_metadata

raw = request.headers.get("X-Scenario-Metadata")
if raw:
    config = inject_scenario_metadata(config, json.loads(raw))
```

**Direct invocation (tests, notebooks)** — `graph.ainvoke(state, config=inject_scenario_metadata({}, scenario))`.

Only accept the header/field in environments where the feature flag is on.

### 7. Scenario files

One JSON file per scenario under `AGENT_DIR/scenarios/`. Generate at least:

- a **happy path** with a static case per tool and `{{sequence('X')}}` / `{{now - 3d}}` placeholders
- an **edge case** using operators (`$in`, `$gt`, `$regex`, `$contains`) with a catch-all last case, plus whatever top-level keys your hand-written factories read (e.g. `"invoice_policy"`)

Format and samples: [SCENARIOS.md](SCENARIOS.md) and [`reference/scenarios/`](reference/scenarios/). Make outputs resemble the real tool's response shape from the step-2 inventory.

### 8. Tests

Scaffold from [`reference/tests/`](reference/tests/). The suite must pass with **no LLM credentials**:

- A scripted `GenericFakeChatModel` (see `support.py`) drives the full graph.
- `ToolNode`-level tests skip the model entirely by feeding an `AIMessage` with `tool_calls` through a one-node graph (`run_tool_call` helper — `ToolNode` cannot be invoked bare in LangGraph 1.0).
- Cover: static mock, operator-matched case + catch-all, placeholders, context-aware factory, scenario-driven error path, real tool when no scenario, feature flag off, `MissingMockError` for an unmocked tool, and a full-graph trajectory with `CallRecorder` (`assert_call_order`, `assert_called_with`, `assert_not_called`).

Run it and paste the result. Do not report step 8 done until it is green.

### 9. Smoke test

LangGraph Server:

```bash
curl -s localhost:2024/runs/wait -H 'Content-Type: application/json' -d '{
  "assistant_id": "agent",
  "input": {"messages": [{"role": "user", "content": "Does customer CUST-001 owe us anything?"}]},
  "config": {"configurable": {"scenario_metadata": '"$(cat scenarios/happy_path.json)"'}}
}'
```

Custom service with the header from step 6:

```bash
curl -s localhost:8000/invoke -H 'Content-Type: application/json' \
  -H "X-Scenario-Metadata: $(cat scenarios/happy_path.json)" \
  -d '{"message": "Does customer CUST-001 owe us anything?"}'
```

Repeat without the scenario and confirm real tools run.

### 10. Eval pipeline hookup (optional)

Ask before doing this. If the project has an evaluation dataset:

1. Add a `scenario_metadata` column holding the scenario JSON (empty for rows that need real tools or no tools).
2. In the eval runner, parse the column and pass it the same way step 6 expects (run config or header).
3. Offer to generate rows: one per registered tool whose prompt naturally triggers that tool, plus a few no-tool rows; reference answers must reflect the mock data.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Real tool runs even with a scenario | Flag off, or `awrap_tool_call` not reaching the `ToolNode`; check `graph.get_graph().nodes["tools"]` |
| `MissingMockError: No mock registered` | Name mismatch (case-sensitive) — compare with `registry.list_registered()`. Also raised when a factory itself throws; check logs for "Mock factory ... raised" |
| `MissingMockError: ... conditions were not met` | Data-driven cases have no catch-all and no `fallback=` |
| `SignatureMismatchError` at startup | `mock_fn` params differ from the inventory; fix the mock, never the tool |
| `SignatureMismatchError` at runtime for a data-driven/builder mock | Wrapper-level `validate_signatures=True` can't see `**kwargs` ([#69](https://github.com/intuit/stunt-double/issues/69)); drop `tools=` and use `tool=` at registration |
| `SignatureMismatchError` only when MCP is down | MCP-schema mock registered while the local fallback loaded; gate the registration on `mcp_tools` |
| Placeholder comes back literally (`"{{...}}"`) | Unknown expression, or the value was `None`; see the placeholder table in SCENARIOS.md |
| `ValueError: Missing required config key` when calling `ToolNode` directly | Wrap it in a one-node graph (`run_tool_call` in `reference/tests/support.py`) |

Debug: `logging.getLogger("stuntdouble").setLevel(logging.DEBUG)`.

## Final checklist

- [ ] Inventory written; every hand-written `mock_fn` matches it
- [ ] Each tool registered once; MCP-schema mocks gated
- [ ] `ToolNode` gets `awrap_tool_call` only when the flag is on; flag defaults off
- [ ] `scenario_metadata` reaches `configurable` via run config or header
- [ ] Happy-path and edge-case scenario files exist and use operators + placeholders
- [ ] Test suite green with no credentials; `CallRecorder` assertions present
- [ ] Smoke test done with and without a scenario
- [ ] No style drift (comments, defensive code, `Any` casts)

## Resources

- Runnable result: [`reference/`](reference/)
- Factory patterns: [PATTERNS.md](PATTERNS.md)
- Scenario format: [SCENARIOS.md](SCENARIOS.md)
- Library docs: https://intuit.github.io/stunt-double
