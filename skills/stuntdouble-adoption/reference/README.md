# Reference result of the adoption skill

A minimal LangGraph agent with three tools, wired for StuntDouble the way SKILL.md describes. It runs against the published `stuntdouble` package with no LLM credentials.

```
reference/
├── tools.py               # the "real" tools (raise NotImplementedError — stand-ins for real APIs)
├── agent.py               # graph builder; build_tool_node() attaches the wrapper behind STUNTDOUBLE_ENABLED
├── mocking/
│   ├── __init__.py
│   ├── mocks.py           # hand-written factories: simple, conditional + context-aware
│   └── registry.py        # build_registry(): data-driven list_bills + validated factories
├── scenarios/
│   ├── happy_path.json    # static outputs + {{sequence}} / {{now - Nd}} placeholders
│   └── overdue_bills.json # $in / $regex cases, catch-all, invoice_policy flag read by a factory
├── tests/
│   ├── conftest.py        # fixtures: recorder, scenarios
│   ├── support.py         # scripted fake LLM, tool_call()/final_answer(), run_tool_call()
│   └── test_mocked_agent.py
└── conftest.py            # puts this directory on sys.path for the tests
```

## Run

From a checkout of this repository:

```bash
uv run pytest skills/stuntdouble-adoption/reference -c /dev/null --rootdir skills/stuntdouble-adoption/reference
```

Or copy the directory anywhere with `stuntdouble`, `pytest` and `pytest-asyncio` installed and run `pytest` inside it.

## Mapping to SKILL.md steps

| Step | File |
|---|---|
| 2 Discover | `tools.py` is the inventory source |
| 3–4 Authoring + registry | `mocking/mocks.py`, `mocking/registry.py` |
| 5 Feature-flagged wiring | `agent.py::build_tool_node` |
| 6 Config propagation | `tests/support.py::scenario_config` (direct invocation variant) |
| 7 Scenarios | `scenarios/*.json` |
| 8 Tests | `tests/` |

## What the tests prove

- A scenario routes a call to the mock; the same node with a plain config runs the real tool.
- Operator matching (`$in`, `$regex`) picks the right case; the catch-all handles the rest.
- Placeholders resolve and a factory reads `user_id` from `RunnableConfig.configurable`.
- A scenario flag makes a factory raise → `ToolMessage(status="error")`.
- Feature flag off → plain `ToolNode`.
- A tool with no case under `mocks` fails with `MissingMockError` rather than calling the real API.
- The whole ReAct loop with a scripted model produces the expected `CallRecorder` trajectory.
