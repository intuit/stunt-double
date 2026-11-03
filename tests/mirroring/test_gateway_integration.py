"""Exercise actual HTTP + SDK sessions without a gateway, IdP or backend process."""

import asyncio
import copy
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from stuntdouble.mirroring.catalog import RegistryCatalogDiscoverer
from stuntdouble.mirroring.mcp_client import MCPClient, MCPServerConfig
from stuntdouble.mirroring.mirror import ToolMirror

pytest.importorskip("mcp")

SCHEMA = {
    "type": "object",
    "properties": {"customer": {"type": "object", "properties": {"id": {"type": "string", "minLength": 1}}}},
    "required": ["customer"],
    "additionalProperties": False,
}


def entry(name="get_customer", path="/crm"):
    return {
        "tool_name": name,
        "server_path": path,
        "server_name": path.strip("/"),
        "description": "Look up a customer",
        "input_schema": copy.deepcopy(SCHEMA),
        "available_versions": ["v1"],
    }


@pytest.fixture
def endpoint():
    original_threads = set(threading.enumerate())
    state = {
        "requests": [],
        "mode": "json",
        "session": True,
        "status": 200,
        "delay": 0,
        "catalog": {"tools": [entry(), entry("list_invoices", "/billing")]},
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, data=b"", content_type="application/json", session=False):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            if state.get("redirect"):
                self.send_header("Location", state["redirect"])
            if session:
                self.send_header("Mcp-Session-Id", "test-session")
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            state["requests"].append(("GET", self.path, dict(self.headers), None))
            if self.path != "/prefix/api/tool-catalog":
                self.reply(405)
                return
            payload = state["catalog"]
            if self.headers.get("Authorization") == "Bearer restricted":
                payload = {"tools": []}
            self.reply(state["status"], json.dumps(payload).encode())

        def do_DELETE(self):
            state["requests"].append(("DELETE", self.path, dict(self.headers), None))
            self.reply(405)  # Session termination is optional.

        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["requests"].append(("POST", self.path, dict(self.headers), data))
            if self.path != "/prefix/virtual/test":
                self.reply(404)
                return
            if state["status"] != 200:
                self.reply(state["status"], b"secret-server-body")
                return
            if "id" not in data:
                self.reply(202)
                return
            method = data["method"]
            if method == "initialize":
                result = {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "fixture", "version": "1"},
                }
            elif method == "tools/list":
                time.sleep(state["delay"])
                second = data.get("params", {}).get("cursor") == "page-2"
                result = {
                    "tools": [
                        {
                            "name": "list_invoices" if second else "get_customer",
                            "description": "Look up a customer",
                            "inputSchema": SCHEMA,
                        }
                    ]
                }
                if not second or state.get("repeat_cursor"):
                    result["nextCursor"] = "page-2"
            else:
                result = {"content": [{"type": "text", "text": "real response"}]}
            body = json.dumps({"jsonrpc": "2.0", "id": data["id"], "result": result}).encode()
            if state["mode"] == "sse":
                # Exercise an SSE notification preceding the response, not just a JSON body.
                notice = b'event: message\ndata: {"jsonrpc":"2.0","method":"notifications/tools/list_changed"}\n\n'
                body = notice + b"event: message\ndata: " + body + b"\n\n"
            self.reply(
                200,
                body,
                "text/event-stream" if state["mode"] == "sse" else "application/json",
                session=state["session"] and method == "initialize",
            )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state["base"] = f"http://127.0.0.1:{server.server_port}/prefix"
    state["url"] = state["base"] + "/virtual/test"
    yield state
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)
    assert not thread.is_alive()
    assert not [t for t in threading.enumerate() if t not in original_threads and "portal" in t.name]


@pytest.mark.parametrize("mode", ["json", "sse"])
@pytest.mark.parametrize("session", [True, False])
def test_transport_lifecycle_pagination_and_headers(endpoint, mode, session):
    endpoint.update(mode=mode, session=session)
    config = MCPServerConfig(
        name="gateway",
        transport="streamable-http",
        http_url=endpoint["url"],
        headers={"Authorization": "Bearer fixture", "X-Test": "retained"},
    )
    client = MCPClient(config)
    with client:
        tools = client.list_tools()
        assert [t.name for t in tools] == ["get_customer", "list_invoices"]
        assert tools[0].input_schema == SCHEMA
        assert client.call_tool("get_customer", {})["content"][0]["text"] == "real response"
    assert client._streamable_client is None
    for method, path, headers, body in endpoint["requests"]:
        headers = {key.lower(): value for key, value in headers.items()}
        assert path == "/prefix/virtual/test"
        assert headers["authorization"] == "Bearer fixture"
        assert headers["x-test"] == "retained"
        if body and body["method"] == "tools/list":
            assert headers["mcp-protocol-version"] == "2025-06-18"
            assert headers.get("mcp-session-id") == ("test-session" if session else None)
    assert any(r[3] and r[3]["method"] == "notifications/initialized" for r in endpoint["requests"])
    assert any(r[0] == "DELETE" for r in endpoint["requests"]) == session


