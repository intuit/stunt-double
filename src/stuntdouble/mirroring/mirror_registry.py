"""
Registry for managing mirrored tools.

Manages the lifecycle of mirrored tools: metadata tracking, persistence,
and registration into LangGraph MockToolsRegistry for ToolNode awrap_tool_call.
"""

import json
import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .models import (
    MirrorInfo,
    MirrorMetadata,
    MockImplementation,
    ToolDefinition,
)

if TYPE_CHECKING:
    from stuntdouble.mock_registry import MockToolsRegistry

    from .generation.base import MockGenerator

logger = logging.getLogger(__name__)


class MirroredToolRegistry:
    """
    Manages the lifecycle of mirrored tools.

    This registry tracks which tools have been mirrored, stores their metadata,
    and integrates with StuntDouble's mock registries:
    - LangGraph MockToolsRegistry: For ToolNode awrap_tool_call pattern

    Supports both static and dynamic mock generation:
    - Static: Returns fixed mock data
    - Dynamic: Generates parameter-aware responses using MockGenerator

    Example:
        >>> # Static mocks (backward compatible)
        >>> registry = MirroredToolRegistry()
        >>> registry.register_mirrored_tool(tool_def, mock_impl, metadata)

        >>> # Dynamic mocks with generator
        >>> from .generation.base import MockGenerator
        >>> from .cache import ResponseCache
        >>> generator = MockGenerator(cache=ResponseCache())
        >>> registry = MirroredToolRegistry(generator=generator)
        >>> registry.register_mirrored_tool(tool_def, mock_impl, metadata,
        ...                                  generator=generator, enable_dynamic=True)

        >>> # With LangGraph registry
        >>> from stuntdouble import MockToolsRegistry
        >>> langgraph_registry = MockToolsRegistry()
        >>> registry = MirroredToolRegistry(langgraph_registry=langgraph_registry)
    """

    def __init__(
        self,
        storage_dir: Path | None = None,
        generator: "MockGenerator | None" = None,
        langgraph_registry: "MockToolsRegistry | None" = None,
    ):
        """
        Initialize the registry.

        Args:
            storage_dir: Directory for storing mirror metadata.
                        If None (default), operates in-memory only with no persistence.
                        If provided, metadata is persisted to disk.
            generator: Optional MockGenerator for dynamic mock generation
            langgraph_registry: Optional LangGraph MockToolsRegistry for registering
                               mocks that work with ToolNode awrap_tool_call pattern.
                               When provided, mocks are registered to BOTH registries.
        """
        # Only create storage directory if explicitly provided
        self.storage_dir: Path | None = None
        if storage_dir is not None:
            self.storage_dir = Path(storage_dir)
            self.storage_dir.mkdir(parents=True, exist_ok=True)

        # Store generator for dynamic mock generation
        self.generator = generator

        # Store LangGraph registry for dual registration
        self._langgraph_registry = langgraph_registry

        # In-memory cache of metadata and mock functions
        self._metadata_cache: dict[str, MirrorMetadata] = {}
        self._mock_functions: dict[str, Callable[..., Any]] = {}

        # Load existing metadata (only if persistence is enabled)
        self._load_metadata()

        storage_info = str(self.storage_dir) if self.storage_dir else "in-memory only"
        langgraph_info = "yes" if langgraph_registry else "no"
        logger.info(
            f"MirroredToolRegistry initialized ({storage_info}, "
            f"dynamic={generator is not None}, langgraph={langgraph_info})"
        )

    def register_mirrored_tool(
        self,
        tool_def: ToolDefinition,
        mock_impl: MockImplementation,
        metadata: MirrorMetadata,
        generator: "MockGenerator | None" = None,
        enable_dynamic: bool = False,
    ) -> None:
        """
        Register a mirrored tool in the registry.

        This:
        1. Registers the mock in LangGraph registry if configured (for ToolNode)
        2. Saves metadata to disk
        3. Caches metadata in memory

        Args:
            tool_def: Tool definition
            mock_impl: Mock implementation
            metadata: Mirror metadata
            generator: Optional MockGenerator for dynamic generation
            enable_dynamic: Whether to use dynamic parameter-aware generation
        """
        # Use instance generator if not provided
        if generator is None:
            generator = self.generator

        langgraph_enabled = self._langgraph_registry is not None
        logger.info(
            f"Registering mirrored tool: {tool_def.name} "
            f"(dynamic={enable_dynamic and generator is not None}, langgraph={langgraph_enabled})"
        )

        try:
            if enable_dynamic and generator:

                def mock_function(**kwargs):
                    """Generated mock function with dynamic parameter-aware responses."""
                    return generator.generate_dynamic_mock(tool_def, kwargs)

                mock_function.__doc__ = (
                    f"Dynamic mock implementation of {tool_def.name} "
                    f"(auto-generated from MCP server, parameter-aware)"
                )
            else:

                def mock_function(**kwargs):
                    """Generated mock function (static response)."""
                    return mock_impl.mock_data.copy()

                mock_function.__doc__ = (
                    f"Static mock implementation of {tool_def.name} "
                    f"(auto-generated from MCP server)"
                )

            mock_function.__name__ = tool_def.name

            # Store locally so callers (e.g. LangChain adapter) can retrieve it
            self._mock_functions[tool_def.name] = mock_function

            # Register in LangGraph registry if configured (for ToolNode awrap_tool_call)
            if self._langgraph_registry is not None:

                def _make_factory(
                    fn: Callable[..., Any],
                ) -> Callable[..., Callable[..., Any]]:
                    def mock_factory(
                        scenario_metadata: dict[str, Any], config: Any = None
                    ) -> Callable[..., Any]:
                        return fn

                    return mock_factory

                self._langgraph_registry.register(
                    tool_def.name,
                    mock_fn=_make_factory(mock_function),
                )
                logger.debug(f"Registered {tool_def.name} in LangGraph registry")

            # Save metadata
            self._save_metadata(metadata)

            # Cache metadata
            self._metadata_cache[tool_def.name] = metadata

            logger.info(f"Successfully registered {tool_def.name}")

        except Exception as e:
            logger.error(f"Failed to register {tool_def.name}: {e}")
            raise

    @property
    def langgraph_registry(self) -> "MockToolsRegistry | None":
        """Get the LangGraph registry if configured."""
        return self._langgraph_registry

    def get_mirror_info(self, tool_name: str) -> MirrorInfo | None:
        """
        Get information about a mirrored tool.

        Args:
            tool_name: Name of the tool

        Returns:
            Mirror info if found, None otherwise
        """
        metadata = self._metadata_cache.get(tool_name)
        if not metadata:
            return None

        return MirrorInfo(
            tool_name=metadata.tool_name,
            server_name=metadata.server_name,
            strategy=metadata.strategy,
            last_updated=metadata.updated_at,
            is_stale=False,
        )

    def list_mirrors(self) -> list[MirrorInfo]:
        """
        List all mirrored tools.

        Returns:
            List of mirror info for all registered tools
        """
        mirrors = []
        for tool_name in self._metadata_cache.keys():
            info = self.get_mirror_info(tool_name)
            if info:
                mirrors.append(info)
        return mirrors

    def list_mirrors_by_server(self, server_name: str) -> list[MirrorInfo]:
        """
        List mirrored tools from a specific server.

        Args:
            server_name: Name of the server

        Returns:
            List of mirror info for tools from this server
        """
        return [
            mirror
            for mirror in self.list_mirrors()
            if mirror.server_name == server_name
        ]

    def get_mock_function(self, tool_name: str) -> Callable[..., Any] | None:
        """Get the mock callable for a mirrored tool, or None if not found."""
        return self._mock_functions.get(tool_name)

    def list_mock_functions(self) -> dict[str, Callable[..., Any]]:
        """Return a dict mapping tool names to their mock callables."""
        return dict(self._mock_functions)

    def unregister_mirror(self, tool_name: str) -> bool:
        """
        Unregister a mirrored tool.

        Args:
            tool_name: Name of the tool to unregister

        Returns:
            True if unregistered, False if not found
        """
        if tool_name not in self._metadata_cache:
            logger.warning(f"Tool {tool_name} not found in registry")
            return False

        try:
            metadata = self._metadata_cache.pop(tool_name)
            self._mock_functions.pop(tool_name, None)

            # Remove metadata file (only if persistence is enabled)
            metadata_file = self._get_metadata_file(metadata.server_name, tool_name)
            if metadata_file is not None and metadata_file.exists():
                metadata_file.unlink()

            # Unregister from LangGraph registry if configured
            if self._langgraph_registry is not None:
                self._langgraph_registry.unregister(tool_name)

            logger.info(f"Unregistered mirror: {tool_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to unregister {tool_name}: {e}")
            return False

    def update_mirror_timestamp(self, tool_name: str) -> None:
        """Update the last updated timestamp for a mirror."""
        if tool_name in self._metadata_cache:
            metadata = self._metadata_cache[tool_name]
            metadata.updated_at = datetime.now()
            self._save_metadata(metadata)

    def _save_metadata(self, metadata: MirrorMetadata) -> None:
        """Save metadata to disk (no-op if storage_dir is None)."""
        if self.storage_dir is None:
            return

        # Create server directory
        server_dir = self.storage_dir / metadata.server_name
        server_dir.mkdir(exist_ok=True)

        # Save metadata file
        metadata_file = self._get_metadata_file(
            metadata.server_name, metadata.tool_name
        )
        if metadata_file is None:
            return

        with open(metadata_file, "w") as f:
            json.dump(metadata.to_dict(), f, indent=2)

        logger.debug(f"Saved metadata for {metadata.tool_name}")

    def _load_metadata(self) -> None:
        """Load all metadata from disk (no-op if storage_dir is None)."""
        if self.storage_dir is None or not self.storage_dir.exists():
            return

        # Scan all server directories
        for server_dir in self.storage_dir.iterdir():
            if not server_dir.is_dir():
                continue

            # Load metadata files from this server
            for metadata_file in server_dir.glob("*.json"):
                try:
                    with open(metadata_file) as f:
                        data = json.load(f)

                    metadata = MirrorMetadata.from_dict(data)
                    self._metadata_cache[metadata.tool_name] = metadata

                except Exception as e:
                    logger.warning(f"Failed to load metadata from {metadata_file}: {e}")

        logger.info(f"Loaded metadata for {len(self._metadata_cache)} mirrored tools")

    def _get_metadata_file(self, server_name: str, tool_name: str) -> Path | None:
        """Get path to metadata file for a tool (None if storage_dir is None)."""
        if self.storage_dir is None:
            return None
        return self.storage_dir / server_name / f"{tool_name}.json"

    def get_server_list(self) -> list[str]:
        """Get list of unique server names with mirrored tools."""
        servers = set()
        for metadata in self._metadata_cache.values():
            servers.add(metadata.server_name)
        return sorted(servers)

    def clear(self, server_name: str | None = None) -> int:
        """
        Clear all mirrored tool metadata from cache and disk.

        Args:
            server_name: Optional - only clear tools from this server.
                        If None, clears all tools.

        Returns:
            Number of tools cleared
        """
        import shutil

        if server_name:
            tools_to_clear = [
                name
                for name, meta in self._metadata_cache.items()
                if meta.server_name == server_name
            ]

            for tool_name in tools_to_clear:
                self._metadata_cache.pop(tool_name, None)
                self._mock_functions.pop(tool_name, None)
                if self._langgraph_registry is not None:
                    self._langgraph_registry.unregister(tool_name)

            # Remove server directory from disk (only if persistence is enabled)
            if self.storage_dir is not None:
                server_dir = self.storage_dir / server_name
                if server_dir.exists():
                    shutil.rmtree(server_dir)

            logger.info(
                f"Cleared {len(tools_to_clear)} mirrored tools from {server_name}"
            )
            return len(tools_to_clear)

        else:
            count = len(self._metadata_cache)
            self._metadata_cache.clear()
            self._mock_functions.clear()

            if self._langgraph_registry is not None:
                self._langgraph_registry.clear()

            # Remove all server directories from disk (only if persistence is enabled)
            if self.storage_dir is not None and self.storage_dir.exists():
                for item in self.storage_dir.iterdir():
                    if item.is_dir():
                        shutil.rmtree(item)
                    elif item.is_file():
                        item.unlink()

            logger.info(f"Cleared all {count} mirrored tools")
            return count


__all__ = ["MirroredToolRegistry"]
