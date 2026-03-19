"""
Tests for MCPToolDiscoverer.

Covers schema analysis, complexity calculation, quality estimation,
and schema version hashing.
"""

import pytest

from stuntdouble.mirroring.discovery import MCPToolDiscoverer
from stuntdouble.mirroring.models import ToolComplexity, ToolDefinition


def _make_tool(
    name: str = "get_customer",
    properties: dict | None = None,
    required: list[str] | None = None,
) -> ToolDefinition:
    if properties is None:
        properties = {"customer_id": {"type": "string", "description": "Customer ID"}}
    if required is None:
        required = list(properties.keys())
    return ToolDefinition(
        name=name,
        description=f"Execute {name}",
        input_schema={
            "type": "object",
            "properties": properties,
            "required": required,
        },
    )


class TestAnalyzeSchema:
    """Tests for MCPToolDiscoverer.analyze_schema."""

    def test_simple_tool_single_required(self):
        discoverer = MCPToolDiscoverer()
        tool = _make_tool(
            properties={"id": {"type": "string"}},
            required=["id"],
        )
        analysis = discoverer.analyze_schema(tool)

        assert analysis.tool_name == "get_customer"
        assert analysis.complexity == ToolComplexity.SIMPLE
        assert analysis.required_params == ["id"]
        assert analysis.optional_params == []
        assert analysis.total_params == 1

    def test_medium_tool_three_required(self):
        discoverer = MCPToolDiscoverer()
        tool = _make_tool(
            properties={
                "a": {"type": "string"},
                "b": {"type": "integer"},
                "c": {"type": "boolean"},
            },
            required=["a", "b", "c"],
        )
        analysis = discoverer.analyze_schema(tool)
        assert analysis.complexity == ToolComplexity.MEDIUM

    def test_complex_tool_nested_object(self):
        discoverer = MCPToolDiscoverer()
        tool = _make_tool(
            properties={"address": {"type": "object"}},
            required=["address"],
        )
        analysis = discoverer.analyze_schema(tool)
        assert analysis.complexity == ToolComplexity.COMPLEX
        assert analysis.has_nested_objects is True

    def test_complex_tool_array(self):
        discoverer = MCPToolDiscoverer()
        tool = _make_tool(
            properties={"tags": {"type": "array"}},
            required=["tags"],
        )
        analysis = discoverer.analyze_schema(tool)
        assert analysis.complexity == ToolComplexity.COMPLEX
        assert analysis.has_arrays is True

    def test_complex_tool_many_required(self):
        discoverer = MCPToolDiscoverer()
        props = {f"p{i}": {"type": "string"} for i in range(6)}
        tool = _make_tool(properties=props, required=list(props.keys()))
        analysis = discoverer.analyze_schema(tool)
        assert analysis.complexity == ToolComplexity.COMPLEX

    def test_optional_params_tracked(self):
        discoverer = MCPToolDiscoverer()
        tool = _make_tool(
            properties={
                "id": {"type": "string"},
                "limit": {"type": "integer"},
            },
            required=["id"],
        )
        analysis = discoverer.analyze_schema(tool)
        assert "id" in analysis.required_params
        assert "limit" in analysis.optional_params

    def test_parameter_info_extracted(self):
        discoverer = MCPToolDiscoverer()
        tool = _make_tool(
            properties={
                "status": {
                    "type": "string",
                    "description": "Order status",
                    "enum": ["pending", "shipped"],
                }
            },
            required=[],
        )
        analysis = discoverer.analyze_schema(tool)
        param = analysis.parameters["status"]
        assert param.type == "string"
        assert param.description == "Order status"
        assert param.is_enum is True

    def test_empty_schema(self):
        discoverer = MCPToolDiscoverer()
        tool = _make_tool(properties={}, required=[])
        analysis = discoverer.analyze_schema(tool)
        assert analysis.complexity == ToolComplexity.SIMPLE
        assert analysis.total_params == 0


class TestMockQualityEstimation:
    """Tests for estimated_mock_quality scoring."""

    def test_simple_tool_high_quality(self):
        discoverer = MCPToolDiscoverer()
        tool = _make_tool(
            properties={"id": {"type": "string", "description": "ID"}},
            required=["id"],
        )
        analysis = discoverer.analyze_schema(tool)
        assert analysis.estimated_mock_quality >= 0.9

    def test_complex_tool_lower_quality(self):
        discoverer = MCPToolDiscoverer()
        tool = _make_tool(
            properties={"data": {"type": "object"}, "items": {"type": "array"}},
            required=["data", "items"],
        )
        analysis = discoverer.analyze_schema(tool)
        assert analysis.estimated_mock_quality < 0.8

    def test_metadata_rich_boosts_quality(self):
        discoverer = MCPToolDiscoverer()
        tool = _make_tool(
            properties={
                "status": {
                    "type": "string",
                    "description": "Status value",
                    "enum": ["a", "b"],
                    "format": "custom",
                }
            },
            required=["status"],
        )
        analysis = discoverer.analyze_schema(tool)
        assert analysis.estimated_mock_quality >= 1.0


class TestSchemaVersioning:
    """Tests for compute_schema_version."""

    def test_same_schema_same_hash(self):
        schema = {"type": "object", "properties": {"id": {"type": "string"}}}
        h1 = MCPToolDiscoverer.compute_schema_version(schema)
        h2 = MCPToolDiscoverer.compute_schema_version(schema)
        assert h1 == h2

    def test_different_schema_different_hash(self):
        s1 = {"type": "object", "properties": {"id": {"type": "string"}}}
        s2 = {"type": "object", "properties": {"name": {"type": "string"}}}
        assert MCPToolDiscoverer.compute_schema_version(
            s1
        ) != MCPToolDiscoverer.compute_schema_version(s2)

    def test_hash_length(self):
        schema = {"type": "object"}
        h = MCPToolDiscoverer.compute_schema_version(schema)
        assert len(h) == 16

    def test_key_order_independent(self):
        s1 = {"properties": {"a": 1}, "type": "object"}
        s2 = {"type": "object", "properties": {"a": 1}}
        assert MCPToolDiscoverer.compute_schema_version(
            s1
        ) == MCPToolDiscoverer.compute_schema_version(s2)


class TestDiscoverRequiresMCPClient:
    """Tests for discover() when MCP client is unavailable."""

    def test_discover_raises_without_mcp(self):
        discoverer = MCPToolDiscoverer()
        from unittest.mock import patch

        with patch("stuntdouble.mirroring.discovery.MCPClient", None):
            config = type("FakeConfig", (), {"name": "test"})()
            with pytest.raises(ImportError, match="MCP client is required"):
                discoverer.discover(config)
