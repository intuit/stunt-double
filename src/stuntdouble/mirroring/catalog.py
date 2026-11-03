"""Discovery from MCP Gateway Registry's stored, caller-filtered REST catalog."""

import math
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from .discovery import MCPToolDiscoverer
from .models import ToolDefinition


def validate_http_url(url: str) -> None:
    """Require an absolute HTTP endpoint without embedded credentials."""
    parsed = urlsplit(url)
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise ValueError("Expected an absolute HTTP(S) URL without credentials or a fragment")


class RegistryCatalogDiscoverer:
    """Fetch definitions without opening a connection to any backend MCP server."""

    def discover(
        self,
        registry_url: str,
        *,
        headers: dict[str, str] | None = None,
        read_timeout: float = 30.0,
        tool_name_map: dict[tuple[str, str], str] | None = None,
    ) -> list[ToolDefinition]:
        validate_http_url(registry_url)
        if urlsplit(registry_url).query:
            raise ValueError("registry_url must be a base URL without a query")
        if not math.isfinite(read_timeout) or read_timeout <= 0:
            raise ValueError("read_timeout must be finite and positive")
        if headers is not None and (
            not isinstance(headers, dict)
            or not all(isinstance(k, str) and isinstance(v, str) for k, v in headers.items())
        ):
            raise TypeError("headers must be a dictionary of strings")
        try:
            import httpx
        except ImportError:
            raise ImportError("Catalog discovery requires: pip install 'stuntdouble[mcp]'") from None

        try:
            with httpx.Client(headers=headers, timeout=read_timeout, follow_redirects=False) as client:
                response = client.get(registry_url.rstrip("/") + "/api/tool-catalog")
                if not 200 <= response.status_code < 300:
                    raise RuntimeError(f"Registry catalog request failed: HTTP {response.status_code}")
                payload = response.json()
        except httpx.TimeoutException:
            raise RuntimeError("Registry catalog request timed out") from None
        except httpx.RequestError:
            raise RuntimeError("Registry catalog connection failed") from None
        except ValueError:
            raise ValueError("Registry catalog returned invalid JSON") from None
        return self.parse(payload, tool_name_map=tool_name_map)

    @staticmethod
    def parse(payload: Any, *, tool_name_map: dict[tuple[str, str], str] | None = None) -> list[ToolDefinition]:
        """Validate every entry before returning definitions for registration."""
        if not isinstance(payload, dict) or not isinstance(payload.get("tools"), list):
            raise ValueError("Registry catalog must contain a tools array")
        mapping = tool_name_map or {}
        definitions = []
        names: set[str] = set()
        identities: set[tuple[str, str]] = set()
        fetched_at = datetime.now(UTC).isoformat()
        for index, entry in enumerate(payload["tools"]):
            if not isinstance(entry, dict):
                raise ValueError(f"Invalid catalog entry at index {index}")
            name, path = entry.get("tool_name"), entry.get("server_path")
            schema = entry.get("input_schema")
            description = entry.get("description", "")
            server = entry.get("server_name", "")
            versions = entry.get("available_versions", [])
            if (
                not isinstance(name, str)
                or not name.strip()
                or not isinstance(path, str)
                or not path.strip()
                or not isinstance(schema, dict)
                or not isinstance(description, str)
                or not isinstance(server, str)
                or not isinstance(versions, list)
                or not all(isinstance(v, str) for v in versions)
            ):
                raise ValueError(f"Invalid catalog entry at index {index}")
            if not schema:
                raise ValueError(
                    "Registry catalog returned an empty input_schema; use direct Streamable HTTP discovery "
                    "or a registry version that preserves stored input schemas"
                )
            identity = (path, name)
            mapped = mapping.get(identity, name)
            if not isinstance(mapped, str) or not mapped.strip():
                raise ValueError("Mapped tool names must be non-empty strings")
            if identity in identities or mapped in names:
                raise ValueError("Duplicate catalog tool identity or callable name; supply an explicit tool_name_map")
            identities.add(identity)
            names.add(mapped)
            definitions.append(
                ToolDefinition(
                    name=mapped,
                    description=description,
                    input_schema=schema,
                    server_name=server or path,
                    metadata={
                        "source": "registry_catalog",
                        "server_path": path,
                        "original_tool_name": name,
                        "available_versions": versions,
                        "fetched_at": fetched_at,
                        "schema_version": MCPToolDiscoverer.compute_schema_version(schema),
                    },
                )
            )
        if set(mapping) - identities:
            raise ValueError("tool_name_map contains identities absent from the authorized catalog")
        return definitions
