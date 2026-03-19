"""
Utility functions for MCP client operations.

Provides helper functions for parsing configurations and handling
common MCP client tasks.
"""

import json
import logging
from typing import Any

from stuntdouble.mirroring.mcp_client import MCPServerConfig

logger = logging.getLogger(__name__)


def parse_mcp_config(config_data: dict[str, Any] | str) -> MCPServerConfig:
    """
    Parse MCP server configuration from dictionary or JSON string.

    Handles both dict and JSON string inputs, validating the configuration
    and creating a proper MCPServerConfig instance.

    Args:
        config_data: Configuration as dict or JSON string with keys:
            - name: Server name (optional, defaults to "mcp-server")
            - transport: "stdio" or "http" (optional, defaults to "stdio")
            - http_url: HTTP URL if transport is "http"
            - command: Command list if transport is "stdio"
            - args: Additional args for stdio transport
            - env: Environment variables

    Returns:
        MCPServerConfig instance

    Raises:
        ValueError: If config is invalid or missing required fields
        json.JSONDecodeError: If JSON string is malformed

    Examples:
        >>> # From dictionary (HTTP)
        >>> config = parse_mcp_config({
        ...     "name": "my-server",
        ...     "transport": "http",
        ...     "http_url": "http://localhost:8080"
        ... })

        >>> # From dictionary (stdio)
        >>> config = parse_mcp_config({
        ...     "name": "my-server",
        ...     "transport": "stdio",
        ...     "command": ["python", "-m", "my_server"]
        ... })

        >>> # From JSON string
        >>> json_str = '{"transport": "http", "http_url": "http://localhost:8080"}'
        >>> config = parse_mcp_config(json_str)
    """
    # Parse JSON string if needed
    if isinstance(config_data, str):
        try:
            config_data = json.loads(config_data)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in mcp_server_config: {e}") from e

    if not isinstance(config_data, dict):
        raise ValueError(
            f"mcp_server_config must be a dict or JSON string, "
            f"got {type(config_data).__name__}"
        )

    # Extract fields with defaults
    name = config_data.get("name", "mcp-server")
    transport = config_data.get("transport", "stdio")
    http_url = config_data.get("http_url")
    command = config_data.get("command", [])
    args = config_data.get("args", [])
    env = config_data.get("env")

    # Validate transport-specific requirements
    if transport not in ["stdio", "http"]:
        raise ValueError(f"Invalid transport '{transport}', must be 'stdio' or 'http'")

    if transport == "http" and not http_url:
        raise ValueError("http_url is required when transport is 'http'")

    if transport == "stdio" and not command:
        raise ValueError("command is required when transport is 'stdio'")

    try:
        # Create MCPServerConfig (will validate in __post_init__)
        config = MCPServerConfig(
            name=name,
            transport=transport,
            http_url=http_url,
            command=command,
            args=args,
            env=env,
        )
        logger.debug(
            f"Parsed MCP config: name={config.name}, transport={config.transport}"
        )
        return config

    except Exception as e:
        raise ValueError(f"Failed to create MCPServerConfig: {e}") from e


__all__ = [
    "parse_mcp_config",
]