def test_sync_client_inside_running_event_loop(endpoint):
    async def run():
        with MCPClient(MCPServerConfig(name="test", transport="streamable-http", http_url=endpoint["url"])) as client:
            assert len(client.list_tools()) == 2

    asyncio.run(run())


@pytest.mark.parametrize("status", [401, 403])
def test_auth_failure_cleans_up_and_does_not_leak(endpoint, status, caplog):
    endpoint["status"] = status
    client = MCPClient(
        MCPServerConfig(
            name="test",
            transport="streamable-http",
            http_url=endpoint["url"],
            headers={"Authorization": "Bearer secret-token"},
            read_timeout=1,
        )
    )
    with pytest.raises(RuntimeError, match=f"HTTP {status}") as exc:
        client.connect()
    assert not client._connected
    assert client._streamable_client is None
    assert "secret-token" not in str(exc.value) + caplog.text
    assert "secret-server-body" not in str(exc.value) + caplog.text


def test_timeout_and_repeated_cursor(endpoint):
    config = MCPServerConfig(name="test", transport="streamable-http", http_url=endpoint["url"], read_timeout=0.15)
    endpoint["delay"] = 0.5
    with MCPClient(config) as client:
        with pytest.raises(RuntimeError):
            client.list_tools()
    endpoint["delay"] = 0
    endpoint["repeat_cursor"] = True
    with MCPClient(config) as client:
        with pytest.raises(RuntimeError, match="pagination"):
            client.list_tools()


@pytest.mark.parametrize("source", ["http", "catalog"])
def test_discovery_to_langgraph_mock_never_invokes_backend(endpoint, source):
    from langchain_core.messages import AIMessage
    from langgraph.graph import END, START, MessagesState, StateGraph
    from langgraph.prebuilt import ToolNode

    from stuntdouble import create_mockable_tool_wrapper

    mirror = ToolMirror.for_langgraph(quality="fast")
    if source == "http":
        result = mirror.mirror(http_url=endpoint["url"], transport="streamable-http")
    else:
        result = mirror.mirror(registry_url=endpoint["base"])
    assert result["mirrored_count"] == 2
    mirror.customize("get_customer", {"id": "fixture-customer"})
    tools = mirror.to_langchain_tools()
    assert tools[0].args_schema == SCHEMA
    assert tools[0].description == "Look up a customer"
    builder = StateGraph(MessagesState)
    builder.add_node("tools", ToolNode(tools, awrap_tool_call=create_mockable_tool_wrapper(mirror.langgraph_registry)))
    builder.add_edge(START, "tools")
    builder.add_edge("tools", END)
    graph = builder.compile()
    message = AIMessage(
        content="", tool_calls=[{"id": "c1", "name": "get_customer", "args": {"customer": {"id": "C1"}}}]
    )
    output = asyncio.run(
        graph.ainvoke({"messages": [message]}, config={"configurable": {"scenario_metadata": {"scenario_id": "test"}}})
    )
    assert json.loads(output["messages"][-1].content) == {"id": "fixture-customer"}
    assert not any(r[3] and r[3].get("method") == "tools/call" for r in endpoint["requests"])
    if source == "catalog":
        assert len(endpoint["requests"]) == 1  # Only REST: no initialize or backend connection.


def test_catalog_duplicate_names_mapping_provenance_and_identity(endpoint):
    endpoint["catalog"] = {"tools": [entry(), entry(path="/other")]}
    mirror = ToolMirror.for_ci()
    with pytest.raises(ValueError, match="Duplicate"):
        mirror.mirror(registry_url=endpoint["base"])
    assert mirror.list_mirrors() == []
    mapping = {("/crm", "get_customer"): "crm_customer", ("/other", "get_customer"): "other_customer"}
    result = mirror.mirror(registry_url=endpoint["base"], tool_name_map=mapping)
    assert result["tools"] == ["crm_customer", "other_customer"]
    definition = mirror.registry.get_tool_definition("crm_customer")
    assert definition.metadata["server_path"] == "/crm"
    assert definition.metadata["original_tool_name"] == "get_customer"
    assert definition.metadata["available_versions"] == ["v1"]
    definition.input_schema.clear()
    assert mirror.registry.get_tool_definition("crm_customer").input_schema == SCHEMA
    # No cached catalog is shared between caller identities.
    with pytest.raises(ValueError, match="fresh ToolMirror"):
        mirror.mirror(registry_url=endpoint["base"], headers={"Authorization": "Bearer restricted"})
    restricted = ToolMirror.for_ci()
    assert (
        restricted.mirror(registry_url=endpoint["base"], headers={"Authorization": "Bearer restricted"})["tools"] == []
    )
    assert restricted.list_mirrors() == []
    with pytest.raises(ValueError, match="already registered"):
        mirror.mirror(registry_url=endpoint["base"], tool_name_map=mapping)


@pytest.mark.parametrize("payload", [{}, {"tools": None}, {"tools": [None]}, {"tools": [entry(), {}]}])
def test_catalog_invalid_payload_has_no_partial_registration(endpoint, payload):
    endpoint["catalog"] = payload
    mirror = ToolMirror.for_ci()
    with pytest.raises(ValueError):
        mirror.mirror(registry_url=endpoint["base"])
    assert mirror.list_mirrors() == []


