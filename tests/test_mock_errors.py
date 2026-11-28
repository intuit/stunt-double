"""Tests for mocks configured to raise: data-driven "error" cases and MockBuilder.raises()."""

from __future__ import annotations

import asyncio
import logging
import operator
from typing import Annotated, Any, TypedDict
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.prebuilt.tool_node import ToolCallRequest, ToolRuntime

from stuntdouble import (
    CallRecorder,
    DataDrivenMockFactory,
    InputNotMatchedError,
    MockToolError,
    MockToolsRegistry,
    create_mockable_tool_wrapper,
    validate_registry_mocks,
)
from stuntdouble.exceptions import CONFIGURED_ERROR_TYPES, MockFactoryError, is_configured_error

PROCESS_CONTROL = ["SystemExit", "KeyboardInterrupt", "GeneratorExit", "BaseException"]
UNSUPPORTED = [*PROCESS_CONTROL, "NoSuchError", "os.system", "Exception", "MockFactoryError"]


def _mock(cases: Any, tool_name: str = "charge_card") -> Any:
    mock = DataDrivenMockFactory(tool_name)({"mocks": {tool_name: cases}})
    assert mock is not None
    return mock


def _request(tool_name: str, args: dict[str, Any], scenario: dict[str, Any]) -> ToolCallRequest:
    tool_obj = MagicMock()
    tool_obj.name = tool_name
    runtime = ToolRuntime(
        state={},
        context=None,
        config={"configurable": {"scenario_metadata": scenario}},
        stream_writer=None,
        tool_call_id=None,
        store=None,
    )
    return ToolCallRequest(
        tool_call={"name": tool_name, "args": args, "id": "call-1"},
        tool=tool_obj,
        state={},
        runtime=runtime,
    )


async def _never_execute(request: ToolCallRequest) -> ToolMessage:
    raise AssertionError("the real tool must not run")


def _call(registry: MockToolsRegistry, args: dict[str, Any], scenario: dict[str, Any] | None = None, **kwargs: Any):
    wrapper = create_mockable_tool_wrapper(registry, **kwargs)
    request = _request("charge_card", args, scenario or {"scenario_id": "s"})
    return asyncio.run(wrapper(request, _never_execute))


def _data_driven(cases: Any) -> tuple[MockToolsRegistry, dict[str, Any]]:
    registry = MockToolsRegistry()
    registry.register_data_driven("charge_card")
    return registry, {"scenario_id": "s", "mocks": {"charge_card": cases}}


