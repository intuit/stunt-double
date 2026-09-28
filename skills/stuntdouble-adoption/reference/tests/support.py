"""Test helpers: a scripted fake LLM and small builders for scenario configs."""

from __future__ import annotations

import json
from pathlib import Path

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from stuntdouble import inject_scenario_metadata

SCENARIOS_DIR = Path(__file__).resolve().parent.parent / "scenarios"


class FakeChatWithTools(GenericFakeChatModel):
    """Scripted chat model: replays ``messages`` in order and accepts ``bind_tools``."""

    def bind_tools(self, tools, **kwargs):
        return self


def scripted_llm(*responses: BaseMessage) -> FakeChatWithTools:
    return FakeChatWithTools(messages=iter(responses))


def tool_call(name: str, args: dict, call_id: str | None = None) -> AIMessage:
    """An AIMessage that asks the graph to run one tool."""
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id or f"call_{name}"}])


def final_answer(text: str) -> AIMessage:
    """An AIMessage with no tool calls, which ends the ReAct loop."""
    return AIMessage(content=text)


def load_scenario(name: str) -> dict:
    return json.loads((SCENARIOS_DIR / f"{name}.json").read_text())


def scenario_config(scenario: dict, **configurable) -> dict:
    """RunnableConfig carrying scenario_metadata plus any extra configurable values."""
    return inject_scenario_metadata({"configurable": configurable}, scenario)


async def run_tool_call(node: ToolNode, call: AIMessage, config: dict) -> ToolMessage:
    """Execute one tool call through ``node`` and return the resulting ToolMessage.

    ``ToolNode`` needs the LangGraph runtime, so it is wrapped in a one-node graph
    rather than invoked directly. This exercises the StuntDouble wrapper without a model.
    """
    builder = StateGraph(MessagesState)
    builder.add_node("tools", node)
    builder.add_edge(START, "tools")
    state = await builder.compile().ainvoke({"messages": [call]}, config=config)
    return state["messages"][-1]
