# End-to-End Multi-Tool Agent Tutorial

This tutorial walks through a complete testing workflow for a LangGraph agent that uses multiple tools. We will:

1. Build a small billing support agent with three tools
2. Mock each tool with StuntDouble using input matchers and dynamic resolvers
3. Run the agent end-to-end with `scenario_metadata`
4. Assert tool call order and arguments with `CallRecorder` in pytest
5. Cover a few common edge cases

If you already know the individual pieces, this guide shows how they fit together in one realistic test.

**Prerequisites:** StuntDouble requires **Python 3.12+**. This tutorial also assumes you already have a working LangGraph agent node and tool setup.

---

## What We Are Testing

Assume the agent handles a request like:

> "Check account CUST-100. If they have overdue bills, create a follow-up invoice."

At runtime the agent may call:

- `get_customer(customer_id)`
- `list_bills(customer_id, status)`
- `create_invoice(customer_id, amount, reason)`

In production these tools might hit CRMs, billing systems, or payment APIs. In tests we want:

- deterministic responses
- no network calls
- assertions about which tools were called
- confidence that the agent took the expected path

---

## Step 1: Define the Tools

The tools below are intentionally simple. The important part is that they are real LangChain tools wired into a real `ToolNode`.

```python
from langchain_core.tools import tool


@tool
def get_customer(customer_id: str) -> dict:
    """Fetch a customer record from the CRM."""
    raise NotImplementedError("Production CRM call")


@tool
def list_bills(customer_id: str, status: str = "open") -> dict:
    """List bills for a customer."""
    raise NotImplementedError("Production billing call")


@tool
def create_invoice(customer_id: str, amount: int, reason: str) -> dict:
    """Create a follow-up invoice."""
    raise NotImplementedError("Production invoice call")
```

---

## Step 2: Build a LangGraph Agent

StuntDouble plugs into LangGraph through `ToolNode(..., awrap_tool_call=wrapper)`. That means your graph stays production-shaped.

```python
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from stuntdouble import (
    CallRecorder,
    MockToolsRegistry,
    create_mockable_tool_wrapper,
    validate_registry_mocks,
)


tools = [get_customer, list_bills, create_invoice]

registry = MockToolsRegistry()
recorder = CallRecorder()

# Data-driven mocks read cases from scenario_metadata["mocks"][tool_name]
registry.register_data_driven("get_customer")
registry.register_data_driven("list_bills")
registry.register_data_driven("create_invoice")

wrapper = create_mockable_tool_wrapper(
    registry,
    recorder=recorder,
)

builder = StateGraph(MessagesState)
builder.add_node("agent", agent_node)  # Your LLM/planner node; see langgraph-integration.md for a full example.
builder.add_node("tools", ToolNode(tools, awrap_tool_call=wrapper))
builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", tools_condition)
builder.add_edge("tools", "agent")

graph = builder.compile()
```

Why `register_data_driven()` here?

- It keeps the tutorial focused on test scenarios instead of custom factory code
- It supports matcher-based conditional responses
- It resolves placeholders like `{{input.customer_id}}`, `{{now}}`, and `{{sequence('INV')}}`

---

## Step 3: Define a Multi-Tool Scenario

Now we provide one scenario that mocks all three tools. Each tool can have multiple cases.

```python
from stuntdouble import inject_scenario_metadata, validate_registry_mocks


scenario_metadata = {
    "scenario_id": "billing-agent-overdue-flow",
    "mocks": {
        "get_customer": [
            {
                "input": {"customer_id": {"$regex": "^CUST-"}},
                "output": {
                    "id": "{{input.customer_id}}",
                    "name": "Acme Manufacturing",
                    "tier": "gold",
                    "status": "active",
                },
            }
        ],
        "list_bills": [
            {
                "input": {
                    "customer_id": "CUST-100",
                    "status": "overdue",
                },
                "output": {
                    "bills": [
                        {"id": "BILL-900", "amount": 1200, "status": "overdue"},
                        {"id": "BILL-901", "amount": 300, "status": "overdue"},
                    ],
                    "total_overdue": 1500,
                },
            },
            {
                "output": {
                    "bills": [],
                    "total_overdue": 0,
                }
            },
        ],
        "create_invoice": [
            {
                "input": {"amount": {"$gt": 1000}},
                "output": {
                    "invoice_id": "{{sequence('INV')}}",
                    "customer_id": "{{input.customer_id}}",
                    "amount": "{{input.amount}}",
                    "reason": "{{input.reason}}",
                    "created_at": "{{now}}",
                    "status": "pending_review",
                },
            },
            {
                "output": {
                    "invoice_id": "{{sequence('INV')}}",
                    "customer_id": "{{input.customer_id}}",
                    "amount": "{{input.amount}}",
                    "reason": "{{input.reason}}",
                    "created_at": "{{now}}",
                    "status": "created",
                }
            },
        ],
    },
}

errors = validate_registry_mocks(tools, scenario_metadata)
if errors:
    raise ValueError(f"Invalid scenario metadata: {errors}")

config = inject_scenario_metadata({}, scenario_metadata)
```

