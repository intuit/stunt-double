"""
Integration adapters for external systems.

Provides adapters for:
- LangChain (StructuredTool conversion)
- LLM providers (LangChain-compatible clients)
"""

from .langchain import LangChainAdapter
from .llm import LLMProvider

__all__ = [
    "LangChainAdapter",
    "LLMProvider",
]
