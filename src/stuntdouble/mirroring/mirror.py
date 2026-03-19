"""
Simplified ToolMirror - Dead simple by default, powerful when needed.
"""

import logging
from typing import Any

from .discovery import MCPToolDiscoverer
from .generation.base import MockGenerator
from .integrations.langchain import LangChainAdapter
from .mirror_registry import MirroredToolRegistry
from .models import MirrorInfo, MockStrategy

logger = logging.getLogger(__name__)

# Command runners to skip when inferring server names
_COMMAND_RUNNERS = frozenset(
    {
        "python",
        "python3",
        "node",
        "npm",
        "npx",
        "java",
    }
)


def _infer_server_name(command: list[str]) -> str:
    """
    Infer server name from MCP server command.

    Examples:
        ["python", "-m", "financial_mcp"] → "financial-mcp"
        ["codegen", "mcp", "run", "fintech-mcp"] → "fintech-mcp"
        ["node", "server.js"] → "server"
    """
    if not command:
        return "mcp-server"

    # Module name after -m flag
    if "-m" in command:
        idx = command.index("-m")
        if idx + 1 < len(command):
            module = command[idx + 1]
            return module.split(".")[-1].replace("_", "-")

    # Argument after "run" command
    if "run" in command:
        idx = command.index("run")
        if idx + 1 < len(command):
            return command[idx + 1]

    # First non-flag, non-runner argument
    for i, arg in enumerate(command):
        if arg.startswith("-"):
            continue
        if i == 0 and arg.lower() in _COMMAND_RUNNERS:
            continue

        # Clean up the name
        name = arg.rsplit(".", 1)[0] if "." in arg else arg
        name = name.replace("/", "-").replace("\\", "-")
        return name or "mcp-server"

    return "mcp-server"


