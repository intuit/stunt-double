# ABOUTME: Exposes adapter modules that connect mirroring features to external libraries and services.
# ABOUTME: Provides a small integration-layer import surface for LangChain and LLM-backed generation.
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
