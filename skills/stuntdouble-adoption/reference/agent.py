"""Reference LangGraph agent wired for StuntDouble per-invocation mocking.

The only StuntDouble-specific code is ``build_tool_node``: when the feature
flag is on, the ``ToolNode`` gets an ``awrap_tool_call`` wrapper that routes
calls to mocks *only* for invocations whose ``RunnableConfig`` carries
``configurable.scenario_metadata``. Everything else is a plain ReAct graph.
"""

from __future__ import annotations

import os

from langchain_core.language_models import BaseChatModel
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from mocking import build_registry
from tools import TOOLS

from stuntdouble import CallRecorder, create_mockable_tool_wrapper

FEATURE_FLAG = "STUNTDOUBLE_ENABLED"


def tool_mocking_enabled() -> bool:
    """Feature flag. Leave unset/false in production; set true in test and eval environments."""
    return os.getenv(FEATURE_FLAG, "false").lower() in {"1", "true", "yes"}


def build_tool_node(*, enable_mocks: bool | None = None, recorder: CallRecorder | None = None) -> ToolNode:
    """Build the ToolNode, with the StuntDouble wrapper attached when mocking is enabled."""
    if enable_mocks is None:
        enable_mocks = tool_mocking_enabled()
    if not enable_mocks:
        return ToolNode(TOOLS)

    # Signature validation happens at registration time (``tool=`` in registry.py),
    # which fails at startup rather than mid-conversation. Runtime validation
    # (``tools=TOOLS, validate_signatures=True``) is not used because it rejects
    # ``**kwargs`` mocks such as the data-driven ``list_bills`` registration
    # (https://github.com/intuit/stunt-double/issues/69).
    wrapper = create_mockable_tool_wrapper(build_registry(), recorder=recorder)
    return ToolNode(TOOLS, awrap_tool_call=wrapper)


def build_graph(
    llm: BaseChatModel,
    *,
    enable_mocks: bool | None = None,
    recorder: CallRecorder | None = None,
) -> CompiledStateGraph:
    """Compile the ReAct graph. ``llm`` is injected so tests can pass a fake model."""
    llm_with_tools = llm.bind_tools(TOOLS)

    async def agent(state: MessagesState) -> dict:
        return {"messages": [await llm_with_tools.ainvoke(state["messages"])]}

    builder = StateGraph(MessagesState)
    builder.add_node("agent", agent)
    builder.add_node("tools", build_tool_node(enable_mocks=enable_mocks, recorder=recorder))
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")
    return builder.compile()