class ToolMirror:
    """
    Mirror MCP server tools for fast, offline testing.

    Dead simple by default:
        >>> mirror = ToolMirror()
        >>> mirror.mirror(["python", "-m", "myserver"])

    With LLM for realistic data:
        >>> mirror = ToolMirror.with_llm(my_llm_client)
        >>> mirror.mirror(["python", "-m", "myserver"])

    For LangGraph integration:
        >>> mirror = ToolMirror.for_langgraph()
        >>> mirror.mirror(["python", "-m", "myserver"])
        >>> wrapper = create_mockable_tool_wrapper(mirror.langgraph_registry)
        >>> node = ToolNode(tools, awrap_tool_call=wrapper)

    Full control when needed:
        >>> mirror = (
        ...     ToolMirror()
        ...     .enable_caching(ttl_minutes=30)
        ...     .enable_llm(my_llm_client)
        ... )
    """

    def __init__(
        self,
        *,
        _config: dict[str, Any] | None = None,
        langgraph_registry: Any | None = None,
    ):
        """
        Initialize with smart defaults.

        For most users: Just call ToolMirror() with no arguments.

        Internal use only:
            _config: Internal configuration dict (used by class methods)
            langgraph_registry: LangGraph MockToolsRegistry for dual registration
        """
        config = _config or {}
        self._enable_dynamic = config.get("enable_dynamic", False)
        self._cache_config = config.get("cache_config", {})
        self._llm_client = config.get("llm_client", None)
        self._use_llm = config.get("use_llm", False)
        self._quality_preset = config.get("quality_preset", "balanced")
        self._langgraph_registry = langgraph_registry

        # Initialize cache if dynamic enabled
        if self._enable_dynamic and self._cache_config:
            from .cache import ResponseCache

            self.cache = ResponseCache(**self._cache_config)
        else:
            self.cache = None  # type: ignore[assignment]

        # Initialize components
        self.discoverer = MCPToolDiscoverer()

        # Create generator using quality preset
        try:
            self.generator = MockGenerator.from_config(
                quality=self._quality_preset,
                llm_client=self._llm_client,
                cache=self.cache,
            )
        except ValueError as e:
            # Fallback to default if preset fails
            logger.warning(f"Failed to create generator with preset: {e}")
            self.generator = MockGenerator(cache=self.cache)

        self.registry = MirroredToolRegistry(
            generator=self.generator,
            langgraph_registry=langgraph_registry,
        )

        # Clear any stale mirrored tools from previous sessions
        self.registry.clear()

        langgraph_info = "yes" if langgraph_registry else "no"
        logger.info(
            f"ToolMirror initialized (quality={self._quality_preset}, "
            f"llm={'yes' if self._llm_client else 'no'}, langgraph={langgraph_info})"
        )

    # ============================================================================
    # SIMPLE API - Primary interface for most users
    # ============================================================================

    def mirror(
        self,
        server_command: list[str] | str | None = None,
        *,
        server_name: str | None = None,
        tools: list[str] | None = None,
        http_url: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Mirror tools from an MCP server.

        This is the main method most users need.

        Args:
            server_command: Command to start MCP server (e.g., ["python", "-m", "myserver"])
                           or HTTP URL (e.g., "http://localhost:8080")
            server_name: Optional server name (auto-detected if not provided)
            tools: Optional list of specific tools to mirror (None = all tools)
            http_url: HTTP URL for remote MCP server (alternative to server_command)
            headers: Optional custom HTTP headers for authentication (HTTP transport only)

        Returns:
            Dict with:
                - mirrored_count: Number of tools mirrored
                - tools: List of tool names
                - server_name: Name of the server

        Examples:
            >>> # Mirror from stdio server
            >>> mirror = ToolMirror()
            >>> result = mirror.mirror(["python", "-m", "financial_mcp"])

            >>> # Mirror from HTTP server
            >>> result = mirror.mirror(http_url="http://localhost:8080")

            >>> # Mirror from HTTP server with authentication
            >>> result = mirror.mirror(
            ...     http_url="http://localhost:8080",
            ...     headers={"Authorization": "Bearer token123"}
            ... )

            >>> # Mirror specific tools
            >>> result = mirror.mirror(
            ...     ["python", "-m", "myserver"],
            ...     tools=["create_invoice", "get_customer"]
            ... )
        """
        try:
            from stuntdouble.mirroring.mcp_client import MCPServerConfig
        except ImportError:
            raise ImportError("MCP client module not available. Install with: pip install stuntdouble[mcp]")

        # Validate input - either server_command or http_url must be provided
        if not server_command and not http_url:
            raise ValueError(
                "Either server_command or http_url is required. "
                "Examples:\n"
                "  - stdio: ['python', '-m', 'myserver']\n"
                "  - HTTP: http_url='http://localhost:8080'"
            )

        # Detect if server_command is an HTTP URL string
        if isinstance(server_command, str) and server_command.startswith("http"):
            http_url = server_command
            server_command = None

        # Auto-detect server name if not provided
        if server_name is None:
            if http_url:
                server_name = "http_mcp"
            else:
                server_name = _infer_server_name(server_command)  # type: ignore[arg-type]
            logger.debug(f"Inferred server name: {server_name}")

        # Create config based on transport type
        if http_url:
            # HTTP transport
            config_kwargs: dict[str, Any] = {
                "name": server_name,
                "transport": "http",
                "http_url": http_url,
            }
            # Allow command to be passed optionally for HTTP transport
            if server_command:
                config_kwargs["command"] = server_command if isinstance(server_command, list) else [server_command]
            # Add custom headers if provided
            if headers:
                config_kwargs["headers"] = headers
            server_config = MCPServerConfig(**config_kwargs)
        else:
            # stdio transport (default)
            if server_command is None:
                raise ValueError("server_command is required for stdio transport")
            cmd_list = server_command if isinstance(server_command, list) else [server_command]
            server_config = MCPServerConfig(
                name=server_name,
                command=cmd_list,
                transport="stdio",
            )

        try:
            tool_definitions = self.discoverer.discover(server_config)
        except Exception as e:
            if http_url:
                troubleshooting = (
                    f"Troubleshooting:\n"
                    f"  1. Verify the HTTP server is running at: {http_url}\n"
                    f"  2. Test connectivity: curl {http_url}/health\n"
                    f"  3. Check server logs for errors\n"
                    f"  4. Ensure aiohttp is installed: pip install aiohttp"
                )
            else:
                troubleshooting = (
                    f"Troubleshooting:\n"
                    f"  1. Verify the server command is correct: {server_command}\n"
                    f"  2. Test the server manually: {' '.join(server_command) if server_command else 'N/A'}\n"
                    f"  3. Check that the server uses stdio transport\n"
                    f"  4. Ensure all dependencies are installed"
                )

            raise RuntimeError(
                f"Failed to discover tools from server '{server_name}'. Error: {e}\n\n{troubleshooting}"
            ) from e

        # Filter if specific tools requested
        if tools:
            available_names = [t.name for t in tool_definitions]
            tool_definitions = [t for t in tool_definitions if t.name in tools]
            if not tool_definitions:
                raise ValueError(f"None of the requested tools found: {tools}\nAvailable tools: {available_names}")

        # Mirror each tool
        mirrored = []
        for tool_def in tool_definitions:
            try:
                self._mirror_tool(tool_def, server_config)
                mirrored.append(tool_def.name)
            except Exception as e:
                logger.error(f"Failed to mirror {tool_def.name}: {e}")

        result = {
            "mirrored_count": len(mirrored),
            "tools": mirrored,
            "server_name": server_name,
        }

        logger.info(f"✓ Mirrored {len(mirrored)} tools from {server_name}")
        return result

    def to_langchain_tools(self, server_name: str | None = None, tool_names: list[str] | None = None) -> list[Any]:
        """
        Convert mirrored tools to LangChain format.

        Returns tools ready for agent.bind_tools().

        Args:
            server_name: Optional filter by server
            tool_names: Optional filter by tool names

        Returns:
            List of LangChain StructuredTool instances

        Examples:
            >>> # Get all tools
            >>> tools = mirror.to_langchain_tools()
            >>> agent = llm.bind_tools(tools)

            >>> # Get specific tools
            >>> tools = mirror.to_langchain_tools(
            ...     tool_names=["create_invoice", "get_customer"]
            ... )
        """
        from .models import ToolDefinition

        available = list(self.registry.list_mock_functions().keys())

        if server_name:
            mirrors = self.list_mirrors_by_server(server_name)
            available = [m.tool_name for m in mirrors]

        if tool_names:
            available = [t for t in available if t in tool_names]

        if not available:
            logger.warning("No tools available to convert. Mirror some tools first.")
            return []

        tool_defs = []
        for name in available:
            if info := self.get_mirror_info(name):
                tool_defs.append(
                    ToolDefinition(
                        name=name,
                        description=f"Tool from {info.server_name}",
                        input_schema={},
                        server_name=info.server_name,
                    )
                )

        return LangChainAdapter.to_langchain_tools(tool_defs, self.registry)

    # ============================================================================
    # FLUENT CONFIGURATION - For users who want more control
    # ============================================================================

    @classmethod
    def with_llm(cls, llm_client, quality: str = "balanced") -> "ToolMirror":
        """
        Create a mirror with LLM-powered mock generation.

        Args:
            llm_client: LangChain ChatOpenAI-compatible LLM instance
            quality: "fast" | "balanced" | "high" (default: "balanced")

        Returns:
            Configured ToolMirror instance

        Examples:
            >>> from langchain_openai import ChatOpenAI
            >>> llm = ChatOpenAI(model="gpt-4o")
            >>> mirror = ToolMirror.with_llm(llm)
            >>> mirror.mirror(["python", "-m", "myserver"])
        """
        # Validate quality preset
        valid_presets = ["fast", "balanced", "high"]
        if quality not in valid_presets:
            raise ValueError(f"Unknown quality preset: '{quality}'. Available: {', '.join(valid_presets)}")

        # Quality-specific configs
        quality_configs = {
            "fast": {
                "enable_dynamic": False,
                "cache_config": {},
            },
            "balanced": {
                "enable_dynamic": True,
                "cache_config": {"ttl_seconds": 3600, "max_entries": 10000},
            },
            "high": {
                "enable_dynamic": True,
                "cache_config": {"ttl_seconds": 7200, "max_entries": 5000},
            },
        }

        # Create config with quality preset
        config = {
            "llm_client": llm_client,
            "use_llm": True,
            "quality_preset": quality,
            **quality_configs[quality],
        }

        return cls(_config=config)

    @classmethod
    def for_ci(cls) -> "ToolMirror":
        """
        Create a mirror optimized for CI/CD: fast and deterministic.

        Returns:
            Configured ToolMirror instance

        Examples:
            >>> mirror = ToolMirror.for_ci()
            >>> mirror.mirror(["python", "-m", "myserver"])
        """
        config = {
            "quality_preset": "fast",
            "enable_dynamic": False,
            "cache_config": {},
            "use_llm": False,
        }
        return cls(_config=config)

    @classmethod
    def for_langgraph(
        cls,
        registry: Any | None = None,
        quality: str = "balanced",
    ) -> "ToolMirror":
        """
        Create a mirror configured for LangGraph integration.

        Mirrored tools are automatically registered to the
        LangGraph MockToolsRegistry (for ToolNode awrap_tool_call).

        Args:
            registry: Optional MockToolsRegistry to use. If None, creates a new one.
            quality: Quality preset - "fast" | "balanced" | "high" (default: "balanced")

        Returns:
            Configured ToolMirror instance with LangGraph registry

        Examples:
            >>> from stuntdouble import create_mockable_tool_wrapper
            >>> from langgraph.prebuilt import ToolNode
            >>>
            >>> # Create mirror with LangGraph support
            >>> mirror = ToolMirror.for_langgraph()
            >>> mirror.mirror(["python", "-m", "my_mcp_server"])
            >>>
            >>> # Get tools and create wrapper
            >>> tools = mirror.to_langchain_tools()
            >>> wrapper = create_mockable_tool_wrapper(mirror.langgraph_registry)
            >>> node = ToolNode(tools, awrap_tool_call=wrapper)

            >>> # Use with existing registry
            >>> from stuntdouble import MockToolsRegistry
            >>> registry = MockToolsRegistry()
            >>> registry.register("custom_tool", mock_fn=lambda md: lambda: "custom")
            >>> mirror = ToolMirror.for_langgraph(registry)
            >>> mirror.mirror(["python", "-m", "my_server"])  # Added to same registry
        """
        # Import here to avoid circular imports and make LangGraph optional
        try:
            from stuntdouble.mock_registry import MockToolsRegistry
        except ImportError:
            raise ImportError(
                "LangGraph integration requires stuntdouble. Ensure stuntdouble dependencies are installed."
            )

        # Create or use provided registry
        if registry is None:
            registry = MockToolsRegistry()

        # Validate quality preset
        valid_presets = ["fast", "balanced", "high"]
        if quality not in valid_presets:
            raise ValueError(f"Unknown quality preset: '{quality}'. Available: {', '.join(valid_presets)}")

        config = {"quality_preset": quality}
        return cls(_config=config, langgraph_registry=registry)

    @property
    def langgraph_registry(self) -> Any | None:
        """
        Get the LangGraph MockToolsRegistry (if configured).

        Returns:
            MockToolsRegistry if configured via for_langgraph(), None otherwise

        Examples:
            >>> mirror = ToolMirror.for_langgraph()
            >>> mirror.mirror(["python", "-m", "myserver"])
            >>> registry = mirror.langgraph_registry
            >>> wrapper = create_mockable_tool_wrapper(registry)
        """
        return self._langgraph_registry

    def enable_caching(self, ttl_minutes: int = 60, max_entries: int = 10000) -> "ToolMirror":
        """
        Enable response caching.

        Args:
            ttl_minutes: Cache time-to-live in minutes
            max_entries: Maximum cache entries

        Returns:
            Self for method chaining

        Examples:
            >>> mirror = ToolMirror().enable_caching(ttl_minutes=30)
            >>> mirror.mirror(["python", "-m", "myserver"])
        """
        self._enable_dynamic = True
        self._cache_config = {
            "ttl_seconds": ttl_minutes * 60,
            "max_entries": max_entries,
        }

        # Reinitialize cache and generator
        from .cache import ResponseCache

        self.cache = ResponseCache(**self._cache_config)

        # Recreate generator with new cache
        try:
            self.generator = MockGenerator.from_config(
                quality=self._quality_preset,
                llm_client=self._llm_client,
                cache=self.cache,
            )
        except ValueError:
            # Fallback to default
            self.generator = MockGenerator(cache=self.cache)

        self.registry = MirroredToolRegistry(
            generator=self.generator,
            langgraph_registry=self._langgraph_registry,
        )

        logger.info(f"Caching enabled (ttl={ttl_minutes}min, max_entries={max_entries})")
        return self

    def enable_llm(self, llm_client) -> "ToolMirror":
        """
        Enable LLM-powered mock generation.

        Args:
            llm_client: LLM client instance

        Returns:
            Self for method chaining

        Examples:
            >>> from langchain_openai import ChatOpenAI
            >>> mirror = ToolMirror().enable_llm(ChatOpenAI(model="gpt-4o"))
            >>> mirror.mirror(["python", "-m", "myserver"])
        """
        self._llm_client = llm_client
        self._enable_dynamic = True
        self._use_llm = True
        # Upgrade to high quality when LLM enabled
        if self._quality_preset == "balanced":
            self._quality_preset = "high"

        # Recreate generator with LLM
        try:
            self.generator = MockGenerator.from_config(
                quality=self._quality_preset,
                llm_client=llm_client,
                cache=self.cache,
            )
        except ValueError:
            # Fallback
            self.generator = MockGenerator(cache=self.cache)

        self.registry = MirroredToolRegistry(
            generator=self.generator,
            langgraph_registry=self._langgraph_registry,
        )

        logger.info("LLM-powered mock generation enabled")
        return self

    # ============================================================================
    # INTROSPECTION - Query mirrored tools
    # ============================================================================

    def list_mirrors(self) -> list[MirrorInfo]:
        """List all mirrored tools."""
        return self.registry.list_mirrors()

    def list_mirrors_by_server(self, server_name: str) -> list[MirrorInfo]:
        """List mirrored tools from a specific server."""
        return self.registry.list_mirrors_by_server(server_name)

    def get_mirror_info(self, tool_name: str) -> MirrorInfo | None:
        """Get information about a specific mirrored tool."""
        return self.registry.get_mirror_info(tool_name)

    def get_stats(self) -> dict[str, Any]:
        """
        Get statistics about mirroring operations.

        Returns:
            Dict with cache stats, LLM usage, etc.
        """
        stats = {
            "total_mirrors": len(self.list_mirrors()),
            "llm_enabled": self._use_llm,
            "caching_enabled": self.cache is not None,
        }

        if self.cache:
            cache_stats = self.cache.stats()
            stats["cache"] = cache_stats

        if self._use_llm:
            llm_stats = self.generator.get_llm_stats()
            stats["llm"] = llm_stats

        return stats

    # ============================================================================
    # CUSTOMIZATION - Override mock data
    # ============================================================================

    def customize(self, tool_name: str, mock_data: dict[str, Any]) -> None:
        """
        Set custom mock data for a tool.

        Args:
            tool_name: Name of the tool
            mock_data: Custom mock data to return

        Examples:
            >>> mirror.customize("create_invoice", {
            ...     "invoice_id": "TEST-001",
            ...     "status": "pending"
            ... })
        """

        def mock_function(**kwargs: Any) -> dict[str, Any]:
            return mock_data.copy()

        mock_function.__name__ = tool_name
        mock_function.__doc__ = f"Custom mock for {tool_name}"

        # Store in the mirrored-tool registry
        self.registry._mock_functions[tool_name] = mock_function

        # Also register in LangGraph registry if configured
        if self.registry.langgraph_registry is not None:

            def _factory(fn: Any) -> Any:
                def mock_factory(scenario_metadata: Any, config: Any = None) -> Any:
                    return fn

                return mock_factory

            self.registry.langgraph_registry.register(
                tool_name,
                mock_fn=_factory(mock_function),
            )

        # Update metadata
        metadata = self.registry._metadata_cache.get(tool_name)
        if metadata:
            metadata.custom_data_set = True
            self.registry._save_metadata(metadata)

    def unregister(self, tool_name: str) -> bool:
        """
        Remove a mirrored tool.

        Args:
            tool_name: Name of the tool to remove

        Returns:
            True if removed, False if not found
        """
        return self.registry.unregister_mirror(tool_name)

    # ============================================================================
    # CACHE MANAGEMENT
    # ============================================================================

    def get_cache_stats(self) -> dict[str, Any] | None:
        """
        Get cache statistics (only available when caching is enabled).

        Returns:
            Cache statistics or None if caching not enabled
        """
        return self.cache.stats() if self.cache else None

    def clear_cache(self, tool_name: str | None = None) -> int:
        """
        Clear response cache (only available when caching is enabled).

        Args:
            tool_name: Clear only entries for this tool (None = clear all)

        Returns:
            Number of entries cleared
        """
        if self.cache:
            return self.cache.clear(tool_name)
        return 0

    def get_llm_stats(self) -> dict[str, Any] | None:
        """
        Get LLM usage statistics (only available when LLM is enabled).

        Returns:
            LLM statistics or None if LLM not enabled
        """
        if self._use_llm:
            return self.generator.get_llm_stats()
        return None

    # ============================================================================
    # INTERNAL METHODS
    # ============================================================================

    def _mirror_tool(self, tool_def, server_config) -> None:
        """Internal: Mirror a single tool."""
        logger.debug(f"Mirroring tool: {tool_def.name}")

        # Analyze schema
        analysis = self.discoverer.analyze_schema(tool_def)

        # Determine strategy
        if self._use_llm:
            strategy = MockStrategy.LLM_DYNAMIC
        else:
            strategy = MockStrategy.SCHEMA_ONLY

        # Generate mock
        mock_impl = self.generator.generate_mock(tool_def, analysis, strategy)

        # Update metadata
        mock_impl.metadata.server_command = server_config.command
        mock_impl.metadata.schema_version = MCPToolDiscoverer.compute_schema_version(tool_def.input_schema)

        # Register
        self.registry.register_mirrored_tool(
            tool_def,
            mock_impl,
            mock_impl.metadata,
            generator=self.generator,
            enable_dynamic=self._enable_dynamic,
        )


# ============================================================================
# CONVENIENCE FUNCTIONS - Top-level helpers
# ============================================================================


def mirror(
    server_command: list[str],
    server_name: str | None = None,
    tools: list[str] | None = None,
) -> dict[str, Any]:
    """
    One-line function to mirror MCP server tools.

    This is the absolute simplest way to use StuntDouble mirror.

    Args:
        server_command: Command to start MCP server
        server_name: Optional server name (auto-detected if not provided)
        tools: Optional list of specific tools to mirror

    Returns:
        Dict with mirrored_count, tools, server_name

    Examples:
        >>> from stuntdouble.mirroring import mirror
        >>> mirror(["python", "-m", "myserver"])
        {'mirrored_count': 5, 'tools': ['tool1', 'tool2', ...], 'server_name': 'myserver'}
    """
    m = ToolMirror()
    return m.mirror(server_command, server_name=server_name, tools=tools)


def mirror_for_agent(llm_client, server_command: list[str], **kwargs) -> list[Any]:
    """
    One-line function to mirror tools and get LangChain tools.

    Perfect for agent setup - does everything in one call.

    Args:
        llm_client: LLM client for mock generation
        server_command: Command to start MCP server
        **kwargs: Additional options (server_name, tools, etc.)

    Returns:
        List of LangChain StructuredTool instances ready for agent.bind_tools()

    Examples:
        >>> from stuntdouble.mirroring import mirror_for_agent
        >>> from langchain_openai import ChatOpenAI
        >>>
        >>> llm = ChatOpenAI(model="gpt-4o")
        >>> tools = mirror_for_agent(llm, ["python", "-m", "myserver"])
        >>> agent = llm.bind_tools(tools)
    """
    m = ToolMirror.with_llm(llm_client)
    m.mirror(server_command, **kwargs)
    return m.to_langchain_tools()


__all__ = ["ToolMirror", "mirror", "mirror_for_agent"]
