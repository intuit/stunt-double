"""
Data-driven mock factories for scenario_metadata-based mocking.

Provides a generic mock factory that reads mock cases from scenario_metadata
at runtime, eliminating the need for hand-written per-tool mock factories.

Each tool's mock data lives in scenario_metadata["mocks"][tool_name] as a list
of {input, output} cases. The factory handles input matching, placeholder
resolution, fallback values, and echo_input mode automatically.

Placeholders in outputs are resolved at call time:
- {{input.field}} references tool call arguments (kwargs)
- {{config.field}} references values from RunnableConfig
- {{now}}, {{uuid}}, etc. generate dynamic values

scenario_metadata["stuntdouble"] opts in to reproducible values:
- base_time freezes the clock for timestamp placeholders
- seed drives {{uuid}} and the random_* placeholders from a private stream

The stream's lifetime is set out in _run_key and DataDrivenMockFactory.__call__.
"""

from __future__ import annotations

import copy
import logging
import random
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from stuntdouble.exceptions import InputNotMatchedError
from stuntdouble.matching import InputMatcher
from stuntdouble.resolving import ResolverContext, ValueResolver

logger = logging.getLogger(__name__)

# Past this many runs, streams idle for _STREAM_IDLE_SECONDS are dropped. A newer
# stream may belong to a run still in progress, and dropping it would silently
# restart that run's values, so the limit is exceeded rather than enforced on them.
_MAX_RUN_STREAMS = 1024
_STREAM_IDLE_SECONDS = 3600.0


@dataclass
class _RunStream:
    """Random stream of one tool within one run."""

    seed: int | str
    rng: random.Random
    last_used: float


def _run_key(config: dict[str, Any] | None) -> tuple[str | None, str | None] | None:
    """Identify the run a tool call belongs to, or None if config names no run.

    The run is configurable["thread_id"] narrowed by an optional
    configurable["invocation_id"]. A thread is a conversation, so invocations
    reusing one continue its stream unless they set different invocation ids.
    scenario_id is not used: it names the mocks, and concurrent runs share it.
    checkpoint_ns is not used either: LangGraph changes it on every tools step.
    """
    configurable = (config or {}).get("configurable") or {}
    thread_id = configurable.get("thread_id")
    invocation_id = configurable.get("invocation_id")
    if thread_id is None and invocation_id is None:
        return None
    return (
        None if thread_id is None else str(thread_id),
        None if invocation_id is None else str(invocation_id),
    )


def _parse_base_time(value: Any) -> datetime | None:
    """Parse a scenario base_time to aware UTC, reading naive values as UTC.

    Local time is never assumed, so a frozen clock gives the same output on any
    machine.
    """
    if value is None:
        return None
    parsed: datetime
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as e:
            raise ValueError(f"Invalid stuntdouble.base_time {value!r}: expected an ISO 8601 timestamp") from e
    else:
        raise ValueError(f"Invalid stuntdouble.base_time {value!r}: expected an ISO 8601 string or datetime")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _extract_config_data(config: dict[str, Any] | None) -> dict[str, Any]:
    """
    Extract a flat dict of values from RunnableConfig for placeholder resolution.

    Merges configurable["config_data"] (explicit) and configurable (implicit)
    so that {{config.field}} can reference either source.
    """
    if not config:
        return {}
    configurable = config.get("configurable", {})
    # Explicit config_data takes precedence over raw configurable keys
    data: dict[str, Any] = dict(configurable)
    data.update(configurable.get("config_data", {}))
    return data


