"""End-to-end integration tests — full StuntDouble pipeline through a real LangGraph graph."""

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from stuntdouble import (
    CallRecorder,
    MockToolsRegistry,
    create_mockable_tool_wrapper,
    inject_scenario_metadata,
    register_data_driven,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


# -- Fake LLM ----------------------------------------------------------------


class FakeChatWithTools(GenericFakeChatModel):
    """GenericFakeChatModel that accepts bind_tools as a no-op."""

    def bind_tools(self, tools, **kwargs):
        return self


# -- Stub tools ---------------------------------------------------------------


@tool
def get_customer(customer_id: str) -> dict:
    """Look up a customer by ID."""
    raise NotImplementedError("Real API")


@tool
def list_items(category: str = "", status: str = "") -> dict:
    """List items with optional filters."""
    raise NotImplementedError("Real API")


@tool
def create_order(customer_id: str, item_id: str, quantity: int = 1) -> dict:
    """Create an order."""
    raise NotImplementedError("Real API")


E2E_TOOLS = [get_customer, list_items, create_order]


# -- Helpers ------------------------------------------------------------------


def make_tool_call(name: str, args: dict, call_id: str = None) -> AIMessage:
    """Construct an AIMessage with a single tool call."""
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id or f"call_{name}"}],
    )


def make_final_response(text: str) -> AIMessage:
    """Construct a terminal AIMessage (no tool calls = loop ends)."""
    return AIMessage(content=text)


