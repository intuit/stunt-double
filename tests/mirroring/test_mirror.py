"""
Tests for ToolMirror and convenience functions.

Covers factory methods, _infer_server_name, customize, unregister, and input
validation.  Mirror discovery is mocked to avoid a real MCP server.
"""

from unittest.mock import MagicMock, patch

import pytest

from stuntdouble.mirroring.mirror import ToolMirror, _infer_server_name


class TestInferServerName:
    """Tests for _infer_server_name helper."""

    def test_python_m_module(self):
        assert _infer_server_name(["python", "-m", "financial_mcp"]) == "financial-mcp"

    def test_python3_m_nested_module(self):
        assert _infer_server_name(["python3", "-m", "acme.tools.billing"]) == "billing"

    def test_run_command(self):
        assert _infer_server_name(["codegen", "mcp", "run", "fintech-mcp"]) == "fintech-mcp"

    def test_node_script(self):
        assert _infer_server_name(["node", "server.js"]) == "server"

    def test_npm_script(self):
        assert _infer_server_name(["npm", "start"]) == "start"

    def test_direct_binary(self):
        assert _infer_server_name(["my-server"]) == "my-server"

    def test_empty_list_default(self):
        assert _infer_server_name([]) == "mcp-server"

    def test_all_flags(self):
        assert _infer_server_name(["--flag", "-v"]) == "mcp-server"


class TestToolMirrorInit:
    """Tests for ToolMirror construction and factory methods."""

    def test_default_init(self):
        mirror = ToolMirror()
        assert mirror.registry is not None
        assert mirror.langgraph_registry is None

    def test_for_ci(self):
        mirror = ToolMirror.for_ci()
        assert mirror._use_llm is False

    def test_for_langgraph(self):
        mirror = ToolMirror.for_langgraph()
        assert mirror.langgraph_registry is not None

    def test_for_langgraph_custom_registry(self):
        from stuntdouble.mock_registry import MockToolsRegistry

        custom = MockToolsRegistry()
        mirror = ToolMirror.for_langgraph(registry=custom)
        assert mirror.langgraph_registry is custom

    def test_for_langgraph_invalid_quality(self):
        with pytest.raises(ValueError, match="Unknown quality preset"):
            ToolMirror.for_langgraph(quality="ultra")

    def test_with_llm_invalid_quality(self):
        with pytest.raises(ValueError, match="Unknown quality preset"):
            ToolMirror.with_llm(MagicMock(), quality="invalid")


class TestToolMirrorMirrorValidation:
    """Tests for .mirror() input validation."""

    def _mock_mcp_import(self):
        """Create a fake MCPServerConfig for patching the mcp import inside mirror()."""
        fake_config_cls = type(
            "MCPServerConfig",
            (),
            {
                "__init__": lambda self, **kw: self.__dict__.update(kw),
            },
        )
        return fake_config_cls

    def test_no_command_or_url_raises(self):
        mirror = ToolMirror()
        fake = self._mock_mcp_import()
        with patch("stuntdouble.mirroring.mirror.ToolMirror.mirror"):
            # Directly test that None triggers the ValueError path
            # by calling the real method after patching the mcp import
            pass

        with patch.dict("sys.modules", {"stuntdouble.mirroring.mcp_client": MagicMock(MCPServerConfig=fake)}):
            with pytest.raises(ValueError, match="Either server_command or http_url"):
                mirror.mirror(None)

    def test_http_url_string_command_converted(self):
        """A string starting with http is treated as http_url."""
        fake = self._mock_mcp_import()
        fake_module = MagicMock(MCPServerConfig=fake)

        mirror = ToolMirror()
        mirror.discoverer = MagicMock()
        mirror.discoverer.discover.return_value = []

        with patch.dict("sys.modules", {"stuntdouble.mirroring.mcp_client": fake_module}):
            result = mirror.mirror("http://localhost:8080")
        assert result["server_name"] == "http_mcp"

    def test_tool_filter_no_match_raises(self):
        """Filtering by tool names that don't exist raises ValueError."""
        from stuntdouble.mirroring.models import ToolDefinition

        fake = self._mock_mcp_import()
        fake_module = MagicMock(MCPServerConfig=fake)

        mirror = ToolMirror()
        mirror.discoverer = MagicMock()
        mirror.discoverer.discover.return_value = [
            ToolDefinition(name="a", description="a", input_schema={}),
        ]

        with patch.dict("sys.modules", {"stuntdouble.mirroring.mcp_client": fake_module}):
            with pytest.raises(ValueError, match="None of the requested tools found"):
                mirror.mirror(["python", "-m", "srv"], tools=["nonexistent"])


class TestToolMirrorCustomize:
    """Tests for .customize() and .unregister()."""

    def test_customize_stores_mock(self):
        mirror = ToolMirror()
        mirror.customize("get_weather", {"temp": 72, "conditions": "sunny"})

        fn = mirror.registry.get_mock_function("get_weather")
        assert fn is not None
        assert fn() == {"temp": 72, "conditions": "sunny"}

    def test_customize_returns_copy(self):
        """Each invocation returns a fresh copy so callers can't mutate."""
        mirror = ToolMirror()
        mirror.customize("get_weather", {"temp": 72})

        fn = mirror.registry.get_mock_function("get_weather")
        assert fn is not None
        r1 = fn()
        r1["temp"] = 999
        assert fn()["temp"] == 72

    def test_unregister_nonexistent(self):
        mirror = ToolMirror()
        assert mirror.unregister("ghost") is False


class TestToolMirrorLangChainConversion:
    """Tests for .to_langchain_tools() when no tools are mirrored."""

    def test_empty_returns_empty_list(self):
        mirror = ToolMirror()
        tools = mirror.to_langchain_tools()
        assert tools == []


class TestToolMirrorStats:
    """Tests for .get_stats() and .get_cache_stats()."""

    def test_stats_without_llm(self):
        mirror = ToolMirror()
        stats = mirror.get_stats()
        assert stats["total_mirrors"] == 0
        assert stats["llm_enabled"] is False

    def test_cache_stats_none_without_cache(self):
        mirror = ToolMirror()
        assert mirror.get_cache_stats() is None

    def test_llm_stats_none_without_llm(self):
        mirror = ToolMirror()
        assert mirror.get_llm_stats() is None

    def test_clear_cache_noop_without_cache(self):
        mirror = ToolMirror()
        assert mirror.clear_cache() == 0
