"""
MCP Client for connecting to MCP servers and listing/calling tools.

This module provides a client for connecting to Model Context Protocol (MCP)
servers to discover and execute tools exposed by those servers.

Supports both stdio (subprocess) and HTTP transports.
"""

import json
import logging
import subprocess
from dataclasses import dataclass, field
from typing import Any, Literal

logger = logging.getLogger(__name__)


@dataclass
class MCPTool:
    """Representation of an MCP tool."""

    name: str
    description: str
    input_schema: dict[str, Any]
    namespace: str | None = None
    _meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format."""
        result = {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "namespace": self.namespace,
        }
        if self._meta:
            result["_meta"] = self._meta
        return result


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server connection.

    Args:
        name: Name identifier for this server
        command: Command to execute (e.g., ["python", "-m", "server"]) - required for stdio
        args: Additional arguments for the command
        env: Environment variables (None = inherit parent, {} = empty env, dict = custom vars)
        transport: Transport type - "stdio" (subprocess) or "http" (HTTP/SSE)
        http_url: HTTP URL for the server (required if transport="http")
        headers: Custom HTTP headers for authentication (HTTP transport only).
                Must be a dict with string keys and values. Headers are validated
                at initialization and redacted in string representations for security.
                The Content-Type header is automatically set to application/json and
                cannot be overridden to ensure JSON-RPC protocol compliance.

    Security Notes:
        - Headers are validated to ensure they are a dictionary with string keys/values
        - Headers are redacted in __repr__ to prevent sensitive data exposure in logs
        - Content-Type is always enforced as application/json for protocol compliance
        - Warning issued if headers are specified for stdio transport (they are ignored)
    """

    name: str
    command: list[str] = field(default_factory=list)
    args: list[str] = field(default_factory=list)
    env: dict[str, str] | None = None
    transport: Literal["stdio", "http"] = "stdio"
    http_url: str | None = None
    headers: dict[str, str] | None = None

    def __post_init__(self):
        """Validate configuration after initialization."""
        if self.transport == "stdio" and not self.command:
            raise ValueError("command is required for stdio transport")
        if self.transport == "http" and not self.http_url:
            raise ValueError("http_url is required for http transport")

        # Validate headers parameter
        if self.headers is not None:
            if not isinstance(self.headers, dict):
                raise TypeError("headers must be a dictionary")
            if not all(isinstance(k, str) and isinstance(v, str) for k, v in self.headers.items()):
                raise TypeError("headers must have string keys and string values")

            if self.transport == "stdio":
                logger.warning(
                    f"Server '{self.name}': headers parameter is ignored for stdio transport. "
                    "Headers are only used with HTTP transport."
                )
                self.headers = None

    def _safe_headers(self) -> dict[str, str]:
        """Return headers with sensitive values masked for safe logging."""
        if not self.headers:
            return {}
        safe = {}
        for k, v in self.headers.items():
            if len(v) > 8:
                safe[k] = v[:4] + "****"
            else:
                safe[k] = "****"
        return safe

    def __repr__(self) -> str:
        """String representation with sensitive data redacted."""
        headers_repr = "<redacted>" if self.headers else None
        return (
            f"MCPServerConfig(name={self.name!r}, transport={self.transport!r}, "
            f"http_url={self.http_url!r}, headers={headers_repr})"
        )

    def __str__(self) -> str:
        return self.__repr__()

    # Note: env is kept as None to inherit parent environment including PATH
    # Only set env to {} or a dict if you need to customize environment variables