class TestDataDrivenErrorCases:
    def test_string_error_raises_mock_tool_error(self):
        mock = _mock([{"error": "Card declined"}])
        with pytest.raises(MockToolError, match="^Card declined$") as info:
            mock(amount=5)
        assert is_configured_error(info.value)

    @pytest.mark.parametrize("type_name", sorted(CONFIGURED_ERROR_TYPES))
    def test_each_supported_type_is_raised(self, type_name):
        mock = _mock([{"error": {"type": type_name, "message": "Amount exceeds limit"}}])
        with pytest.raises(Exception) as info:
            mock(amount=5)
        assert type(info.value) is CONFIGURED_ERROR_TYPES[type_name]
        assert info.value.args == ("Amount exceeds limit",)
        assert is_configured_error(info.value)

    def test_dict_without_type_raises_mock_tool_error(self):
        with pytest.raises(MockToolError, match="Card declined"):
            _mock([{"error": {"message": "Card declined"}}])(amount=5)

    @pytest.mark.parametrize("type_name", UNSUPPORTED)
    def test_unsupported_type_falls_back_to_mock_tool_error(self, type_name, caplog):
        with caplog.at_level(logging.WARNING, logger="stuntdouble.scenario_mocking"):
            mock = _mock([{"error": {"type": type_name, "message": "boom"}}])
        assert f"error type {type_name!r} is not supported" in caplog.text
        with pytest.raises(MockToolError, match="^boom$") as info:
            mock(amount=5)
        assert type(info.value) is MockToolError

    @pytest.mark.parametrize("type_name", PROCESS_CONTROL)
    def test_process_control_types_are_never_raised(self, type_name):
        with pytest.raises(Exception) as info:
            _mock([{"error": {"type": type_name, "message": "stop"}}])(amount=5)
        assert type(info.value) is MockToolError

    def test_message_placeholders_are_resolved(self):
        mock = DataDrivenMockFactory("charge_card")(
            {"mocks": {"charge_card": [{"error": "Card {{input.card}} declined for {{config.user}}"}]}},
            {"configurable": {"user": "U-1"}},
        )
        with pytest.raises(MockToolError, match="^Card 4000 declined for U-1$"):
            mock(card="4000")

    @pytest.mark.parametrize("payload", [{"error": "down"}, {"error": "down", "status": 503}])
    def test_bare_error_shaped_payload_is_still_output(self, payload):
        assert _mock(payload)() == payload

    def test_bare_case_with_input_can_raise(self):
        with pytest.raises(MockToolError, match="boom"):
            _mock({"input": {"amount": 1}, "error": "boom"})(amount=1)

    def test_output_and_error_in_one_case_is_rejected_at_resolve(self):
        with pytest.raises(ValueError, match="Mock case 1 for tool 'charge_card' has both 'output' and 'error'"):
            _mock([{"output": {"ok": True}, "input": {"x": 1}}, {"output": {"ok": True}, "error": "boom"}])

    @pytest.mark.parametrize(
        ("spec", "message"),
        [
            (42, "'error' must be a message string or a {type, message} dict"),
            (["boom"], "'error' must be a message string or a {type, message} dict"),
            ({"type": "ValueError"}, "'error' dict needs a 'message'"),
            ({"type": "ValueError", "message": "x", "code": 503}, "unknown 'error' keys \\['code'\\]"),
            ({"type": ValueError, "message": "x"}, "'error.type' must be a string"),
        ],
    )
    def test_malformed_error_is_rejected_at_resolve(self, spec, message):
        with pytest.raises(ValueError, match=message):
            _mock([{"error": spec}])


class TestErrorCaseMatching:
    CASES = [
        {"input": {"amount": {"$gt": 10000}}, "error": {"type": "ValueError", "message": "Amount exceeds limit"}},
        {"input": {"card": "4000-0000-0000-0002"}, "error": "Card declined"},
        {"output": {"ok": True}},
    ]

    def test_cases_are_tried_in_order(self):
        mock = _mock(self.CASES)
        with pytest.raises(ValueError, match="Amount exceeds limit"):
            mock(amount=20000, card="4000-0000-0000-0002")
        with pytest.raises(MockToolError, match="Card declined"):
            mock(amount=5, card="4000-0000-0000-0002")
        assert mock(amount=5, card="4242") == {"ok": True}

    def test_output_case_before_error_case_wins(self):
        mock = _mock([{"input": {"amount": 1}, "output": {"ok": True}}, {"error": "boom"}])
        assert mock(amount=1) == {"ok": True}
        with pytest.raises(MockToolError, match="boom"):
            mock(amount=2)

    def test_unmatched_error_case_without_catch_all_is_input_not_matched(self):
        mock = _mock([{"input": {"amount": 1}, "error": "boom"}])
        with pytest.raises(InputNotMatchedError):
            mock(amount=2)

    def test_unmatched_error_case_uses_fallback(self):
        mock = DataDrivenMockFactory("charge_card", fallback={"ok": False})(
            {"mocks": {"charge_card": [{"input": {"amount": 1}, "error": "boom"}]}}
        )
        assert mock(amount=2) == {"ok": False}