class DataDrivenMockFactory:
    """
    Mock factory that reads cases from scenario_metadata at runtime.

    Designed to replace hand-written mock factories. Each instance is bound
    to a single tool_name and, when called with scenario_metadata (and
    optionally RunnableConfig), returns a mock callable that matches inputs
    and resolves outputs.

    Args:
        tool_name: Name of the tool (key in scenario_metadata["mocks"])
        fallback: Value returned when no case matches. If None and no match,
                  raises InputNotMatchedError (add a catch-all case or set
                  fallback=).
        echo_input: If True, the mock callable returns the input kwargs as-is
                    when no cases match. Useful for passthrough tools.

    Example:
        >>> factory = DataDrivenMockFactory("get_weather", fallback={"temp": 0})
        >>> scenario = {"mocks": {"get_weather": [
        ...     {"input": {"city": "NYC"}, "output": {"temp": 72}},
        ...     {"output": {"temp": 65}}  # catch-all
        ... ]}}
        >>> mock_fn = factory(scenario)
        >>> mock_fn(city="NYC")
        {'temp': 72}

    With config placeholders:
        >>> scenario = {"mocks": {"get_user": [
        ...     {"output": {"user": "{{config.user_id}}", "ts": "{{now}}"}}
        ... ]}}
        >>> config = {"configurable": {"user_id": "U-123"}}
        >>> mock_fn = factory(scenario, config)
        >>> mock_fn()
        {'user': 'U-123', 'ts': '2025-...'}
    """

    def __init__(
        self,
        tool_name: str,
        fallback: Any = None,
        echo_input: bool = False,
    ) -> None:
        self.tool_name = tool_name
        self.fallback = fallback
        self.echo_input = echo_input
        self._matcher = InputMatcher()
        self._resolver = ValueResolver()
        # resolve() calls this factory on every tool call, so streams outlive the
        # resolved callable. Streams are per factory, hence per tool: parallel
        # calls to different tools cannot change each other's values.
        self._run_streams: OrderedDict[tuple[str | None, str | None], _RunStream] = OrderedDict()
        self._run_streams_lock = threading.Lock()

    def _new_rng(self, seed: int | str) -> random.Random:
        """Create the stream for a seed, distinct per tool. String seeds hash stably."""
        return random.Random(f"{seed}:{self.tool_name}")

    def _rng_for_call(self, seed: Any, config: dict[str, Any] | None) -> random.Random | None:
        """Return the stream a resolved mock draws from, or None when not seeded."""
        if seed is None:
            return None
        if isinstance(seed, bool) or not isinstance(seed, (int, str)):
            raise ValueError(f"Invalid stuntdouble.seed {seed!r}: expected an int or str")
        if config is None:
            # Direct call: the resolved callable is the run, like sequence counters.
            return self._new_rng(seed)

        run_key = _run_key(config)
        if run_key is None:
            # Falling back to a shared or per-call stream would look seeded while
            # being neither repeatable nor isolated.
            raise ValueError(
                f"stuntdouble.seed needs a run identifier for tool '{self.tool_name}': set "
                f'config["configurable"]["thread_id"] or ["invocation_id"].'
            )

        now = time.monotonic()
        with self._run_streams_lock:
            stream = self._run_streams.get(run_key)
            if stream is None or stream.seed != seed:
                stream = _RunStream(seed, self._new_rng(seed), now)
                self._run_streams[run_key] = stream
            stream.last_used = now
            self._run_streams.move_to_end(run_key)
            while len(self._run_streams) > _MAX_RUN_STREAMS:
                oldest_key, oldest = next(iter(self._run_streams.items()))
                if now - oldest.last_used < _STREAM_IDLE_SECONDS:
                    break
                del self._run_streams[oldest_key]
            return stream.rng

    def reset_run_state(self, config: dict[str, Any] | None = None) -> None:
        """Forget this tool's seeded stream for one run, or for all runs if config is None.

        The next call in a reset run replays the stream from the start. Use
        MockToolsRegistry.reset_run_state to reset every tool at once.

        Args:
            config: The RunnableConfig identifying the run.
        """
        with self._run_streams_lock:
            if config is None:
                self._run_streams.clear()
                return
            run_key = _run_key(config)
            if run_key is not None:
                self._run_streams.pop(run_key, None)

    def __call__(
        self,
        scenario_metadata: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> Callable[..., Any] | None:
        """
        Create a mock callable from scenario_metadata.

        Args:
            scenario_metadata: Scenario data containing mock cases.
            config: Optional RunnableConfig for {{config.*}} placeholders.

        Returns None if scenario_metadata has no mock data for this tool,
        signaling the registry to skip mocking and call the real tool.

        scenario_metadata["stuntdouble"] may set base_time (frozen, as aware UTC)
        and seed. A seeded stream is scoped by config (see _run_key), so it keeps
        advancing across the per-call resolves the wrapper makes. With config=None
        the returned callable owns a new stream, and resolving again restarts it.

        Raises:
            ValueError: base_time or seed is invalid, or seed is set and config
                names no run.
        """
        cases = scenario_metadata.get("mocks", {}).get(self.tool_name)
        if cases is None:
            return None

        # Normalize to list of cases
        if not isinstance(cases, list):
            if isinstance(cases, dict) and ("output" in cases or "input" in cases):
                cases = [cases]
            else:
                cases = [{"output": cases}]

        matcher = self._matcher
        resolver = self._resolver
        fallback = self.fallback
        echo_input = self.echo_input
        tool_name = self.tool_name
        config_data = _extract_config_data(config)
        reproducibility = scenario_metadata.get("stuntdouble") or {}
        base_time = _parse_base_time(reproducibility.get("base_time"))
        rng = self._rng_for_call(reproducibility.get("seed"), config)
        # One counter dict per resolved mock (i.e. per run), shared by all its
        # calls, so {{sequence('X')}} gives X-001, X-002, ... across calls.
        sequence_counters: dict[str, int] = {}

        def mock_callable(**kwargs: Any) -> Any:
            context = ResolverContext(
                input_data=kwargs,
                config_data=config_data,
                base_time=base_time if base_time is not None else datetime.now(),
                sequence_counters=sequence_counters,
                rng=rng,
            )

            for case in cases:
                case_input = case.get("input")
                if case_input is None:
                    # Catch-all case
                    output = case.get("output", case)
                    return resolver.resolve_dynamic_values(copy.deepcopy(output), context)

                if matcher.matches(case_input, kwargs):
                    output = case.get("output", case)
                    return resolver.resolve_dynamic_values(copy.deepcopy(output), context)

            # No match found
            if echo_input:
                return kwargs

            if fallback is not None:
                return copy.deepcopy(fallback)

            raise InputNotMatchedError(
                tool_name,
                message=(
                    f"No matching mock case for tool '{tool_name}' and no fallback configured. "
                    f"Add a catch-all case (one without an 'input' key) or set fallback=... "
                    f"when registering the data-driven mock."
                ),
            )

        return mock_callable

    def when_predicate(self, scenario_metadata: dict[str, Any]) -> bool:
        """Return True if scenario_metadata contains mock data for this tool."""
        return self.tool_name in scenario_metadata.get("mocks", {})

    def __repr__(self) -> str:
        opts = []
        if self.fallback is not None:
            opts.append(f"fallback={self.fallback!r}")
        if self.echo_input:
            opts.append("echo_input=True")
        extra = f", {', '.join(opts)}" if opts else ""
        return f"DataDrivenMockFactory({self.tool_name!r}{extra})"


def register_data_driven(
    registry: Any,
    tool_name: str,
    *,
    fallback: Any = None,
    echo_input: bool = False,
) -> DataDrivenMockFactory:
    """
    Register a data-driven mock for a tool on the given registry.

    Convenience function that creates a DataDrivenMockFactory and registers
    it with the registry in one call.

    Args:
        registry: A MockToolsRegistry instance
        tool_name: Name of the tool to mock
        fallback: Value returned when no case matches
        echo_input: If True, return input kwargs when no match

    Returns:
        The created DataDrivenMockFactory instance

    Example:
        >>> from stuntdouble import MockToolsRegistry, register_data_driven
        >>> registry = MockToolsRegistry()
        >>> register_data_driven(registry, "query_bills", echo_input=True)
        >>> register_data_driven(registry, "search", fallback="No results.")
    """
    factory = DataDrivenMockFactory(tool_name, fallback=fallback, echo_input=echo_input)
    registry.register(tool_name, mock_fn=factory, when=factory.when_predicate)
    return factory


__all__ = [
    "DataDrivenMockFactory",
    "register_data_driven",
]