class MCPClient:
    """
    Client for connecting to MCP servers via stdio or HTTP.

    This client can connect to MCP servers using either stdio (subprocess)
    or HTTP transport, list available tools, and execute tool calls through
    the MCP protocol.

    Example (stdio):
        >>> config = MCPServerConfig(
        ...     name="my-server",
        ...     command=["python", "-m", "my_mcp_server"],
        ...     transport="stdio"
        ... )
        >>> client = MCPClient(config)
        >>> tools = client.list_tools()
        >>> result = client.call_tool("tool_name", {"arg": "value"})

    Example (HTTP):
        >>> config = MCPServerConfig(
        ...     name="my-server",
        ...     transport="http",
        ...     http_url="http://localhost:8080"
        ... )
        >>> client = MCPClient(config)
        >>> tools = client.list_tools()
        >>> result = client.call_tool("tool_name", {"arg": "value"})

    Example (HTTP with authentication):
        >>> config = MCPServerConfig(
        ...     name="my-server",
        ...     transport="http",
        ...     http_url="https://api.example.com/mcp",
        ...     headers={"Authorization": "Bearer your-token-here"}
        ... )
        >>> client = MCPClient(config)
        >>> tools = client.list_tools()

    Security Notes:
        - Custom headers are validated and redacted in logs for security
        - Content-Type is always set to application/json (cannot be overridden)
        - Headers are only used with HTTP transport (ignored for stdio)
    """

    def __init__(self, config: MCPServerConfig):
        """
        Initialize MCP client.

        Args:
            config: Server configuration
        """
        self.config = config
        self._process: subprocess.Popen | None = None
        self._http_session: Any = None  # aiohttp.ClientSession when using HTTP
        self._http_message_endpoint: str | None = None  # SSE session endpoint
        self._sse_response_queue: Any = None  # asyncio.Queue for SSE responses
        self._sse_task: Any = None  # Background task for SSE listener
        self._event_loop: Any = None  # Event loop for HTTP transport (must be reused)
        self._connected = False
        self._tools_cache: list[MCPTool] | None = None

        logger.info(f"MCPClient initialized for server: {config.name} (transport: {config.transport})")

    def connect(self) -> None:
        """
        Connect to the MCP server.

        Starts the server process (stdio) or establishes HTTP connection.
        """
        if self._connected:
            logger.warning(f"Already connected to {self.config.name}")
            return

        try:
            if self.config.transport == "stdio":
                self._connect_stdio()
            elif self.config.transport == "http":
                self._connect_http()
            else:
                raise ValueError(f"Unsupported transport: {self.config.transport}")

            self._connected = True
            logger.info(f"Connected to MCP server: {self.config.name}")

            # Perform handshake
            self._handshake()

        except Exception as e:
            logger.error(f"Failed to connect to MCP server {self.config.name}: {e}")
            raise

    def _connect_stdio(self) -> None:
        """Connect to MCP server via stdio (subprocess)."""
        import os

        full_command = self.config.command + self.config.args

        # Merge custom env with current environment to preserve PATH, etc.
        # If config.env is None or empty, use current environment
        if self.config.env:
            process_env = os.environ.copy()
            process_env.update(self.config.env)
        else:
            process_env = None  # Inherit parent environment

        self._process = subprocess.Popen(
            full_command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=process_env,
            text=True,
            bufsize=1,
        )

        logger.debug(f"Started stdio subprocess for {self.config.name}")

    def _connect_http(self) -> None:
        """Connect to MCP server via HTTP/SSE."""
        try:
            import aiohttp  # noqa: F401
        except ImportError:
            raise ImportError("aiohttp is required for HTTP transport. Install with: pip install aiohttp")

        # Note: We don't create the session here because it requires an event loop
        # For SSE transport, we'll establish the connection and get the message endpoint
        # when the first request is made
        logger.debug(f"HTTP transport configured for {self.config.name} at {self.config.http_url}")

        # Establish SSE connection and get message endpoint
        import asyncio

        # Store the event loop so we can reuse it for all HTTP requests
        # This is critical because aiohttp sessions are bound to their event loop
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        self._event_loop = loop
        loop.run_until_complete(self._establish_sse_connection())

    def disconnect(self) -> None:
        """Disconnect from the MCP server."""
        if not self._connected:
            return

        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            finally:
                self._process = None

        if self._sse_task or self._http_session:
            # Close the SSE listener and aiohttp session
            import asyncio

            try:
                # Use the stored event loop if available, otherwise get/create one
                loop = self._event_loop
                if loop is None:
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)

                if loop.is_running():
                    # If event loop is running, schedule cleanup
                    if self._sse_task:
                        self._sse_task.cancel()
                    if self._http_session:
                        asyncio.create_task(self._http_session.close())
                else:
                    # Otherwise close synchronously
                    if self._sse_task:
                        self._sse_task.cancel()
                    if self._http_session:
                        loop.run_until_complete(self._http_session.close())
            except Exception:
                # Fallback: close without event loop
                import warnings

                warnings.warn("Could not properly close HTTP resources")
            finally:
                self._http_session = None
                self._http_message_endpoint = None
                self._sse_response_queue = None
                self._sse_task = None
                self._event_loop = None

        self._connected = False
        self._tools_cache = None
        logger.info(f"Disconnected from MCP server: {self.config.name}")

    def list_tools(self, use_cache: bool = True) -> list[MCPTool]:
        """
        List all available tools from the MCP server.

        Args:
            use_cache: Whether to use cached tools if available

        Returns:
            List of MCPTool objects

        Example:
            >>> client = MCPClient(config)
            >>> client.connect()
            >>> tools = client.list_tools()
            >>> for tool in tools:
            ...     print(f"{tool.name}: {tool.description}")
        """
        if use_cache and self._tools_cache is not None:
            return self._tools_cache

        if not self._connected:
            self.connect()

        try:
            request = {
                "jsonrpc": "2.0",
                "id": self._generate_id(),
                "method": "tools/list",
                "params": {},
            }

            response = self._send_request(request)

            if "error" in response:
                raise RuntimeError(f"Server error: {response['error']}")

            tools_data = response.get("result", {}).get("tools", [])

            tools = []
            for tool_data in tools_data:
                tool = MCPTool(
                    name=tool_data["name"],
                    description=tool_data.get("description", ""),
                    input_schema=tool_data.get("inputSchema", {}),
                    namespace=tool_data.get("namespace"),
                    _meta=tool_data.get("_meta", {}),
                )
                tools.append(tool)

            self._tools_cache = tools
            logger.info(f"Listed {len(tools)} tools from {self.config.name}")

            return tools

        except Exception as e:
            logger.error(f"Failed to list tools from {self.config.name}: {e}")
            raise

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """
        Call a tool on the MCP server.

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments as dictionary

        Returns:
            Tool execution result

        Example:
            >>> result = client.call_tool("search_documents", {"query": "test"})
        """
        if not self._connected:
            self.connect()

        try:
            request = {
                "jsonrpc": "2.0",
                "id": self._generate_id(),
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
            }

            response = self._send_request(request)

            if "error" in response:
                raise RuntimeError(f"Tool call error: {response['error']}")

            result = response.get("result", {})
            logger.info(f"Successfully called tool '{tool_name}' on {self.config.name}")

            return result

        except Exception as e:
            logger.error(f"Failed to call tool '{tool_name}' on {self.config.name}: {e}")
            raise

    def get_tool_info(self, tool_name: str) -> MCPTool | None:
        """
        Get information about a specific tool.

        Args:
            tool_name: Name of the tool

        Returns:
            MCPTool object if found, None otherwise
        """
        tools = self.list_tools()
        for tool in tools:
            if tool.name == tool_name:
                return tool
        return None

    def _handshake(self) -> None:
        """Perform initial handshake with the server."""
        try:
            request = {
                "jsonrpc": "2.0",
                "id": self._generate_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {},
                    },
                    "clientInfo": {"name": "stunt-double", "version": "0.1.0"},
                },
            }

            response = self._send_request(request)

            if "error" in response:
                raise RuntimeError(f"Handshake error: {response['error']}")

            logger.debug(f"Handshake successful with {self.config.name}")

        except Exception as e:
            logger.error(f"Handshake failed with {self.config.name}: {e}")
            raise

    def _send_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """
        Send a JSON-RPC request to the server.

        Args:
            request: JSON-RPC request dictionary

        Returns:
            JSON-RPC response dictionary

        Note:
            This method is resilient to servers that output logs to stdout (stdio).
            It will skip non-JSON lines and only process valid JSON-RPC responses.
        """
        if self.config.transport == "stdio":
            return self._send_request_stdio(request)
        elif self.config.transport == "http":
            return self._send_request_http(request)
        else:
            raise RuntimeError(f"Unsupported transport: {self.config.transport}")

    def _send_request_stdio(self, request: dict[str, Any]) -> dict[str, Any]:
        """Send JSON-RPC request via stdio."""
        if not self._process or not self._process.stdin:
            raise RuntimeError("Not connected to stdio server")

        try:
            # Send request
            request_str = json.dumps(request) + "\n"
            self._process.stdin.write(request_str)
            self._process.stdin.flush()

            # Read response - skip log lines and find valid JSON-RPC
            max_lines = 100  # Safety limit to avoid infinite loops
            for _ in range(max_lines):
                response_str = self._process.stdout.readline()  # type: ignore[union-attr]

                if not response_str:
                    raise RuntimeError("No response from server")

                # Skip empty lines
                response_str = response_str.strip()
                if not response_str:
                    continue

                # Try to parse as JSON
                try:
                    response = json.loads(response_str)

                    # Validate it's a JSON-RPC response (has 'jsonrpc' and 'id' or 'method')
                    if isinstance(response, dict) and (
                        "jsonrpc" in response or "result" in response or "error" in response or "method" in response
                    ):
                        return response
                    else:
                        # Valid JSON but not JSON-RPC, skip it (probably a log line)
                        logger.debug(f"Skipping non-JSON-RPC line: {response_str[:100]}")
                        continue

                except json.JSONDecodeError:
                    # Not valid JSON, probably a log line - skip it
                    logger.debug(f"Skipping non-JSON line: {response_str[:100]}")
                    continue

            # If we get here, we've read max_lines without finding a valid response
            raise RuntimeError(f"No valid JSON-RPC response after {max_lines} lines")

        except Exception as e:
            logger.error(f"Stdio request failed: {e}")
            raise

    def _send_request_http(self, request: dict[str, Any]) -> dict[str, Any]:
        """Send JSON-RPC request via HTTP."""
        if not self._connected:
            raise RuntimeError("Not connected to HTTP server")

        import asyncio

        # Use the same event loop that was used to create the HTTP session
        # This is critical - aiohttp sessions are bound to their event loop
        if self._event_loop is None:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            self._event_loop = loop
        else:
            loop = self._event_loop

        # Check if the loop is already running
        # If it is, we can't use run_until_complete() - need to use asyncio.run_coroutine_threadsafe
        if loop.is_running():
            # This shouldn't happen in normal usage, but handle it gracefully
            import concurrent.futures

            future: concurrent.futures.Future[dict[str, Any]] = concurrent.futures.Future()

            def set_result(task):
                try:
                    future.set_result(task.result())
                except Exception as e:
                    future.set_exception(e)

            # Schedule the coroutine in the running loop
            task = asyncio.run_coroutine_threadsafe(self._send_request_http_async(request), loop)
            task.add_done_callback(set_result)
            return future.result(timeout=60)
        else:
            return loop.run_until_complete(self._send_request_http_async(request))

    async def _get_or_create_http_session(self):
        """Get existing HTTP session or create a new one (lazy initialization)."""
        import aiohttp

        # Check if session exists and is still valid
        if self._http_session is None or self._http_session.closed:
            if self._http_session is not None and self._http_session.closed:
                logger.warning(f"HTTP session for {self.config.name} was closed, creating new one")
            self._http_session = aiohttp.ClientSession()
            logger.debug(f"Created HTTP session for {self.config.name}")
        return self._http_session

    async def _establish_sse_connection(self):
        """Establish SSE connection and start listening for responses."""
        import asyncio

        session = await self._get_or_create_http_session()
        self._sse_response_queue = asyncio.Queue()

        try:
            # Connect to SSE endpoint
            sse_url = f"{self.config.http_url}/sse"
            logger.debug(f"Connecting to SSE endpoint: {sse_url}")

            # Start SSE listener as background task
            self._sse_task = asyncio.create_task(self._sse_listener(session, sse_url))

            # FastMCP uses a standard message endpoint: /messages
            # If we don't get an endpoint event, use the default FastMCP endpoint
            await asyncio.sleep(0.5)

            if not self._http_message_endpoint:
                # FastMCP standard endpoint for sending JSON-RPC messages
                self._http_message_endpoint = f"{self.config.http_url}/messages"
                logger.info(f"Using default FastMCP message endpoint: {self._http_message_endpoint}")

        except Exception as e:
            logger.error(f"SSE connection failed: {e}")
            raise

    def _build_request_headers(self, include_content_type: bool = False) -> dict[str, str]:
        """Build request headers from config, keeping values out of caller locals."""
        headers: dict[str, str] = {}
        if self.config.headers:
            headers.update(self.config.headers)
        if include_content_type:
            headers["Content-Type"] = "application/json"
        return headers

    async def _sse_listener(self, session, sse_url):
        """Background task to listen for SSE events."""
        try:
            async with session.get(sse_url, headers=self._build_request_headers()) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"SSE connection failed with status {resp.status}: {error_text}")
                    return

                current_event = None
                current_data = []

                async for line in resp.content:
                    line = line.decode("utf-8").strip()

                    if not line:
                        # Empty line marks end of event
                        if current_event and current_data:
                            await self._handle_sse_event(current_event, "\n".join(current_data))
                            current_event = None
                            current_data = []
                        continue

                    if line.startswith("event: "):
                        current_event = line[7:].strip()
                    elif line.startswith("data: "):
                        current_data.append(line[6:])

        except Exception as e:
            logger.error(f"SSE listener error: {e}")

    async def _handle_sse_event(self, event_type: str, data: str):
        """Handle incoming SSE event."""
        logger.debug(f"SSE event: {event_type}, data: {data[:100]}")

        if event_type == "endpoint":
            # First event: contains the message endpoint
            self._http_message_endpoint = f"{self.config.http_url}{data}"
            logger.info(f"Got SSE message endpoint: {self._http_message_endpoint}")
        elif event_type == "message" or event_type == "":
            # Response message (FastMCP may send messages without event type)
            try:
                # Try to parse as JSON-RPC response
                response = json.loads(data)
                await self._sse_response_queue.put(response)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse SSE message: {e}")
        else:
            # Handle other event types (e.g., FastMCP might use different event names)
            logger.debug(f"Received SSE event type '{event_type}' with data: {data[:100]}")

    async def _send_request_http_async(self, request: dict[str, Any]) -> dict[str, Any]:
        """Send JSON-RPC request via HTTP/SSE (async)."""
        import asyncio

        import aiohttp

        if not self._connected:
            raise RuntimeError("Not connected to HTTP server")

        if not self._http_message_endpoint:
            raise RuntimeError("No HTTP message endpoint available")

        try:
            # Get or create session (lazy initialization)
            session = await self._get_or_create_http_session()

            # Verify session is still valid
            if session.closed:
                logger.warning("Session was closed, recreating...")
                import aiohttp

                self._http_session = aiohttp.ClientSession()
                session = self._http_session

            async with session.post(
                self._http_message_endpoint,
                json=request,
                headers=self._build_request_headers(include_content_type=True),
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 202:  # SSE transport returns 202 Accepted
                    error_text = await resp.text()
                    raise RuntimeError(f"HTTP request failed with status {resp.status}: {error_text}")

            # Wait for response from SSE stream
            try:
                response = await asyncio.wait_for(self._sse_response_queue.get(), timeout=30.0)
                return response
            except TimeoutError:
                raise RuntimeError("Timeout waiting for SSE response")

        except aiohttp.ClientOSError as e:
            logger.error(
                f"HTTP connection error (session closed={self._http_session.closed if self._http_session else 'N/A'}): {e}"
            )
            # Try to recreate session and retry once
            if self._http_session and not self._http_session.closed:
                try:
                    await self._http_session.close()
                except Exception:
                    pass
            self._http_session = None
            raise RuntimeError(
                f"HTTP connection failed. This may happen if the server disconnected. Original error: {e}"
            ) from e
        except Exception as e:
            logger.error(f"HTTP request failed: {e}")
            raise

    def _generate_id(self) -> int:
        """Generate a unique request ID."""
        if not hasattr(self, "_request_id"):
            self._request_id = 0
        self._request_id += 1
        return self._request_id

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
        return False


class MCPClientRegistry:
    """
    Registry for managing multiple MCP server connections.

    This registry allows you to register and manage connections to
    multiple MCP servers, making it easy to discover tools across
    different servers.

    Example:
        >>> registry = MCPClientRegistry()
        >>> registry.register(MCPServerConfig(
        ...     name="server1",
        ...     command=["python", "-m", "server1"]
        ... ))
        >>> all_tools = registry.list_all_tools()
        >>> result = registry.call_tool("server1", "tool_name", {})
    """

    def __init__(self):
        """Initialize the registry."""
        self._clients: dict[str, MCPClient] = {}
        logger.info("MCPClientRegistry initialized")

    def register(self, config: MCPServerConfig) -> MCPClient:
        """
        Register a new MCP server.

        Args:
            config: Server configuration

        Returns:
            Initialized MCPClient
        """
        if config.name in self._clients:
            logger.warning(f"Server {config.name} already registered, replacing")

        client = MCPClient(config)
        self._clients[config.name] = client
        logger.info(f"Registered MCP server: {config.name}")

        return client

    def get_client(self, server_name: str) -> MCPClient | None:
        """
        Get a client by server name.

        Args:
            server_name: Name of the server

        Returns:
            MCPClient if found, None otherwise
        """
        return self._clients.get(server_name)

    def list_servers(self) -> list[str]:
        """List all registered server names."""
        return list(self._clients.keys())

    def list_all_tools(self, connect: bool = True) -> dict[str, list[MCPTool]]:
        """
        List tools from all registered servers.

        Args:
            connect: Whether to automatically connect to servers

        Returns:
            Dictionary mapping server names to their tool lists
        """
        all_tools = {}

        for server_name, client in self._clients.items():
            try:
                if connect and not client._connected:
                    client.connect()

                tools = client.list_tools()
                all_tools[server_name] = tools

            except Exception as e:
                logger.error(f"Failed to list tools from {server_name}: {e}")
                all_tools[server_name] = []

        return all_tools

    def call_tool(self, server_name: str, tool_name: str, arguments: dict[str, Any]) -> Any:
        """
        Call a tool on a specific server.

        Args:
            server_name: Name of the server
            tool_name: Name of the tool
            arguments: Tool arguments

        Returns:
            Tool execution result
        """
        client = self.get_client(server_name)
        if not client:
            raise ValueError(f"Server {server_name} not registered")

        return client.call_tool(tool_name, arguments)

    def disconnect_all(self) -> None:
        """Disconnect from all servers."""
        for client in self._clients.values():
            try:
                client.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting from {client.config.name}: {e}")

        logger.info("Disconnected from all MCP servers")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect_all()
        return False


# Convenience functions


def create_mcp_client(
    server_name: str,
    command: list[str],
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> MCPClient:
    """
    Convenience function to create an MCP client.

    Args:
        server_name: Name for the server
        command: Command to start the server
        args: Additional arguments
        env: Environment variables

    Returns:
        Initialized MCPClient

    Example:
        >>> client = create_mcp_client(
        ...     "my-server",
        ...     ["python", "-m", "my_mcp_server"]
        ... )
        >>> with client:
        ...     tools = client.list_tools()
    """
    config = MCPServerConfig(
        name=server_name,
        command=command,
        args=args or [],
        env=env,
    )
    return MCPClient(config)


def list_tools_from_server(
    command: list[str],
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> list[MCPTool]:
    """
    Convenience function to quickly list tools from an MCP server.

    Args:
        command: Command to start the server
        args: Additional arguments
        env: Environment variables

    Returns:
        List of MCPTool objects

    Example:
        >>> tools = list_tools_from_server(["python", "-m", "my_server"])
        >>> for tool in tools:
        ...     print(f"- {tool.name}: {tool.description}")
    """
    client = create_mcp_client("temp-server", command, args, env)
    try:
        with client:
            return client.list_tools()
    finally:
        client.disconnect()
