"""Tests for the StuntDouble wiring of the reference agent.

No LLM credentials are needed: the model is a scripted fake, and the
``ToolNode``-level tests bypass the model entirely by feeding the node an
``AIMessage`` that already contains the tool call.
"""

from __future__ import annotations

import json

import pytest
from agent import build_graph, build_tool_node
from langchain_core.messages import HumanMessage, ToolMessage
from support import final_answer, run_tool_call, scenario_config, scripted_llm, tool_call

from stuntdouble import MissingMockError

pytestmark = pytest.mark.asyncio


def payload(message: ToolMessage) -> dict:
    assert message.status == "success", message.content
    return json.loads(message.content)


# -- ToolNode level: mock routing, matching, placeholders -------------------------


async def test_static_mock_replaces_real_tool(happy_path, recorder):
    node = build_tool_node(enable_mocks=True, recorder=recorder)

    message = await run_tool_call(
        node, tool_call("get_customer", {"customer_id": "CUST-001"}), scenario_config(happy_path)
    )

    assert payload(message) == {"id": "CUST-001", "name": "Acme Corp", "tier": "enterprise"}
    recorder.assert_called_once("get_customer")
    assert recorder.get_last_call("get_customer").was_mocked is True


async def test_input_matching_selects_case_by_operator(overdue_bills, recorder):
    node = build_tool_node(enable_mocks=True, recorder=recorder)
    config = scenario_config(overdue_bills)

    overdue = await run_tool_call(
        node, tool_call("list_bills", {"customer_id": "CUST-002", "status": "overdue"}), config
    )
    paid = await run_tool_call(node, tool_call("list_bills", {"customer_id": "CUST-002", "status": "paid"}), config)
    other = await run_tool_call(
        node, tool_call("list_bills", {"customer_id": "CUST-002", "status": "disputed"}), config
    )

    assert payload(overdue)["total_due"] == 4000.0  # matched {"status": {"$in": [...]}}
    assert payload(overdue)["customer_id"] == "CUST-002"  # {{input.customer_id}}
    assert payload(paid)["note"] == "No paid bills on record for CUST-002"  # matched $regex case
    assert payload(other) == {"bills": [], "total_due": 0}  # catch-all case
    recorder.assert_called_times("list_bills", 3)


async def test_placeholders_and_context_aware_factory(happy_path, recorder):
    node = build_tool_node(enable_mocks=True, recorder=recorder)

    message = await run_tool_call(
        node,
        tool_call("create_invoice", {"customer_id": "CUST-001", "amount": 250.0}),
        scenario_config(happy_path, user_id="qa-bot"),
    )

    invoice = payload(message)
    assert invoice["customer_id"] == "CUST-001"
    assert invoice["amount"] == 250.0
    assert invoice["created_by"] == "qa-bot"  # read from RunnableConfig.configurable
    assert len(invoice["invoice_id"]) == 36  # {{uuid}}
    assert invoice["due_date"] > invoice["created_at"]  # {{now + 30d}} vs {{now}}


async def test_scenario_driven_error_path(overdue_bills, recorder):
    """overdue_bills sets invoice_policy=reject_large: the mock raises, the wrapper returns an error ToolMessage."""
    node = build_tool_node(enable_mocks=True, recorder=recorder)

    message = await run_tool_call(
        node,
        tool_call("create_invoice", {"customer_id": "CUST-002", "amount": 9999.0}),
        scenario_config(overdue_bills),
    )

    assert message.status == "error"
    assert "exceeds limit 5000" in message.content
    assert recorder.get_last_call("create_invoice").error is not None


# -- Guard rails -----------------------------------------------------------------


async def test_real_tool_runs_when_no_scenario_metadata(recorder):
    """Same node, plain config: the wrapper steps aside and the real tool executes."""
    node = build_tool_node(enable_mocks=True, recorder=recorder)

    with pytest.raises(NotImplementedError, match="real customer API"):
        await run_tool_call(node, tool_call("get_customer", {"customer_id": "CUST-001"}), config={})

    assert recorder.get_last_call("get_customer").was_mocked is False


async def test_feature_flag_off_builds_plain_tool_node(happy_path):
    node = build_tool_node(enable_mocks=False)

    with pytest.raises(NotImplementedError):
        await run_tool_call(node, tool_call("get_customer", {"customer_id": "CUST-001"}), scenario_config(happy_path))


async def test_unmocked_tool_with_scenario_is_a_configuration_error(recorder):
    """Strict mode: scenario present but no case for the tool -> MissingMockError, not a silent real call."""
    node = build_tool_node(enable_mocks=True, recorder=recorder)

    with pytest.raises(MissingMockError):
        await run_tool_call(
            node,
            tool_call("list_bills", {"customer_id": "CUST-001"}),
            scenario_config({"scenario_id": "no-list-bills-cases", "mocks": {}}),
        )


# -- Whole graph with a scripted model --------------------------------------------


async def test_full_graph_records_tool_trajectory(happy_path, recorder):
    llm = scripted_llm(
        tool_call("get_customer", {"customer_id": "CUST-001"}, call_id="c1"),
        tool_call("list_bills", {"customer_id": "CUST-001", "status": "all"}, call_id="c2"),
        final_answer("Acme Corp has no outstanding bills."),
    )
    graph = build_graph(llm, enable_mocks=True, recorder=recorder)

    state = await graph.ainvoke(
        {"messages": [HumanMessage(content="Does Acme owe us anything?")]},
        config=scenario_config(happy_path),
    )

    assert state["messages"][-1].content == "Acme Corp has no outstanding bills."
    recorder.assert_call_order("get_customer", "list_bills")
    recorder.assert_called_with("list_bills", customer_id="CUST-001", status="all")
    recorder.assert_not_called("create_invoice")
    assert all(call.was_mocked for call in recorder.calls)
    assert {call.scenario_id for call in recorder.calls} == {"happy-path"}
