"""Tests for reproducible placeholders: a fixed clock and seeded random streams.

The graph tests run a real compiled graph with one shared registry. Hand-built
requests would miss how LangGraph scopes config: checkpoint_ns, for one, changes
on every tools step.
"""

from __future__ import annotations

import asyncio
import json
import operator
import random
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta, timezone
from typing import Annotated, Any, TypedDict

import pytest
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from stuntdouble import scenario_mocking
from stuntdouble.exceptions import MockFactoryError
from stuntdouble.mock_registry import MockToolsRegistry
from stuntdouble.resolving import ResolverContext, ValueResolver, resolve_output
from stuntdouble.scenario_mocking import DataDrivenMockFactory
from stuntdouble.wrapper import create_mockable_tool_wrapper

SEEDED_OUTPUT = {"id": "{{uuid}}", "n": "{{random_int(0, 1000000000)}}", "s": "{{random_string(16)}}"}


def _scenario(tool_names: Sequence[str] = ("create_invoice",), **settings: Any) -> dict[str, Any]:
    return {
        "scenario_id": "reproducible",
        "stuntdouble": settings,
        "mocks": {name: [{"output": SEEDED_OUTPUT}] for name in tool_names},
    }


def _config(thread_id: str | None = "thread-1", invocation_id: str | None = None) -> dict[str, Any]:
    configurable: dict[str, Any] = {}
    if thread_id is not None:
        configurable["thread_id"] = thread_id
    if invocation_id is not None:
        configurable["invocation_id"] = invocation_id
    return {"configurable": configurable}


class TestResolverRng:
    def test_same_seed_replays_every_generator(self):
        template = {**SEEDED_OUTPUT, "f": "{{random_float(0, 1000)}}", "c": "{{choice('a', 'b', 'c', 'd')}}"}
        first = resolve_output(template, rng=random.Random(7))
        assert first == resolve_output(template, rng=random.Random(7))
        assert first != resolve_output(template, rng=random.Random(8))

    def test_seeded_uuid_is_a_valid_v4(self):
        value = uuid.UUID(resolve_output("{{uuid}}", rng=random.Random(1)))
        assert value.version == 4

    def test_seeded_resolution_leaves_global_random_untouched(self):
        random.seed(123)
        state = random.getstate()
        resolve_output(SEEDED_OUTPUT, rng=random.Random(1))
        assert random.getstate() == state

    def test_shared_rng_advances_across_calls(self):
        rng = random.Random(1)
        assert resolve_output("{{uuid}}", rng=rng) != resolve_output("{{uuid}}", rng=rng)

    def test_without_rng_uses_global_random(self):
        random.seed(5)
        first = resolve_output("{{random_int(0, 1000000)}}")
        random.seed(5)
        assert resolve_output("{{random_int(0, 1000000)}}") == first