This single scenario demonstrates a few useful patterns:

- `get_customer` uses a `$regex` matcher
- `list_bills` has a specific case plus a catch-all fallback
- `create_invoice` returns different outputs based on the amount
- placeholder resolution echoes tool inputs into the response

---

## Step 4: Run the Agent End-to-End

Invoke the compiled graph exactly as you would in production, but pass the scenario through config.

```python
from langchain_core.messages import HumanMessage


result = await graph.ainvoke(
    {
        "messages": [
            HumanMessage(
                "Check account CUST-100. If they have overdue bills, create a follow-up invoice."
            )
        ]
    },
    config=config,
)
```

If the agent decides to:

1. fetch the customer
2. fetch overdue bills
3. create an invoice for the overdue amount

then all three calls will be intercepted by StuntDouble and recorded by `CallRecorder`.

---

## Step 5: Assert Tool Behavior in pytest

This is the part many teams want in practice: not just "did the agent return something reasonable?" but "did it use the right tools, in the right order, with the right arguments?"

```python
import pytest
from langchain_core.messages import HumanMessage
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from stuntdouble import (
    CallRecorder,
    MockToolsRegistry,
    create_mockable_tool_wrapper,
    inject_scenario_metadata,
    validate_registry_mocks,
)


@pytest.fixture
def recorder():
    return CallRecorder()


@pytest.fixture
def graph_with_mocks(recorder):
    registry = MockToolsRegistry()
    registry.register_data_driven("get_customer")
    registry.register_data_driven("list_bills")
    registry.register_data_driven("create_invoice")

    tools = [get_customer, list_bills, create_invoice]
    wrapper = create_mockable_tool_wrapper(
        registry,
        recorder=recorder,
    )

    builder = StateGraph(MessagesState)
    builder.add_node("agent", agent_node)  # Your LLM/planner node; see langgraph-integration.md for a full example.
    builder.add_node("tools", ToolNode(tools, awrap_tool_call=wrapper))
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")
    return builder.compile()


@pytest.mark.asyncio
async def test_overdue_billing_flow(graph_with_mocks, recorder):
    scenario_metadata = {
        "scenario_id": "pytest-overdue-billing-flow",
        "mocks": {
            "get_customer": [
                {
                    "output": {
                        "id": "{{input.customer_id}}",
                        "name": "Acme Manufacturing",
                        "status": "active",
                    }
                }
            ],
            "list_bills": [
                {
                    "input": {"status": "overdue"},
                    "output": {
                        "bills": [{"id": "BILL-900", "amount": 1200}],
                        "total_overdue": 1200,
                    },
                }
            ],
            "create_invoice": [
                {
                    "output": {
                        "invoice_id": "{{sequence('INV')}}",
                        "customer_id": "{{input.customer_id}}",
                        "amount": "{{input.amount}}",
                        "reason": "{{input.reason}}",
                        "status": "created",
                    }
                }
            ],
        },
    }

    errors = validate_registry_mocks([get_customer, list_bills, create_invoice], scenario_metadata)
    assert errors == {}

    config = inject_scenario_metadata({}, scenario_metadata)

    await graph_with_mocks.ainvoke(
        {
            "messages": [
                HumanMessage(
                    "Check account CUST-100. If they have overdue bills, create a follow-up invoice."
                )
            ]
        },
        config=config,
    )

    recorder.assert_call_order("get_customer", "list_bills", "create_invoice")

    recorder.assert_called_with("get_customer", customer_id="CUST-100")
    recorder.assert_called_with("list_bills", customer_id="CUST-100", status="overdue")
    recorder.assert_called_once("create_invoice")

    invoice_call = recorder.get_last_call("create_invoice")
    assert invoice_call is not None
    assert invoice_call.was_mocked is True
    assert invoice_call.args["customer_id"] == "CUST-100"
    assert invoice_call.args["amount"] == 1200

    invoice_result = recorder.get_result("create_invoice")
    assert invoice_result["status"] == "created"
    assert invoice_result["invoice_id"].startswith("INV-")
```