class TestBuilderRaises:
    def _registry(self) -> MockToolsRegistry:
        return MockToolsRegistry()

    def _resolve(self, registry: MockToolsRegistry) -> Any:
        mock = registry.resolve("charge_card", {"scenario_id": "s"})
        assert mock is not None
        return mock

    def test_message_raises_mock_tool_error(self):
        registry = self._registry()
        registry.mock("charge_card").raises("Card declined")
        with pytest.raises(MockToolError, match="^Card declined$") as info:
            self._resolve(registry)(amount=5)
        assert is_configured_error(info.value)

    @pytest.mark.parametrize("exc_type", sorted(CONFIGURED_ERROR_TYPES.values(), key=lambda t: t.__name__))
    def test_instance_of_each_supported_type(self, exc_type):
        registry = self._registry()
        registry.mock("charge_card").raises(exc_type("Amount exceeds limit"))
        with pytest.raises(exc_type) as info:
            self._resolve(registry)(amount=5)
        assert type(info.value) is exc_type
        assert info.value.args == ("Amount exceeds limit",)
        assert is_configured_error(info.value)

    def test_instance_is_raised_unchanged_on_every_call(self):
        class ToolFailedError(Exception):
            def __init__(self, name: str):
                super().__init__(f"{name} failed")

        registry = self._registry()
        original = ToolFailedError("card")
        registry.mock("charge_card").raises(original)
        mock = self._resolve(registry)
        depths = []
        for _ in range(3):
            with pytest.raises(ToolFailedError, match="^card failed$") as info:
                mock()
            assert info.value is original
            depths.append(len(info.traceback))
        assert len(set(depths)) == 1

    def test_class_that_needs_arguments_fails_at_registration(self):
        with pytest.raises(TypeError):
            self._registry().mock("charge_card").raises(UnicodeDecodeError)

    def test_rejects_the_no_match_signal(self):
        with pytest.raises(TypeError, match="cannot raise InputNotMatchedError"):
            self._registry().mock("charge_card").raises(InputNotMatchedError("charge_card"))

    def test_custom_exception_class(self):
        class PaymentError(Exception):
            pass

        registry = self._registry()
        registry.mock("charge_card").raises(PaymentError)
        with pytest.raises(PaymentError) as info:
            self._resolve(registry)()
        assert is_configured_error(info.value)

    @pytest.mark.parametrize("error", [SystemExit, KeyboardInterrupt(), GeneratorExit, BaseException("x"), 42, None])
    def test_rejects_non_exceptions_and_process_control(self, error):
        registry = self._registry()
        with pytest.raises(TypeError, match="raises\\(\\) takes a message"):
            registry.mock("charge_card").raises(error)
        assert registry.resolve("charge_card", {"scenario_id": "s"}) is None

    def test_when_conditions_are_checked_first(self):
        registry = self._registry()
        registry.mock("charge_card").when(amount={"$gt": 10000}).raises(ValueError("Amount exceeds limit"))
        mock = self._resolve(registry)
        with pytest.raises(ValueError, match="Amount exceeds limit"):
            mock(amount=20000)
        with pytest.raises(InputNotMatchedError):
            mock(amount=5)


class TestWrapperHandling:
    @pytest.mark.parametrize("kind", ["data_driven", "builder"])
    def test_non_strict_returns_the_message_without_prefix(self, kind):
        if kind == "data_driven":
            registry, scenario = _data_driven([{"error": {"type": "ValueError", "message": "Amount exceeds limit"}}])
        else:
            registry, scenario = MockToolsRegistry(), None
            registry.mock("charge_card").raises(ValueError("Amount exceeds limit"))
        result = _call(registry, {"amount": 20000}, scenario)
        assert isinstance(result, ToolMessage)
        assert result.status == "error"
        assert result.content == "Amount exceeds limit"
        assert result.name == "charge_card"
        assert result.tool_call_id == "call-1"

    @pytest.mark.parametrize("kind", ["data_driven", "builder"])
    def test_strict_reraises_the_configured_exception(self, kind):
        if kind == "data_driven":
            registry, scenario = _data_driven([{"error": "Card declined"}])
        else:
            registry, scenario = MockToolsRegistry(), None
            registry.mock("charge_card").raises("Card declined")
        with pytest.raises(MockToolError, match="^Card declined$"):
            _call(registry, {}, scenario, strict_mock_errors=True)

    def test_mock_tool_error_raised_by_a_hand_written_mock_counts_as_configured(self):
        registry = MockToolsRegistry()

        def charge_card(**kwargs: Any) -> Any:
            raise MockToolError("Card declined")

        registry.register("charge_card", mock_fn=lambda md: charge_card)
        assert _call(registry, {}).content == "Card declined"

    def test_recorder_records_the_configured_error(self):
        registry, scenario = _data_driven([{"error": "Card declined"}])
        recorder = CallRecorder()
        _call(registry, {"amount": 1}, scenario, recorder=recorder)
        record = recorder.get_calls("charge_card")[0]
        assert isinstance(record.error, MockToolError)
        assert record.was_mocked


