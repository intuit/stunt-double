"""
Data models for MCP Tool Mirror functionality.

This module provides the core data structures for tool mirroring:
- ToolDefinition: Complete tool definition from MCP server
- ParameterInfo: Individual parameter metadata
- ToolAnalysis: Schema analysis results
- MirrorMetadata: Tracking info for mirrored tools
- MirrorInfo: Summary view of mirrored tools
- MockImplementation: Generated mock with code and data
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class MockStrategy(Enum):
    """
    Strategy for generating mocks.

    Determines how mock data is generated or obtained for a mirrored tool.

    Attributes:
        SCHEMA_ONLY: Generate from JSON schema, never call real server
        PROXY_CACHE: Call server once, cache and reuse the response
        PROXY_ALWAYS: Always call real server (for integration tests)
        CUSTOM: User-provided mock data
        LLM_DYNAMIC: Use LLM to generate realistic mock responses

    Example:
        >>> from stuntdouble.mirroring import MockStrategy
        >>>
        >>> # Available strategies
        >>> MockStrategy.SCHEMA_ONLY   # schema-based generation (no server calls)
        >>> MockStrategy.PROXY_CACHE   # caching proxy (calls server once)
        >>> MockStrategy.LLM_DYNAMIC   # LLM-powered realistic data
    """

    SCHEMA_ONLY = "schema"
    PROXY_CACHE = "proxy"
    PROXY_ALWAYS = "live"
    CUSTOM = "custom"
    LLM_DYNAMIC = "llm_dynamic"


class ToolComplexity(Enum):
    """
    Complexity rating for tools.

    Used to estimate mock generation difficulty and quality.

    Attributes:
        SIMPLE: Basic types (str, int, bool), few parameters
        MEDIUM: Some nesting or multiple required parameters
        COMPLEX: Deep nesting, many parameters, complex types

    Example:
        >>> from stuntdouble.mirroring import ToolComplexity
        >>>
        >>> # Check tool complexity
        >>> if analysis.complexity == ToolComplexity.COMPLEX:
        ...     print("Consider using LLM for realistic mocks")
    """

    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"


@dataclass
class ToolDefinition:
    """
    Complete definition of a tool from an MCP server.

    Captures all metadata needed to generate mocks or call the real tool.

    Attributes:
        name: Tool name (e.g., "get_customer")
        description: Human-readable description
        input_schema: JSON Schema for tool inputs
        namespace: Optional namespace/category for grouping
        server_name: Name of the source MCP server
        metadata: Additional metadata from server

    Example:
        >>> from stuntdouble.mirroring import ToolDefinition
        >>>
        >>> tool = ToolDefinition(
        ...     name="get_customer",
        ...     description="Retrieve customer by ID",
        ...     input_schema={
        ...         "type": "object",
        ...         "properties": {
        ...             "customer_id": {"type": "string", "description": "Customer ID"}
        ...         },
        ...         "required": ["customer_id"]
        ...     },
        ...     server_name="customer-service"
        ... )
        >>> print(tool.full_name)
        'get_customer'
        >>>
        >>> # With namespace
        >>> tool_with_ns = ToolDefinition(
        ...     name="get_customer",
        ...     description="Retrieve customer",
        ...     input_schema={},
        ...     namespace="crm"
        ... )
        >>> print(tool_with_ns.full_name)
        'crm.get_customer'
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    namespace: str | None = None
    server_name: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def full_name(self) -> str:
        """Get fully qualified tool name including namespace."""
        if self.namespace:
            return f"{self.namespace}.{self.name}"
        return self.name


@dataclass
class ParameterInfo:
    """
    Information about a tool parameter.

    Extracted from JSON schema for use in mock generation.

    Attributes:
        name: Parameter name
        type: JSON schema type (string, integer, object, etc.)
        description: Human-readable description
        required: Whether parameter is required
        default: Default value if any
        enum: List of allowed values (for enum types)
        format: JSON schema format (email, date-time, etc.)
        pattern: Regex pattern for validation

    Example:
        >>> from stuntdouble.mirroring import ParameterInfo
        >>>
        >>> # Simple string parameter
        >>> param = ParameterInfo(
        ...     name="customer_id",
        ...     type="string",
        ...     description="Unique customer identifier",
        ...     required=True
        ... )
        >>>
        >>> # Enum parameter
        >>> status_param = ParameterInfo(
        ...     name="status",
        ...     type="string",
        ...     description="Order status",
        ...     enum=["pending", "shipped", "delivered"]
        ... )
        >>> print(status_param.is_enum)
        True
    """

    name: str
    type: str
    description: str = ""
    required: bool = False
    default: Any | None = None
    enum: list[Any] | None = None
    format: str | None = None
    pattern: str | None = None

    @property
    def is_enum(self) -> bool:
        """Check if parameter is an enum type."""
        return self.enum is not None and len(self.enum) > 0


