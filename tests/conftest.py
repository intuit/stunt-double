"""
Location for your shared test fixtures
"""

import os
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def shared_fixture():
    """
    Placeholder for a pytest fixture that would be shared across tests.
    :return: Replace with the value your real fixture returns
    """
    pass


@pytest.fixture
def mock_llm():
    """
    Mock LLM client for unit tests (no API calls).

    Returns a MagicMock that simulates LangChain ChatOpenAI interface
    with both invoke() and chat() methods.
    """
    from langchain_openai import ChatOpenAI

    llm = MagicMock(spec=ChatOpenAI)

    # Mock invoke() method (LangChain standard)
    mock_response = MagicMock()
    mock_response.content = "Mock response"
    llm.invoke.return_value = mock_response

    # Mock chat() method (alternative interface)
    llm.chat.return_value = "Mock response"

    return llm


@pytest.fixture
def openai_llm():
    """
    Real OpenAI client for integration tests.

    Skips test if OPENAI_API_KEY is not set.
    Uses gpt-4o-mini for cost efficiency.
    """
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set - skipping integration test")

    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.0,
    )
