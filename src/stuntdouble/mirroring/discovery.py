# ABOUTME: Discovers tools exposed by MCP servers and analyzes their schemas for mirroring.
# ABOUTME: Forms the first step of the mirroring pipeline by turning remote tool metadata into local structures.
"""
Tool discovery from MCP servers.

Requires the optional ``stuntdouble[mcp]`` extra for MCP client support.
"""

import hashlib
import json
import logging
from typing import Any

from .models import ParameterInfo, ToolAnalysis, ToolComplexity, ToolDefinition

try:
    from stuntdouble.mirroring.mcp_client import MCPClient, MCPServerConfig, MCPTool
except ImportError:
    MCPClient = None  # type: ignore[assignment,misc]
    MCPServerConfig = Any  # type: ignore[assignment,misc]
    MCPTool = Any  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)


class MCPToolDiscoverer:
    """
    Discovers tools from MCP servers and analyzes their schemas.

    This class connects to MCP servers, retrieves tool definitions,
    and performs analysis to understand tool complexity and structure.

    Example:
        >>> discoverer = MCPToolDiscoverer()
        >>> tools = discoverer.discover(server_config)
        >>> for tool in tools:
        ...     print(f"Found: {tool.name}")
    """

    def __init__(self):
        """Initialize the discoverer."""
        self._client: MCPClient | None = None

    def discover(self, server_config: "MCPServerConfig") -> list[ToolDefinition]:
        """
        Discover all tools from an MCP server.

        Args:
            server_config: Configuration for the MCP server

        Returns:
            List of discovered tool definitions

        Raises:
            ConnectionError: If unable to connect to server
            RuntimeError: If discovery fails
            ImportError: If stuntdouble[mcp] is not installed
        """
        if MCPClient is None:
            raise ImportError("MCP client is required for tool discovery. Install with: pip install stuntdouble[mcp]")

        logger.info(f"Discovering tools from {server_config.name}")

        try:
            with MCPClient(server_config) as client:
                # Get tools from server
                mcp_tools = client.list_tools()

                # Convert to ToolDefinitions
                tool_definitions = []
                for mcp_tool in mcp_tools:
                    tool_def = self._convert_to_definition(mcp_tool, server_config.name)
                    tool_definitions.append(tool_def)

                logger.info(f"Discovered {len(tool_definitions)} tools from {server_config.name}")
                return tool_definitions

        except Exception as e:
            logger.error(f"Failed to discover tools from {server_config.name}: {e}")
            raise RuntimeError(f"Tool discovery failed: {e}") from e

    def analyze_schema(self, tool_def: ToolDefinition) -> ToolAnalysis:
        """
        Analyze a tool's schema to understand its structure and complexity.

        Args:
            tool_def: Tool definition to analyze

        Returns:
            Analysis of the tool's schema
        """
        logger.debug(f"Analyzing schema for {tool_def.name}")

        schema = tool_def.input_schema
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        # Analyze parameters
        parameters: dict[str, ParameterInfo] = {}
        required_params: list[str] = []
        optional_params: list[str] = []
        has_nested_objects = False
        has_arrays = False

        for param_name, param_schema in properties.items():
            param_info = self._analyze_parameter(param_name, param_schema)
            parameters[param_name] = param_info

            if param_name in required:
                required_params.append(param_name)
            else:
                optional_params.append(param_name)

            # Check for complexity indicators
            if param_info.type == "object":
                has_nested_objects = True
            elif param_info.type == "array":
                has_arrays = True

        # Determine complexity
        complexity = self._calculate_complexity(
            len(required_params), len(optional_params), has_nested_objects, has_arrays
        )

        # Estimate mock quality (simpler schemas = better quality)
        quality = self._estimate_mock_quality(complexity, parameters)

        return ToolAnalysis(
            tool_name=tool_def.name,
            complexity=complexity,
            required_params=required_params,
            optional_params=optional_params,
            parameters=parameters,
            has_nested_objects=has_nested_objects,
            has_arrays=has_arrays,
            estimated_mock_quality=quality,
        )

    def _convert_to_definition(self, mcp_tool: "MCPTool", server_name: str) -> ToolDefinition:
        """Convert MCPTool to ToolDefinition."""
        return ToolDefinition(
            name=mcp_tool.name,
            description=mcp_tool.description,
            input_schema=mcp_tool.input_schema,
            namespace=mcp_tool.namespace,
            server_name=server_name,
        )

    def _analyze_parameter(self, param_name: str, param_schema: dict) -> ParameterInfo:
        """Analyze a single parameter."""
        return ParameterInfo(
            name=param_name,
            type=param_schema.get("type", "any"),
            description=param_schema.get("description", ""),
            enum=param_schema.get("enum"),
            format=param_schema.get("format"),
            pattern=param_schema.get("pattern"),
        )

    def _calculate_complexity(
        self,
        required_count: int,
        optional_count: int,
        has_nested: bool,
        has_arrays: bool,
    ) -> ToolComplexity:
        """Calculate tool complexity based on schema features."""
        total_params = required_count + optional_count

        # Complex if has nested structures or many parameters
        if has_nested or has_arrays or required_count > 5:
            return ToolComplexity.COMPLEX

        # Medium if multiple required params
        if required_count > 2 or total_params > 4:
            return ToolComplexity.MEDIUM

        # Simple otherwise
        return ToolComplexity.SIMPLE

    def _estimate_mock_quality(self, complexity: ToolComplexity, parameters: dict[str, ParameterInfo]) -> float:
        """
        Estimate how well we can generate mocks for this tool.

        Returns:
            Quality score from 0.0 to 1.0
        """
        # Start with base score based on complexity
        base_scores = {
            ToolComplexity.SIMPLE: 1.0,
            ToolComplexity.MEDIUM: 0.8,
            ToolComplexity.COMPLEX: 0.6,
        }
        score = base_scores[complexity]

        # Boost score if parameters have helpful metadata
        has_descriptions = sum(1 for p in parameters.values() if p.description)
        has_enums = sum(1 for p in parameters.values() if p.is_enum)
        has_formats = sum(1 for p in parameters.values() if p.format)

        total_params = len(parameters)
        if total_params > 0:
            metadata_ratio = (has_descriptions + has_enums + has_formats) / (total_params * 3)
            score += metadata_ratio * 0.2  # Up to 20% boost

        return min(score, 1.0)

    @staticmethod
    def compute_schema_version(input_schema: dict) -> str:
        """
        Compute a version hash for a schema.

        This can be used to detect schema changes.

        Args:
            input_schema: JSON Schema dict

        Returns:
            SHA-256 hash of the schema
        """
        schema_str = json.dumps(input_schema, sort_keys=True)
        return hashlib.sha256(schema_str.encode()).hexdigest()[:16]


__all__ = ["MCPToolDiscoverer"]
