"""Synchronous facade over an SDK session owned by a dedicated async task."""

import logging
from contextlib import ExitStack, asynccontextmanager
from datetime import timedelta
from typing import Any, cast

logger = logging.getLogger(__name__)


def _safe_error(exc: BaseException) -> str:
    """Describe failures without echoing server bodies, URLs or credentials."""
    import httpx

    if isinstance(exc, BaseExceptionGroup):
        return "; ".join(dict.fromkeys(_safe_error(e) for e in exc.exceptions))
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
        return "request timed out"
    return type(exc).__name__


class StreamableHTTPClient:
    """Keep SDK context managers on one task, including initialization and close.

    A blocking portal makes the synchronous MCPClient usable even when its caller
    already has an event loop. Calls still block that caller; async applications
    should use ``asyncio.to_thread`` when they need concurrent local work.
    """

    def __init__(self, url: str, headers: dict[str, str] | None, timeout: float):
        self.url = url
        self.headers = headers
        self.timeout = timeout
        self._stack: ExitStack | None = None
        self._portal: Any = None
        self._session: Any = None

    @asynccontextmanager
    async def _connection(self):
        import anyio
        import httpx
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async with httpx.AsyncClient(headers=self.headers, timeout=self.timeout, follow_redirects=False) as http:
            async with streamable_http_client(self.url, http_client=http) as (read, write, _):
                async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=self.timeout)) as session:
                    with anyio.fail_after(self.timeout):
                        await session.initialize()
                    yield session

    def connect(self) -> None:
        try:
            from anyio.from_thread import start_blocking_portal
            from mcp.client.streamable_http import streamable_http_client  # noqa: F401
        except ImportError:
            raise ImportError("Streamable HTTP requires: pip install 'stuntdouble[mcp]'") from None

        stack = ExitStack()
        try:
            self._portal = stack.enter_context(start_blocking_portal())
            self._session = stack.enter_context(self._portal.wrap_async_context_manager(self._connection()))
            self._stack = stack
        except Exception as exc:
            try:
                stack.close()
            except Exception:
                pass  # Preserve the initialization failure, not a secondary close error.
            self._portal = self._session = None
            raise RuntimeError(f"Streamable HTTP connection failed: {_safe_error(exc)}") from None

    async def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        import anyio

        with anyio.fail_after(self.timeout):
            if method == "tools/list":
                result = await self._session.list_tools(cursor=params.get("cursor"))
            elif method == "tools/call":
                result = await self._session.call_tool(params["name"], arguments=params.get("arguments", {}))
            else:
                raise ValueError("Unsupported MCP operation")
            return {"result": result.model_dump(mode="json", by_alias=True, exclude_none=True)}

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if self._portal is None:
            raise RuntimeError("Streamable HTTP client is not connected")
        try:
            return cast(dict[str, Any], self._portal.call(self._request, method, params))
        except Exception as exc:
            raise RuntimeError(f"Streamable HTTP request failed: {_safe_error(exc)}") from None

    def close(self) -> None:
        try:
            if self._stack is not None:
                self._stack.close()
        except Exception as exc:
            # The SDK may re-raise a failed request from its background task group
            # during teardown. ExitStack still closes the portal; do not mask the
            # request failure or discard an already received result.
            logger.warning("Streamable HTTP cleanup: %s", _safe_error(exc))
        finally:
            self._stack = self._portal = self._session = None