class TestResolverClock:
    def test_resolve_output_accepts_base_time(self):
        base = datetime(2026, 1, 15, 10, 0, tzinfo=UTC)
        assert resolve_output("{{now - 1d}}", base_time=base) == "2026-01-14T10:00:00+00:00"

    def test_now_utc_converts_aware_base_time(self):
        base = datetime(2026, 1, 15, 3, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
        assert resolve_output("{{now_utc}}", base_time=base) == "2026-01-14T21:30:00+00:00"

    def test_now_utc_supports_offsets(self):
        base = datetime(2026, 1, 15, 10, 0, tzinfo=UTC)
        assert resolve_output("{{now_utc + 2h}}", base_time=base) == "2026-01-15T12:00:00+00:00"

    def test_now_utc_without_base_time_is_aware(self):
        value = datetime.fromisoformat(resolve_output("{{now_utc}}"))
        assert value.utcoffset() == timedelta(0)

    def test_default_now_stays_naive(self):
        context = ResolverContext()
        assert datetime.fromisoformat(ValueResolver().resolve_dynamic_values("{{now}}", context)).tzinfo is None


class TestFactoryScenarioSettings:
    def test_base_time_string_with_z_suffix(self):
        factory = DataDrivenMockFactory("t")
        scenario = {
            "stuntdouble": {"base_time": "2026-01-15T10:00:00Z"},
            "mocks": {"t": [{"output": {"at": "{{now}}", "day": "{{today}}"}}]},
        }
        assert factory(scenario)() == {"at": "2026-01-15T10:00:00+00:00", "day": "2026-01-15"}

    def test_offset_base_time_is_normalized_to_utc(self):
        factory = DataDrivenMockFactory("t")
        scenario = {
            "stuntdouble": {"base_time": "2026-01-15T03:00:00+05:30"},
            "mocks": {"t": [{"output": "{{today}}"}]},
        }
        assert factory(scenario)() == "2026-01-14"

    def test_naive_base_time_is_read_as_utc(self):
        factory = DataDrivenMockFactory("t")
        scenario = {
            "stuntdouble": {"base_time": datetime(2026, 1, 15, 10, 0)},
            "mocks": {"t": [{"output": "{{now}}"}]},
        }
        assert factory(scenario)() == "2026-01-15T10:00:00+00:00"

    @pytest.mark.parametrize("base_time", ["not-a-time", 1736935200])
    def test_invalid_base_time_is_rejected(self, base_time):
        with pytest.raises(ValueError, match="base_time"):
            DataDrivenMockFactory("t")({"stuntdouble": {"base_time": base_time}, "mocks": {"t": []}})

    @pytest.mark.parametrize("seed", [True, 1.5, ["a"]])
    def test_invalid_seed_is_rejected(self, seed):
        with pytest.raises(ValueError, match="seed"):
            DataDrivenMockFactory("t")({"stuntdouble": {"seed": seed}, "mocks": {"t": []}})

    def test_seed_zero_is_honored(self):
        factory = DataDrivenMockFactory("create_invoice")
        assert factory(_scenario(seed=0))() == factory(_scenario(seed=0))()

    def test_tools_with_the_same_seed_get_different_streams(self):
        scenario = _scenario(("a", "b"), seed=1)
        assert DataDrivenMockFactory("a")(scenario)() != DataDrivenMockFactory("b")(scenario)()


class TestFactoryDirectCalls:
    def test_resolved_callable_advances_and_a_new_resolve_restarts(self):
        factory = DataDrivenMockFactory("create_invoice")
        mock = factory(_scenario(seed=1))
        first, second = mock(), mock()
        assert first != second
        replay = factory(_scenario(seed=1))
        assert [replay(), replay()] == [first, second]

    def test_direct_calls_keep_no_run_state(self):
        factory = DataDrivenMockFactory("create_invoice")
        factory(_scenario(seed=1))()
        assert not factory._run_streams


class TestRunScope:
    def test_seed_without_run_identifier_is_an_error(self):
        with pytest.raises(ValueError, match="thread_id"):
            DataDrivenMockFactory("create_invoice")(_scenario(seed=1), _config(thread_id=None))

    def test_invocation_id_alone_identifies_a_run(self):
        factory = DataDrivenMockFactory("create_invoice")
        config = _config(thread_id=None, invocation_id="i")
        assert factory(_scenario(seed=1), config)() != factory(_scenario(seed=1), config)()

    def test_unseeded_scenarios_need_no_identifier_and_keep_no_state(self):
        factory = DataDrivenMockFactory("create_invoice")
        assert factory(_scenario(), _config(thread_id=None))()
        assert not factory._run_streams

    def test_changing_the_seed_on_a_run_starts_that_seeds_stream(self):
        factory = DataDrivenMockFactory("create_invoice")
        config = _config()
        factory(_scenario(seed=1), config)()
        assert factory(_scenario(seed=2), config)() == factory(_scenario(seed=2))()

    def test_reset_forgets_one_run(self):
        factory = DataDrivenMockFactory("create_invoice")
        first = factory(_scenario(seed=1), _config("a"))()
        kept = factory(_scenario(seed=1), _config("b"))()
        factory.reset_run_state(_config("a"))
        assert factory(_scenario(seed=1), _config("a"))() == first
        assert factory(_scenario(seed=1), _config("b"))() != kept

    def test_reset_without_config_forgets_every_run(self):
        factory = DataDrivenMockFactory("create_invoice")
        first = factory(_scenario(seed=1), _config("a"))()
        factory.reset_run_state()
        assert factory(_scenario(seed=1), _config("a"))() == first

    def test_reset_tolerates_a_registration_during_the_sweep(self):
        registry = MockToolsRegistry()

        class RegistersDuringReset:
            def __call__(self, scenario_metadata, config=None):
                return None

            def reset_run_state(self, config=None):
                registry.register("late_tool", mock_fn=self)

        registry.register("first_tool", mock_fn=RegistersDuringReset())

        registry.reset_run_state()

        assert registry.is_registered("late_tool")

    def test_recent_runs_are_kept_past_the_limit(self, monkeypatch):
        monkeypatch.setattr(scenario_mocking, "_MAX_RUN_STREAMS", 2)
        factory = DataDrivenMockFactory("create_invoice")
        first = factory(_scenario(seed=1), _config("active"))()
        for name in ("b", "c", "d"):
            factory(_scenario(seed=1), _config(name))()
        assert factory(_scenario(seed=1), _config("active"))() != first

    def test_idle_runs_are_dropped_past_the_limit(self, monkeypatch):
        monkeypatch.setattr(scenario_mocking, "_MAX_RUN_STREAMS", 2)
        clock = [0.0]
        monkeypatch.setattr(scenario_mocking.time, "monotonic", lambda: clock[0])
        factory = DataDrivenMockFactory("create_invoice")
        factory(_scenario(seed=1), _config("idle"))()
        clock[0] = scenario_mocking._STREAM_IDLE_SECONDS
        factory(_scenario(seed=1), _config("b"))()
        factory(_scenario(seed=1), _config("c"))()
        assert len(factory._run_streams) == 2
        assert ("idle", None) not in factory._run_streams


class _State(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    step: int


@tool
def create_invoice(amount: int = 0) -> str:
    """Real tool, replaced by the mock."""
    raise AssertionError("mocked in these tests")


@tool
def create_refund(amount: int = 0) -> str:
    """Real tool, replaced by the mock."""
    raise AssertionError("mocked in these tests")


def _build_graph(wrapper: Any, steps: list[list[str]], *, checkpointer: Any | None = None) -> Any:
    """Compile an agent that makes the given tool calls, one list per tools step."""

    async def agent(state: _State) -> dict[str, Any]:
        await asyncio.sleep(0)  # let concurrent runs interleave
        step = state.get("step", 0)
        if step >= len(steps):
            return {"messages": [AIMessage(content="done")], "step": step}
        calls = [
            {"name": name, "args": {"amount": 1}, "id": f"call-{step}-{index}"}
            for index, name in enumerate(steps[step])
        ]
        return {"messages": [AIMessage(content="", tool_calls=calls)], "step": step + 1}

    def route(state: _State) -> str:
        return "tools" if state["messages"][-1].tool_calls else END

    builder = StateGraph(_State)
    builder.add_node("agent", agent)
    builder.add_node("tools", ToolNode([create_invoice, create_refund], awrap_tool_call=wrapper))
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", route)
    builder.add_edge("tools", "agent")
    return builder.compile(checkpointer=checkpointer if checkpointer is not None else MemorySaver())


def _registry() -> MockToolsRegistry:
    registry = MockToolsRegistry()
    registry.register_data_driven("create_invoice")
    registry.register_data_driven("create_refund")
    return registry


async def _run(
    graph: Any,
    scenario: dict[str, Any],
    thread_id: str | None = "thread-1",
    invocation_id: str | None = None,
) -> list[tuple[str, str]]:
    config = _config(thread_id, invocation_id)
    config["configurable"]["scenario_metadata"] = scenario
    state = await graph.ainvoke({"messages": [], "step": 0}, config)
    return [(m.name, m.content) for m in state["messages"] if isinstance(m, ToolMessage)]


def _values(messages: list[tuple[str, str]], tool_name: str) -> list[str]:
    return [content for name, content in messages if name == tool_name]


THREE_STEPS = [["create_invoice"], ["create_invoice"], ["create_invoice"]]


class TestThroughGraph:
    @pytest.mark.asyncio
    async def test_stream_advances_across_tools_steps(self):
        graph = _build_graph(create_mockable_tool_wrapper(_registry()), THREE_STEPS)
        values = _values(await _run(graph, _scenario(seed=1)), "create_invoice")
        assert len(set(values)) == 3

    @pytest.mark.asyncio
    async def test_fresh_run_with_the_same_seed_reproduces(self):
        graph = _build_graph(create_mockable_tool_wrapper(_registry()), THREE_STEPS)
        first = await _run(graph, _scenario(seed=1), "run-a")
        assert await _run(graph, _scenario(seed=1), "run-b") == first

    @pytest.mark.asyncio
    async def test_concurrent_runs_do_not_consume_each_others_stream(self):
        graph = _build_graph(create_mockable_tool_wrapper(_registry()), THREE_STEPS)
        expected = await _run(graph, _scenario(seed=1), "alone")
        runs = await asyncio.gather(*(_run(graph, _scenario(seed=1), f"run-{i}") for i in range(8)))
        assert all(run == expected for run in runs)

    @pytest.mark.asyncio
    async def test_repeated_thread_continues_the_stream(self):
        graph = _build_graph(create_mockable_tool_wrapper(_registry()), THREE_STEPS)
        first = await _run(graph, _scenario(seed=1))
        # A reused thread accumulates messages, so compare the three new results.
        second = (await _run(graph, _scenario(seed=1)))[3:]
        assert second and not set(_values(first, "create_invoice")) & set(_values(second, "create_invoice"))

    @pytest.mark.asyncio
    async def test_new_invocation_id_on_a_thread_replays(self):
        graph = _build_graph(create_mockable_tool_wrapper(_registry()), THREE_STEPS)
        first = await _run(graph, _scenario(seed=1), invocation_id="first")
        second = await _run(graph, _scenario(seed=1), invocation_id="second")
        assert second[3:] == first

    @pytest.mark.asyncio
    async def test_registry_reset_replays_every_tool(self):
        registry = _registry()
        graph = _build_graph(create_mockable_tool_wrapper(registry), [["create_invoice"], ["create_refund"]])
        scenario = _scenario(("create_invoice", "create_refund"), seed=1)
        first = await _run(graph, scenario)
        registry.reset_run_state(_config())
        second = (await _run(graph, scenario))[2:]
        assert second == first

    @pytest.mark.asyncio
    async def test_parallel_calls_to_different_tools_ignore_call_order(self):
        names = ("create_invoice", "create_refund")
        graph = _build_graph(create_mockable_tool_wrapper(_registry()), [list(names)])
        reversed_graph = _build_graph(create_mockable_tool_wrapper(_registry()), [list(reversed(names))])
        scenario = _scenario(names, seed=1)
        assert sorted(await _run(graph, scenario)) == sorted(await _run(reversed_graph, scenario))

    @pytest.mark.asyncio
    async def test_parallel_calls_to_one_tool_each_draw_new_values(self):
        graph = _build_graph(create_mockable_tool_wrapper(_registry()), [["create_invoice", "create_invoice"]])
        values = _values(await _run(graph, _scenario(seed=1)), "create_invoice")
        assert len(set(values)) == 2

    @pytest.mark.asyncio
    async def test_missing_identifier_is_reported_as_a_mock_error(self):
        graph = _build_graph(create_mockable_tool_wrapper(_registry()), [["create_invoice"]], checkpointer=False)
        [(_, content)] = await _run(graph, _scenario(seed=1), thread_id=None, invocation_id=None)
        assert "thread_id" in content

    @pytest.mark.asyncio
    async def test_missing_identifier_raises_in_strict_mode(self):
        wrapper = create_mockable_tool_wrapper(_registry(), strict_mock_errors=True)
        graph = _build_graph(wrapper, [["create_invoice"]], checkpointer=False)
        with pytest.raises(MockFactoryError):
            await _run(graph, _scenario(seed=1), thread_id=None)

    @pytest.mark.asyncio
    async def test_fixed_clock_applies_to_every_wrapped_call(self):
        registry = _registry()
        graph = _build_graph(create_mockable_tool_wrapper(registry), THREE_STEPS[:2])
        scenario = {
            "stuntdouble": {"base_time": "2026-01-15T10:00:00Z"},
            "mocks": {"create_invoice": [{"output": {"at": "{{now}}", "due": "{{now + 7d}}"}}]},
        }
        values = _values(await _run(graph, scenario), "create_invoice")
        assert [json.loads(value) for value in values] == [
            {"at": "2026-01-15T10:00:00+00:00", "due": "2026-01-22T10:00:00+00:00"}
        ] * 2

    @pytest.mark.asyncio
    async def test_invocation_id_scopes_a_graph_without_a_checkpointer(self):
        graph = _build_graph(create_mockable_tool_wrapper(_registry()), THREE_STEPS, checkpointer=False)
        first = await _run(graph, _scenario(seed=1), thread_id=None, invocation_id="a")
        assert len(set(_values(first, "create_invoice"))) == 3
        assert await _run(graph, _scenario(seed=1), thread_id=None, invocation_id="b") == first

    @pytest.mark.asyncio
    async def test_unconfigured_scenarios_stay_unseeded_without_a_thread(self):
        graph = _build_graph(create_mockable_tool_wrapper(_registry()), THREE_STEPS, checkpointer=False)
        scenario = _scenario()
        del scenario["stuntdouble"]
        values = _values(await _run(graph, scenario, thread_id=None), "create_invoice")
        assert len(set(values)) == 3 and all(json.loads(value)["id"] for value in values)
