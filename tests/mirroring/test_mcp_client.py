"""
Tests for MCP Client functionality.
"""

import json
from unittest.mock import MagicMock, Mock, patch

import pytest

pytest.importorskip("stuntdouble.mirroring.mcp_client")

from stuntdouble.mirroring.mcp_client import (  # noqa: E402
    MCPClient,
    MCPClientRegistry,
    MCPServerConfig,
    MCPTool,
    create_mcp_client,
)


class TestMCPTool:
    """Test MCPTool dataclass."""

    def test_create_tool(self):
        """Test creating an MCPTool."""
        tool = MCPTool(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object", "properties": {}},
        )

        assert tool.name == "test_tool"
        assert tool.description == "A test tool"
        assert tool.input_schema == {"type": "object", "properties": {}}
        assert tool.namespace is None

    def test_tool_to_dict(self):
        """Test converting tool to dictionary."""
        tool = MCPTool(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object"},
            namespace="test",
        )

        tool_dict = tool.to_dict()

        assert tool_dict["name"] == "test_tool"
        assert tool_dict["description"] == "A test tool"
        assert tool_dict["inputSchema"] == {"type": "object"}
        assert tool_dict["namespace"] == "test"


class TestMCPServerConfig:
    """Test MCPServerConfig dataclass."""

    def test_create_config(self):
        """Test creating server config."""
        config = MCPServerConfig(
            name="test-server",
            command=["python", "-m", "test"],
        )

        assert config.name == "test-server"
        assert config.command == ["python", "-m", "test"]
        assert config.args == []
        assert config.env is None

    def test_config_with_args(self):
        """Test config with arguments."""
        config = MCPServerConfig(
            name="test-server",
            command=["python", "-m", "test"],
            args=["--verbose", "--debug"],
            env={"KEY": "value"},
        )

        assert config.args == ["--verbose", "--debug"]
        assert config.env == {"KEY": "value"}


class TestMCPClient:
    """Test MCPClient class."""

    def test_init(self):
        """Test client initialization."""
        config = MCPServerConfig(
            name="test-server",
            command=["python", "-m", "test"],
        )

        client = MCPClient(config)

        assert client.config == config
        assert client._process is None
        assert client._connected is False
        assert client._tools_cache is None

    @patch("subprocess.Popen")
    def test_connect(self, mock_popen):
        """Test connecting to server."""
        mock_process = MagicMock()
        mock_process.stdin = MagicMock()
        mock_process.stdout = MagicMock()
        mock_process.stdout.readline.return_value = (
            json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2024-11-05"}}) + "\n"
        )
        mock_popen.return_value = mock_process

        config = MCPServerConfig(
            name="test-server",
            command=["python", "-m", "test"],
        )
        client = MCPClient(config)

        client.connect()

        assert client._connected is True
        assert client._process is not None
        mock_popen.assert_called_once()

    @patch("subprocess.Popen")
    def test_list_tools(self, mock_popen):
        """Test listing tools from server."""
        mock_process = MagicMock()
        mock_process.stdin = MagicMock()
        mock_process.stdout = MagicMock()

        handshake_response = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2024-11-05"}}) + "\n"

        list_tools_response = (
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "result": {
                        "tools": [
                            {
                                "name": "tool1",
                                "description": "First tool",
                                "inputSchema": {"type": "object", "properties": {}},
                            },
                            {
                                "name": "tool2",
                                "description": "Second tool",
                                "inputSchema": {"type": "object", "properties": {}},
                                "namespace": "test",
                            },
                        ]
                    },
                }
            )
            + "\n"
        )

        mock_process.stdout.readline.side_effect = [
            handshake_response,
            list_tools_response,
        ]
        mock_popen.return_value = mock_process

        config = MCPServerConfig(
            name="test-server",
            command=["python", "-m", "test"],
        )
        client = MCPClient(config)

        tools = client.list_tools()

        assert len(tools) == 2
        assert tools[0].name == "tool1"
        assert tools[0].description == "First tool"
        assert tools[1].name == "tool2"
        assert tools[1].namespace == "test"

    @patch("subprocess.Popen")
    def test_list_tools_caching(self, mock_popen):
        """Test that list_tools uses cache on second call."""
        mock_process = MagicMock()
        mock_process.stdin = MagicMock()
        mock_process.stdout = MagicMock()

        handshake_response = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2024-11-05"}}) + "\n"

        list_tools_response = (
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "result": {"tools": [{"name": "tool1", "description": "Test", "inputSchema": {}}]},
                }
            )
            + "\n"
        )

        mock_process.stdout.readline.side_effect = [
            handshake_response,
            list_tools_response,
        ]
        mock_popen.return_value = mock_process

        config = MCPServerConfig(name="test", command=["python", "-m", "test"])
        client = MCPClient(config)

        tools1 = client.list_tools()
        tools2 = client.list_tools()

        assert tools1 is tools2
        assert mock_process.stdout.readline.call_count == 2

    def test_disconnect(self):
        """Test disconnecting from server."""
        config = MCPServerConfig(name="test", command=["python", "-m", "test"])
        client = MCPClient(config)

        client._connected = True
        client._process = MagicMock()
        client._tools_cache = [Mock()]

        client.disconnect()

        assert client._connected is False
        assert client._process is None
        assert client._tools_cache is None

    @patch("subprocess.Popen")
    def test_context_manager(self, mock_popen):
        """Test using client as context manager."""
        mock_process = MagicMock()
        mock_process.stdin = MagicMock()
        mock_process.stdout = MagicMock()
        mock_process.stdout.readline.return_value = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}) + "\n"
        mock_popen.return_value = mock_process

        config = MCPServerConfig(name="test", command=["python", "-m", "test"])

        with MCPClient(config) as client:
            assert client._connected is True

        assert not client._connected