def test_catalog_missing_upstream_schema_fails_without_partial_registration(endpoint):
    missing_schema = entry("missing_schema")
    missing_schema["input_schema"] = {}
    endpoint["catalog"] = {"tools": [entry(), missing_schema]}
    mirror = ToolMirror.for_ci()

    with pytest.raises(ValueError, match="empty input_schema.*Streamable HTTP"):
        mirror.mirror(registry_url=endpoint["base"])

    assert mirror.list_mirrors() == []


def test_catalog_preserves_explicit_no_argument_tool_schema(endpoint):
    no_arguments = {"type": "object", "properties": {}, "additionalProperties": False}
    tool = entry()
    tool["input_schema"] = no_arguments
    endpoint["catalog"] = {"tools": [tool]}
    mirror = ToolMirror.for_ci()

    assert mirror.mirror(registry_url=endpoint["base"])["mirrored_count"] == 1
    assert mirror.to_langchain_tools()[0].args_schema == no_arguments


@pytest.mark.parametrize("status", [302, 401, 403, 500])
def test_catalog_errors_never_become_empty_success(endpoint, status):
    endpoint["status"] = status
    with pytest.raises(RuntimeError, match=f"HTTP {status}"):
        ToolMirror.for_ci().mirror(registry_url=endpoint["base"])


def test_catalog_mapping_typos_and_missing_selection(endpoint):
    with pytest.raises(ValueError, match="absent"):
        RegistryCatalogDiscoverer.parse(endpoint["catalog"], tool_name_map={("/missing", "tool"): "x"})
    mirror = ToolMirror.for_ci()
    with pytest.raises(ValueError, match="absent"):
        mirror.mirror(registry_url=endpoint["base"], tools=["missing"])
    assert mirror.list_mirrors() == []
    assert mirror.mirror(registry_url=endpoint["base"], tools=[])["mirrored_count"] == 0


def test_source_conflicts_and_invalid_config(endpoint):
    mirror = ToolMirror.for_ci()
    with pytest.raises(ValueError, match="cannot be combined"):
        mirror.mirror(registry_url=endpoint["base"], http_url=endpoint["url"])
    with pytest.raises(ValueError, match="require"):
        mirror.mirror(["python"], transport="streamable-http")
    for timeout in [0, -1, float("inf"), float("nan")]:
        with pytest.raises(ValueError):
            MCPServerConfig(name="test", transport="streamable-http", http_url=endpoint["url"], read_timeout=timeout)


def test_definition_survives_metadata_roundtrip(endpoint, tmp_path):
    from stuntdouble.mirroring.mirror_registry import MirroredToolRegistry

    mirror = ToolMirror.for_ci()
    mirror.registry = MirroredToolRegistry(storage_dir=tmp_path)
    mirror.mirror(registry_url=endpoint["base"])
    restored = MirroredToolRegistry(storage_dir=tmp_path)
    assert restored.get_tool_definition("get_customer").input_schema == SCHEMA
    assert restored.get_tool_definition("get_customer").metadata["server_path"] == "/crm"


def test_cross_origin_redirect_is_not_followed(endpoint):
    endpoint.update(status=307, redirect="http://127.0.0.1:1/must-not-receive-token")
    config = MCPServerConfig(
        name="redirect",
        transport="streamable-http",
        http_url=endpoint["url"],
        headers={"Authorization": "Bearer fixture"},
        read_timeout=1,
    )
    with pytest.raises(RuntimeError, match="HTTP 307"):
        MCPClient(config).connect()
    assert len(endpoint["requests"]) == 1


def test_catalog_generation_failure_rolls_back_new_tools(endpoint, monkeypatch):
    mirror = ToolMirror.for_langgraph(quality="fast")
    original = mirror._mirror_tool

    def fail_second(definition, config):
        if definition.name == "list_invoices":
            raise RuntimeError("generation failed")
        return original(definition, config)

    monkeypatch.setattr(mirror, "_mirror_tool", fail_second)
    with pytest.raises(RuntimeError, match="generation failed"):
        mirror.mirror(registry_url=endpoint["base"])
    assert mirror.list_mirrors() == []
    assert mirror.registry.list_mock_functions() == {}
    assert mirror.langgraph_registry.list_registered() == []


def test_catalog_persistence_treats_remote_names_as_data(endpoint, tmp_path):
    from stuntdouble.mirroring.mirror_registry import MirroredToolRegistry

    remote = entry("../../outside", "/unusual")
    remote["server_name"] = "../outside"
    endpoint["catalog"] = {"tools": [remote]}
    mirror = ToolMirror.for_ci()
    mirror.registry = MirroredToolRegistry(storage_dir=tmp_path)
    mirror.mirror(registry_url=endpoint["base"])
    files = list(tmp_path.rglob("*.json"))
    assert len(files) == 1
    assert files[0].resolve().is_relative_to(tmp_path.resolve())
    assert MirroredToolRegistry(storage_dir=tmp_path).get_tool_definition("../../outside").name == "../../outside"