class TestAccidentalFailuresKeepDiagnostics:
    """Errors from bugs in mock code keep the "Mock error: " prefix and never reach the real tool."""

    def test_builtin_error_from_a_hand_written_mock(self):
        registry = MockToolsRegistry()

        def charge_card(**kwargs: Any) -> Any:
            return {}["missing"]

        registry.register("charge_card", mock_fn=lambda md: charge_card)
        result = _call(registry, {})
        assert result.status == "error"
        assert result.content == "Mock error: 'missing'"

    def test_builtin_error_from_returns_fn(self):
        registry = MockToolsRegistry()
        registry.mock("charge_card").returns_fn(lambda amount: amount / 0)
        result = _call(registry, {"amount": 1})
        assert result.content == "Mock error: division by zero"
        with pytest.raises(ZeroDivisionError):
            _call(registry, {"amount": 1}, strict_mock_errors=True)

    def test_failing_factory(self):
        registry = MockToolsRegistry()

        def factory(md: dict[str, Any]) -> Any:
            raise ValueError("bad factory")

        registry.register("charge_card", mock_fn=factory)
        result = _call(registry, {})
        assert result.content.startswith("Mock error: Mock factory for tool 'charge_card' raised ValueError")

    def test_case_with_output_and_error(self):
        registry, scenario = _data_driven([{"output": {"ok": True}, "error": "boom"}])
        result = _call(registry, {}, scenario)
        assert result.status == "error"
        assert result.content.startswith("Mock error: Mock factory for tool 'charge_card' raised ValueError")
        assert "has both 'output' and 'error'" in result.content
        with pytest.raises(MockFactoryError):
            _call(registry, {}, scenario, strict_mock_errors=True)


def test_validate_registry_mocks_checks_error_case_inputs():
    @tool
    def charge_card(amount: int) -> dict:
        """Charge a card."""
        return {"ok": True}

    errors = validate_registry_mocks([charge_card], {"mocks": {"charge_card": {"input": {"cents": 1}, "error": "x"}}})
    assert "cents" in errors["charge_card"][0]


class _State(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    step: int


@tool
def charge_card(amount: int) -> dict:
    """Charge a card."""
    raise AssertionError("the real tool must not run")


def _graph(wrapper: Any) -> Any:
    async def agent(state: _State) -> dict[str, Any]:
        if state.get("step", 0):
            return {"messages": [AIMessage(content="done")], "step": 1}
        call = {"name": "charge_card", "args": {"amount": 20000}, "id": "call-1"}
        return {"messages": [AIMessage(content="", tool_calls=[call])], "step": 1}

    def route(state: _State) -> str:
        return "tools" if state["messages"][-1].tool_calls else END

    builder = StateGraph(_State)
    builder.add_node("agent", agent)
    builder.add_node("tools", ToolNode([charge_card], awrap_tool_call=wrapper))
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", route)
    builder.add_edge("tools", "agent")
    return builder.compile()


class TestInAGraph:
    SCENARIO = {
        "scenario_id": "declines",
        "mocks": {
            "charge_card": [
                {
                    "input": {"amount": {"$gt": 10000}},
                    "error": {"type": "ValueError", "message": "Amount exceeds limit"},
                },
                {"output": {"ok": True}},
            ]
        },
    }

    def _run(self, **wrapper_kwargs: Any) -> list[ToolMessage]:
        registry = MockToolsRegistry()
        registry.register_data_driven("charge_card")
        graph = _graph(create_mockable_tool_wrapper(registry, tools=[charge_card], **wrapper_kwargs))
        config = {"configurable": {"scenario_metadata": self.SCENARIO}}
        state = asyncio.run(graph.ainvoke({"messages": [], "step": 0}, config))
        return [m for m in state["messages"] if isinstance(m, ToolMessage)]

    def test_agent_receives_an_error_tool_message(self):
        (message,) = self._run()
        assert message.status == "error"
        assert message.content == "Amount exceeds limit"

    def test_strict_mode_raises_out_of_the_graph(self):
        with pytest.raises(ValueError, match="Amount exceeds limit"):
            self._run(strict_mock_errors=True)