@dataclass
class ToolAnalysis:
    """
    Analysis of a tool's schema and complexity.

    Result of analyzing a ToolDefinition to determine mock generation strategy.

    Attributes:
        tool_name: Name of the analyzed tool
        complexity: Complexity rating (SIMPLE, MEDIUM, COMPLEX)
        required_params: List of required parameter names
        optional_params: List of optional parameter names
        parameters: Detailed parameter information by name
        has_nested_objects: Whether schema contains nested objects
        has_arrays: Whether schema contains array types
        estimated_mock_quality: Quality estimate (0.0-1.0)

    Example:
        >>> from stuntdouble.mirroring import ToolAnalysis, ToolComplexity, ParameterInfo
        >>>
        >>> analysis = ToolAnalysis(
        ...     tool_name="get_customer",
        ...     complexity=ToolComplexity.SIMPLE,
        ...     required_params=["customer_id"],
        ...     optional_params=["include_orders"],
        ...     parameters={
        ...         "customer_id": ParameterInfo(name="customer_id", type="string", required=True),
        ...         "include_orders": ParameterInfo(name="include_orders", type="boolean"),
        ...     }
        ... )
        >>> print(analysis.total_params)
        2
        >>> print(analysis.complexity)
        ToolComplexity.SIMPLE
    """

    tool_name: str
    complexity: ToolComplexity
    required_params: list[str]
    optional_params: list[str]
    parameters: dict[str, ParameterInfo]
    has_nested_objects: bool = False
    has_arrays: bool = False
    estimated_mock_quality: float = 1.0

    @property
    def total_params(self) -> int:
        """Get total number of parameters."""
        return len(self.required_params) + len(self.optional_params)


@dataclass
class MirrorMetadata:
    """
    Metadata about a mirrored tool.

    Tracks when and how a tool was mirrored for staleness detection.

    Attributes:
        tool_name: Name of the tool
        server_name: Source MCP server name
        server_command: Command used to start the server
        strategy: Mock strategy used
        created_at: When mirror was first created
        updated_at: When mirror was last updated
        schema_version: Version/hash of the schema (for change detection)
        custom_data_set: Whether custom mock data was provided

    Example:
        >>> from stuntdouble.mirroring import MirrorMetadata, MockStrategy
        >>> from datetime import datetime
        >>>
        >>> metadata = MirrorMetadata(
        ...     tool_name="get_customer",
        ...     server_name="customer-service",
        ...     server_command=["python", "-m", "customer_mcp"],
        ...     strategy=MockStrategy.SCHEMA_ONLY
        ... )
        >>>
        >>> # Serialize for storage
        >>> data = metadata.to_dict()
        >>> print(data["strategy"])
        'schema'
        >>>
        >>> # Deserialize from storage
        >>> restored = MirrorMetadata.from_dict(data)
        >>> print(restored.tool_name)
        'get_customer'
    """

    tool_name: str
    server_name: str
    server_command: list[str]
    strategy: MockStrategy
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    schema_version: str = ""
    custom_data_set: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "tool_name": self.tool_name,
            "server_name": self.server_name,
            "server_command": self.server_command,
            "strategy": self.strategy.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "schema_version": self.schema_version,
            "custom_data_set": self.custom_data_set,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MirrorMetadata":
        """Create from dictionary."""
        return cls(
            tool_name=data["tool_name"],
            server_name=data["server_name"],
            server_command=data["server_command"],
            strategy=MockStrategy(data["strategy"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            schema_version=data.get("schema_version", ""),
            custom_data_set=data.get("custom_data_set", False),
        )


@dataclass
class MirrorInfo:
    """
    Summary information about a mirrored tool.

    Lightweight view of mirrored tool status for listing and monitoring.

    Attributes:
        tool_name: Tool name
        server_name: Source server
        strategy: Mock strategy used
        last_updated: Last update timestamp
        is_stale: Whether mirror needs updating

    Example:
        >>> from stuntdouble.mirroring import MirrorInfo, MockStrategy
        >>> from datetime import datetime
        >>>
        >>> info = MirrorInfo(
        ...     tool_name="get_customer",
        ...     server_name="customer-service",
        ...     strategy=MockStrategy.SCHEMA_ONLY,
        ...     last_updated=datetime.now()
        ... )
        >>> print(info)
        ✓ get_customer [schema] from customer-service
        >>>
        >>> # Stale mirror
        >>> stale_info = MirrorInfo(
        ...     tool_name="old_tool",
        ...     server_name="legacy-server",
        ...     strategy=MockStrategy.PROXY_CACHE,
        ...     last_updated=datetime(2024, 1, 1),
        ...     is_stale=True
        ... )
        >>> print(stale_info)
        ⚠️ stale old_tool [proxy] from legacy-server
    """

    tool_name: str
    server_name: str
    strategy: MockStrategy
    last_updated: datetime
    is_stale: bool = False

    def __str__(self) -> str:
        """String representation with status indicator."""
        status = "⚠️ stale" if self.is_stale else "✓"
        return (
            f"{status} {self.tool_name} [{self.strategy.value}] from {self.server_name}"
        )


@dataclass
class MockImplementation:
    """
    Generated mock implementation.

    Contains the generated mock function code and data for a mirrored tool.

    Attributes:
        tool_name: Name of the tool
        function_code: Generated Python function code (as string)
        mock_data: Mock data to return when tool is called
        metadata: Full mirror metadata

    Example:
        >>> from stuntdouble.mirroring import MockImplementation, MirrorMetadata, MockStrategy
        >>>
        >>> impl = MockImplementation(
        ...     tool_name="get_customer",
        ...     function_code='def get_customer(**kwargs):\\n    return {"id": "123", "name": "Acme"}',
        ...     mock_data={"id": "123", "name": "Acme Corp", "balance": 1500.00},
        ...     metadata=MirrorMetadata(
        ...         tool_name="get_customer",
        ...         server_name="customer-service",
        ...         server_command=["python", "-m", "server"],
        ...         strategy=MockStrategy.SCHEMA_ONLY
        ...     )
        ... )
        >>> print(impl.mock_data["name"])
        'Acme Corp'
    """

    tool_name: str
    function_code: str
    mock_data: Any
    metadata: MirrorMetadata


__all__ = [
    "MockStrategy",
    "ToolComplexity",
    "ToolDefinition",
    "ParameterInfo",
    "ToolAnalysis",
    "MirrorMetadata",
    "MirrorInfo",
    "MockImplementation",
]