class TestMCPClientRegistry:
    """Test MCPClientRegistry class."""

    def test_init(self):
        """Test registry initialization."""
        registry = MCPClientRegistry()

        assert registry._clients == {}

    def test_register(self):
        """Test registering a server."""
        registry = MCPClientRegistry()

        config = MCPServerConfig(
            name="test-server",
            command=["python", "-m", "test"],
        )

        client = registry.register(config)

        assert isinstance(client, MCPClient)
        assert "test-server" in registry._clients
        assert registry._clients["test-server"] == client

    def test_get_client(self):
        """Test getting a client by name."""
        registry = MCPClientRegistry()

        config = MCPServerConfig(name="test", command=["python"])
        registry.register(config)

        client = registry.get_client("test")

        assert client is not None
        assert client.config.name == "test"

    def test_get_nonexistent_client(self):
        """Test getting a non-existent client."""
        registry = MCPClientRegistry()

        client = registry.get_client("nonexistent")

        assert client is None

    def test_list_servers(self):
        """Test listing registered servers."""
        registry = MCPClientRegistry()

        registry.register(MCPServerConfig("server1", ["python"]))
        registry.register(MCPServerConfig("server2", ["node"]))

        servers = registry.list_servers()

        assert len(servers) == 2
        assert "server1" in servers
        assert "server2" in servers

    def test_disconnect_all(self):
        """Test disconnecting from all servers."""
        registry = MCPClientRegistry()

        client1 = Mock(spec=MCPClient)
        client2 = Mock(spec=MCPClient)

        registry._clients = {
            "server1": client1,
            "server2": client2,
        }

        registry.disconnect_all()

        client1.disconnect.assert_called_once()
        client2.disconnect.assert_called_once()


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_create_mcp_client(self):
        """Test create_mcp_client convenience function."""
        client = create_mcp_client(
            "test-server",
            ["python", "-m", "test"],
            args=["--verbose"],
            env={"KEY": "value"},
        )

        assert isinstance(client, MCPClient)
        assert client.config.name == "test-server"
        assert client.config.command == ["python", "-m", "test"]
        assert client.config.args == ["--verbose"]
        assert client.config.env == {"KEY": "value"}