This test checks:

- the workflow path
- the arguments used for each tool call
- that the invoice tool was mocked rather than executed for real
- the actual mock result returned to the agent

---

## Common Patterns

### Conditional Responses Per Tool

Use multiple cases ordered from specific to general:

```python
"list_bills": [
    {
        "input": {"status": "overdue", "customer_id": "CUST-100"},
        "output": {"bills": [{"id": "BILL-1"}], "total_overdue": 800},
    },
    {
        "input": {"status": "overdue"},
        "output": {"bills": [{"id": "BILL-2"}], "total_overdue": 200},
    },
    {
        "output": {"bills": [], "total_overdue": 0},
    },
]
```

Put your most specific matcher first and leave a catch-all case last.

### Dynamic Outputs That Echo Inputs

Resolvers are useful when your assertions should depend on agent-generated inputs:

```python
"create_invoice": [
    {
        "output": {
            "invoice_id": "{{sequence('INV')}}",
            "customer_id": "{{input.customer_id}}",
            "amount": "{{input.amount}}",
            "created_at": "{{now}}",
        }
    }
]
```

This makes the mock feel realistic without hard-coding every possible request.

### Simulating a Tool Error

For error cases, use a custom mock that raises:

```python
def failing_invoice_mock(scenario_metadata):
    def mock_fn(customer_id: str, amount: int, reason: str) -> dict:
        raise ValueError("Billing API timeout")
    return mock_fn


registry = MockToolsRegistry()
registry.register_data_driven("get_customer")
registry.register_data_driven("list_bills")
registry.register("create_invoice", failing_invoice_mock)

wrapper = create_mockable_tool_wrapper(
    registry,
    strict_mock_errors=True,
)
```

With `strict_mock_errors=True`, the wrapper re-raises mock failures so your test can use:

```python
with pytest.raises(ValueError, match="Billing API timeout"):
    await graph.ainvoke(state, config=config)
```

### Allowing Some Tools to Stay Real

If you want a hybrid test where only some tools are mocked:

```python
wrapper = create_mockable_tool_wrapper(
    registry,
    require_mock_when_scenario=False,
)
```

That tells StuntDouble to fall back to the real tool when no mock is registered for a tool in the current scenario.

---

## Troubleshooting

### "Mock for tool X is registered but its input conditions were not met"

This usually means the tool was mocked, but none of its input cases matched the actual arguments.

Fix it by either:

- adding a catch-all case with no `input`
- relaxing the matcher
- asserting the recorded args to see what the agent actually sent

```python
print(recorder.get_calls("list_bills"))
```

### "No mock registered for tool X"

This happens when `scenario_metadata` is present and the wrapper is in strict mode, but the registry has no mock for that tool.

Either:

- register the missing tool with `register_data_driven()` or `register()`
- or set `require_mock_when_scenario=False` for hybrid runs

### Signature Mismatch Errors

`register_data_driven()` scenarios are best validated with `validate_registry_mocks(tools, scenario_metadata)` before invocation.

If you register a custom mock factory with `register()` instead, then `tools=tools` and `validate_signatures=True` are useful for checking that the returned callable matches the real tool signature.

---

## When to Use This Pattern

This end-to-end setup works especially well when:

- your agent can take multiple tool paths depending on the prompt
- you want one test to verify both final behavior and internal tool usage
- you need scenario-specific mock data per invocation
- you want fast tests without modifying production graph wiring

If you only need a single static mock, the [Quickstart](quickstart.md) is simpler. If you need deeper detail on matcher syntax or placeholder support, continue with the dedicated guides below.

---

## See Also

- [Quickstart](quickstart.md)
- [LangGraph Integration](langgraph-integration.md)
- [Matchers and Resolvers](matchers-and-resolvers.md)
- [Call Recording](call-recording.md)
- [Signature Validation](signature-validation.md)
