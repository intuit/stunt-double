"""
MCP Tool Mirroring - Auto-discover and mock MCP server tools.

Quick Start:
    >>> from stuntdouble.mirroring import ToolMirror
    >>>
    >>> mirror = ToolMirror()
    >>> mirror.mirror(["python", "-m", "myserver"])
    >>> tools = mirror.to_langchain_tools()

One-line agent setup:
    >>> from stuntdouble.mirroring import mirror_for_agent
    >>>
    >>> tools = mirror_for_agent(my_llm, ["python", "-m", "myserver"])
    >>> agent = my_llm.bind_tools(tools)

With LLM for realistic mocks:
    >>> mirror = ToolMirror.with_llm(my_llm_client)
    >>> mirror.mirror(["python", "-m", "myserver"])

HTTP server with authentication:
    >>> mirror = ToolMirror()
    >>> mirror.mirror(
    ...     http_url="http://localhost:8080",
    ...     headers={"Authorization": "Bearer token123"}
    ... )

Custom configuration:
    >>> mirror = (
    ...     ToolMirror()
    ...     .enable_caching(ttl_minutes=30)
    ...     .enable_llm(my_llm_client)
    ... )
"""

# ============================================================================
# SIMPLE API - Recommended starting point (80% of users)
# ============================================================================

from .cache import ResponseCache
from .discovery import MCPToolDiscoverer
from .generation.base import MockGenerator
from .generation.presets import (
    QualityPreset,
    get_preset,
    list_presets,
)
from .mirror import (
    ToolMirror,
    mirror,
    mirror_for_agent,
)
from .mirror_registry import MirroredToolRegistry
from .models import (
    MirrorInfo,
    MirrorMetadata,
    MockImplementation,
    MockStrategy,
    ParameterInfo,
    ToolAnalysis,
    ToolComplexity,
    ToolDefinition,
)
from .strategies import (
    BaseStrategy,
    DynamicStrategy,
    StaticStrategy,
)

# ============================================================================
# MODELS - Data structures
# ============================================================================


# ============================================================================
# REGISTRY - Mirrored tool management
# ============================================================================


# ============================================================================
# CACHE - Response caching
# ============================================================================


# ============================================================================
# DISCOVERY - MCP server tool discovery
# ============================================================================


# ============================================================================
# GENERATION - Mock generation utilities
# ============================================================================


# ============================================================================
# STRATEGIES - Advanced mock generation strategies
# ============================================================================


__all__ = [
    # Simple API
    "ToolMirror",
    "mirror",
    "mirror_for_agent",
    # Models
    "MockStrategy",
    "ToolComplexity",
    "ToolDefinition",
    "ParameterInfo",
    "ToolAnalysis",
    "MirrorMetadata",
    "MirrorInfo",
    "MockImplementation",
    # Registry
    "MirroredToolRegistry",
    # Cache
    "ResponseCache",
    # Discovery
    "MCPToolDiscoverer",
    # Generation
    "MockGenerator",
    "QualityPreset",
    "get_preset",
    "list_presets",
    # Strategies
    "BaseStrategy",
    "StaticStrategy",
    "DynamicStrategy",
]