def build_e2e_graph(responses, wrapper, tools=None):
    """Build a complete LangGraph ReAct graph with fake LLM and StuntDouble wrapper."""
    tools = tools or E2E_TOOLS
    llm = FakeChatWithTools(messages=iter(responses))
    llm_with_tools = llm.bind_tools(tools)

    async def agent_node(state: MessagesState):
        ai = await llm_with_tools.ainvoke(state["messages"])
        return {"messages": [ai]}

    builder = StateGraph(MessagesState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", ToolNode(tools=tools, awrap_tool_call=wrapper))
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")
    return builder.compile()


def _run_graph(registry, recorder, responses, scenario_metadata):
    """Build graph, create config, return (graph, config) tuple."""
    wrapper = create_mockable_tool_wrapper(registry, recorder=recorder)
    graph = build_e2e_graph(responses, wrapper)
    config = inject_scenario_metadata({}, scenario_metadata)
    return graph, config


async def _invoke(graph, config, user_message="test"):
    return await graph.ainvoke(
        {"messages": [HumanMessage(content=user_message)]},
        config=config,
    )


# -- 1. Fluent Builder -------------------------------------------------------


class TestFluentBuilderE2E:
    """Verify registry.mock().returns() works through a real graph."""

    async def test_simple_mock_returns_response(self):
        registry = MockToolsRegistry()
        recorder = CallRecorder()
        registry.mock("get_customer").returns({"id": "C1", "name": "Acme"})

        graph, config = _run_graph(
            registry,
            recorder,
            [
                make_tool_call("get_customer", {"customer_id": "C1"}),
                make_final_response("Found Acme."),
            ],
            {"scenario_id": "builder-test"},
        )

        result = await _invoke(graph, config)

        recorder.assert_called("get_customer")
        assert recorder.calls[0].was_mocked is True
        assert "Acme" in result["messages"][-1].content

    async def test_returns_fn_with_computation(self):
        registry = MockToolsRegistry()
        recorder = CallRecorder()
        registry.mock("create_order").returns_fn(
            lambda customer_id, item_id, quantity=1: {
                "order_id": "ORD-1",
                "total_items": quantity,
            }
        )

        graph, config = _run_graph(
            registry,
            recorder,
            [
                make_tool_call("create_order", {"customer_id": "C1", "item_id": "I1", "quantity": 3}),
                make_final_response("Order created."),
            ],
            {"scenario_id": "returns-fn-test"},
        )

        await _invoke(graph, config)
        recorder.assert_called("create_order")


# -- 2. Input Matching -------------------------------------------------------


class TestInputMatchingE2E:
    """Verify input matching operators through a real graph."""

    async def test_regex_matching_selects_correct_case(self):
        registry = MockToolsRegistry()
        recorder = CallRecorder()
        register_data_driven(registry, "get_customer")

        scenario = {
            "scenario_id": "input-match-test",
            "mocks": {
                "get_customer": [
                    {"input": {"customer_id": {"$regex": "^VIP"}}, "output": {"tier": "platinum"}},
                    {"output": {"tier": "standard"}},
                ],
            },
        }

        graph, config = _run_graph(
            registry,
            recorder,
            [
                make_tool_call("get_customer", {"customer_id": "VIP-001"}),
                make_final_response("Done."),
            ],
            scenario,
        )

        await _invoke(graph, config)
        recorder.assert_called_with("get_customer", customer_id="VIP-001")

    async def test_catch_all_when_no_match(self):
        registry = MockToolsRegistry()
        recorder = CallRecorder()
        register_data_driven(registry, "get_customer")

        scenario = {
            "scenario_id": "catch-all-test",
            "mocks": {
                "get_customer": [
                    {"input": {"customer_id": {"$regex": "^VIP"}}, "output": {"tier": "platinum"}},
                    {"output": {"tier": "standard"}},
                ],
            },
        }

        graph, config = _run_graph(
            registry,
            recorder,
            [
                make_tool_call("get_customer", {"customer_id": "REGULAR-001"}),
                make_final_response("Done."),
            ],
            scenario,
        )

        await _invoke(graph, config)
        recorder.assert_called("get_customer")

    async def test_numeric_operators(self):
        registry = MockToolsRegistry()
        recorder = CallRecorder()
        register_data_driven(registry, "create_order")

        scenario = {
            "scenario_id": "numeric-ops-test",
            "mocks": {
                "create_order": [
                    {"input": {"quantity": {"$gte": 10}}, "output": {"discount": "bulk"}},
                    {"output": {"discount": "none"}},
                ],
            },
        }

        graph, config = _run_graph(
            registry,
            recorder,
            [
                make_tool_call("create_order", {"customer_id": "C1", "item_id": "I1", "quantity": 25}),
                make_final_response("Done."),
            ],
            scenario,
        )

        await _invoke(graph, config)
        recorder.assert_called("create_order")


# -- 3. Data-Driven ----------------------------------------------------------


class TestDataDrivenE2E:
    """Verify register_data_driven + scenario dict through a real graph."""

    async def test_multi_tool_scenario(self):
        registry = MockToolsRegistry()
        recorder = CallRecorder()
        register_data_driven(registry, "get_customer")
        register_data_driven(registry, "list_items")

        scenario = {
            "scenario_id": "data-driven-test",
            "mocks": {
                "get_customer": [
                    {"input": {"customer_id": "C1"}, "output": {"id": "C1", "name": "Acme"}},
                ],
                "list_items": [
                    {"input": {"status": "active"}, "output": {"items": [{"id": "I1"}]}},
                    {"output": {"items": []}},
                ],
            },
        }

        graph, config = _run_graph(
            registry,
            recorder,
            [
                make_tool_call("get_customer", {"customer_id": "C1"}),
                make_tool_call("list_items", {"status": "active"}),
                make_final_response("Found 1 item."),
            ],
            scenario,
        )

        await _invoke(graph, config)
        recorder.assert_call_order("get_customer", "list_items")
        assert len(recorder.calls) == 2


# -- 4. Dynamic Placeholders -------------------------------------------------


class TestDynamicPlaceholdersE2E:
    """Verify placeholder resolution through a real graph."""

    async def test_uuid_and_timestamp_resolve(self):
        registry = MockToolsRegistry()
        recorder = CallRecorder()
        register_data_driven(registry, "create_order")

        scenario = {
            "scenario_id": "placeholder-test",
            "mocks": {
                "create_order": [
                    {
                        "output": {
                            "order_id": "{{uuid}}",
                            "created_at": "{{now}}",
                            "customer_id": "{{input.customer_id}}",
                            "seq": "{{sequence('ORD')}}",
                        },
                    }
                ],
            },
        }

        graph, config = _run_graph(
            registry,
            recorder,
            [
                make_tool_call("create_order", {"customer_id": "C1", "item_id": "I1"}),
                make_final_response("Done."),
            ],
            scenario,
        )

        await _invoke(graph, config)
        recorder.assert_called("create_order")

        # The tool message in the graph contains the resolved mock output
        # Verify via recorder that the call was mocked
        assert recorder.calls[0].was_mocked is True


# -- 5. Call Recording --------------------------------------------------------


class TestCallRecordingE2E:
    """Verify CallRecorder captures everything through a real graph."""

    async def test_multi_tool_recording(self):
        registry = MockToolsRegistry()
        recorder = CallRecorder()
        registry.mock("get_customer").returns({"id": "C1", "name": "Acme"})
        registry.mock("list_items").returns({"items": [{"id": "I1"}]})
        registry.mock("create_order").returns({"order_id": "ORD-1"})

        graph, config = _run_graph(
            registry,
            recorder,
            [
                make_tool_call("get_customer", {"customer_id": "C1"}),
                make_tool_call("list_items", {"category": "widgets"}),
                make_tool_call("create_order", {"customer_id": "C1", "item_id": "I1", "quantity": 2}),
                make_final_response("Order placed."),
            ],
            {"scenario_id": "recording-test"},
        )

        await _invoke(graph, config)

        # Verify all assertions
        recorder.assert_called("get_customer")
        recorder.assert_called("list_items")
        recorder.assert_called("create_order")
        recorder.assert_not_called("delete_order")
        recorder.assert_call_order("get_customer", "list_items", "create_order")
        recorder.assert_called_with("get_customer", customer_id="C1")
        recorder.assert_called_once("create_order")
        assert len(recorder.calls) == 3
        assert all(c.was_mocked for c in recorder.calls)


# -- 6. Signature Validation --------------------------------------------------


class TestSignatureValidationE2E:
    """Verify signature validation passes for properly-typed mock factories."""

    async def test_valid_signature_passes(self):
        registry = MockToolsRegistry()
        recorder = CallRecorder()

        # Use a proper two-phase factory with explicit signature matching the tool
        def get_customer_factory(scenario_metadata: dict, config: dict = None):
            def mock_impl(customer_id: str) -> dict:
                return {"id": customer_id}
            return mock_impl

        registry.register("get_customer", mock_fn=get_customer_factory)

        # Should not raise -- get_customer(customer_id: str) matches mock_impl(customer_id: str)
        wrapper = create_mockable_tool_wrapper(
            registry, recorder=recorder, tools=E2E_TOOLS, validate_signatures=True
        )
        graph = build_e2e_graph(
            [make_tool_call("get_customer", {"customer_id": "C1"}), make_final_response("OK")],
            wrapper,
        )
        config = inject_scenario_metadata({}, {"scenario_id": "valid-sig"})
        await _invoke(graph, config)
        recorder.assert_called("get_customer")


# -- 7. Custom Mock Factory ---------------------------------------------------


class TestCustomMockFactoryE2E:
    """Verify registry.register(mock_fn=...) two-phase factory through a real graph."""

    async def test_factory_reads_scenario_metadata(self):
        registry = MockToolsRegistry()
        recorder = CallRecorder()

        def tier_factory(scenario_metadata: dict, config: dict = None):
            tier = scenario_metadata.get("customer_tier", "standard")
            return lambda customer_id: {"id": customer_id, "tier": tier}

        registry.register("get_customer", mock_fn=tier_factory)

        graph, config = _run_graph(
            registry,
            recorder,
            [
                make_tool_call("get_customer", {"customer_id": "C1"}),
                make_final_response("Done."),
            ],
            {"scenario_id": "factory-test", "customer_tier": "enterprise"},
        )

        await _invoke(graph, config)
        recorder.assert_called("get_customer")

    async def test_factory_branches_on_metadata_flag(self):
        registry = MockToolsRegistry()
        recorder = CallRecorder()

        def maintenance_factory(scenario_metadata: dict, config: dict = None):
            if scenario_metadata.get("maintenance_mode"):
                return lambda **kw: {"error": "system_maintenance"}
            return lambda **kw: {"items": [{"id": "I1"}]}

        registry.register("list_items", mock_fn=maintenance_factory)

        graph, config = _run_graph(
            registry,
            recorder,
            [
                make_tool_call("list_items", {"status": "active"}),
                make_final_response("Maintenance."),
            ],
            {"scenario_id": "maintenance-test", "maintenance_mode": True},
        )

        await _invoke(graph, config)
        recorder.assert_called("list_items")

    async def test_async_factory_resolves_through_toolnode(self):
        registry = MockToolsRegistry()
        recorder = CallRecorder()

        async def async_customer_factory(scenario_metadata: dict, config: dict = None):
            return lambda customer_id: {
                "id": customer_id,
                "tier": scenario_metadata["customer_tier"],
            }

        registry.register("get_customer", mock_fn=async_customer_factory)

        graph, config = _run_graph(
            registry,
            recorder,
            [
                make_tool_call("get_customer", {"customer_id": "C1"}),
                make_final_response("Done."),
            ],
            {"scenario_id": "async-factory-test", "customer_tier": "enterprise"},
        )

        result = await _invoke(graph, config)

        recorder.assert_called_with("get_customer", customer_id="C1")
        assert recorder.calls[0].was_mocked is True
        assert recorder.calls[0].result == {"id": "C1", "tier": "enterprise"}
        assert result["messages"][-1].content == "Done."

    async def test_sync_and_async_factories_can_share_registry(self):
        registry = MockToolsRegistry()
        recorder = CallRecorder()

        registry.register(
            "get_customer",
            mock_fn=lambda scenario_metadata, config=None: lambda customer_id: {
                "id": customer_id,
                "tier": scenario_metadata["customer_tier"],
            },
        )

        async def async_items_factory(scenario_metadata: dict, config: dict = None):
            return lambda status="": {
                "items": [{"id": "I1", "status": status}],
                "source": scenario_metadata["source"],
            }

        registry.register("list_items", mock_fn=async_items_factory)

        graph, config = _run_graph(
            registry,
            recorder,
            [
                make_tool_call("get_customer", {"customer_id": "C1"}, call_id="call_customer"),
                make_tool_call("list_items", {"status": "active"}, call_id="call_items"),
                make_final_response("Done."),
            ],
            {"scenario_id": "mixed-factory-test", "customer_tier": "gold", "source": "async"},
        )

        result = await _invoke(graph, config)

        assert [call.tool_name for call in recorder.calls] == ["get_customer", "list_items"]
        assert all(call.was_mocked for call in recorder.calls)
        assert recorder.calls[0].result == {"id": "C1", "tier": "gold"}
        assert recorder.calls[1].result == {
            "items": [{"id": "I1", "status": "active"}],
            "source": "async",
        }
        assert result["messages"][-1].content == "Done."


# -- 8. Mock vs Real Toggle ---------------------------------------------------


class TestMockVsRealToggleE2E:
    """Verify same graph uses mocks when metadata present, real tools when absent."""

    async def test_with_metadata_uses_mock(self):
        registry = MockToolsRegistry()
        recorder = CallRecorder()
        registry.mock("get_customer").returns({"id": "C1", "name": "Mocked"})

        graph, config = _run_graph(
            registry,
            recorder,
            [
                make_tool_call("get_customer", {"customer_id": "C1"}),
                make_final_response("Got mocked customer."),
            ],
            {"scenario_id": "toggle-mock"},
        )

        await _invoke(graph, config)
        recorder.assert_called("get_customer")
        assert recorder.calls[0].was_mocked is True

    async def test_without_metadata_calls_real_tool(self):
        registry = MockToolsRegistry()
        recorder = CallRecorder()
        registry.mock("get_customer").returns({"id": "C1", "name": "Mocked"})

        wrapper = create_mockable_tool_wrapper(registry, recorder=recorder)
        graph = build_e2e_graph(
            [make_tool_call("get_customer", {"customer_id": "C1"}), make_final_response("Done.")],
            wrapper,
        )
        # No inject_scenario_metadata -- plain config
        config = {}

        # Real tool raises NotImplementedError. The wrapper re-raises it (no scenario_metadata path),
        # and the default ToolNode error handler also re-raises NotImplementedError.
        # So we expect the error to propagate.
        with pytest.raises(NotImplementedError, match="Real API"):
            await graph.ainvoke(
                {"messages": [HumanMessage(content="test")]},
                config=config,
            )

        # Tool was called but NOT mocked (no scenario metadata)
        assert len(recorder.calls) == 1
        assert recorder.calls[0].was_mocked is False
