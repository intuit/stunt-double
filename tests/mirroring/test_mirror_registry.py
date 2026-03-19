"""
Tests for MirroredToolRegistry.

Covers lifecycle management, mock function storage, LangGraph integration,
persistence to disk, and server-scoped clear.
"""

from pathlib import Path
from unittest.mock import MagicMock

from stuntdouble.mirroring.mirror_registry import MirroredToolRegistry
from stuntdouble.mirroring.models import (
    MirrorMetadata,
    MockImplementation,
    MockStrategy,
    ToolDefinition,
)


def _tool_def(name: str = "get_customer") -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=f"Execute {name}",
        input_schema={"type": "object", "properties": {}},
        server_name="test-server",
    )


def _mock_impl(name: str = "get_customer") -> MockImplementation:
    return MockImplementation(
        tool_name=name,
        function_code="def mock(): pass",
        mock_data={"id": "123", "status": "ok"},
        metadata=MirrorMetadata(
            tool_name=name,
            server_name="test-server",
            server_command=["python", "-m", "test_server"],
            strategy=MockStrategy.SCHEMA_ONLY,
        ),
    )


class TestMirroredToolRegistryInMemory:
    """In-memory (no persistence) registry operations."""

    def test_register_and_get_mock_function(self):
        registry = MirroredToolRegistry()
        registry.register_mirrored_tool(
            _tool_def(), _mock_impl(), _mock_impl().metadata
        )

        fn = registry.get_mock_function("get_customer")
        assert fn is not None
        result = fn()
        assert result == {"id": "123", "status": "ok"}

    def test_list_mock_functions(self):
        registry = MirroredToolRegistry()
        registry.register_mirrored_tool(
            _tool_def("a"), _mock_impl("a"), _mock_impl("a").metadata
        )
        registry.register_mirrored_tool(
            _tool_def("b"), _mock_impl("b"), _mock_impl("b").metadata
        )

        mocks = registry.list_mock_functions()
        assert set(mocks.keys()) == {"a", "b"}

    def test_get_mock_function_missing(self):
        registry = MirroredToolRegistry()
        assert registry.get_mock_function("nonexistent") is None

    def test_get_mirror_info(self):
        registry = MirroredToolRegistry()
        registry.register_mirrored_tool(
            _tool_def(), _mock_impl(), _mock_impl().metadata
        )

        info = registry.get_mirror_info("get_customer")
        assert info is not None
        assert info.tool_name == "get_customer"
        assert info.server_name == "test-server"
        assert info.strategy == MockStrategy.SCHEMA_ONLY

    def test_get_mirror_info_missing(self):
        registry = MirroredToolRegistry()
        assert registry.get_mirror_info("nonexistent") is None

    def test_list_mirrors(self):
        registry = MirroredToolRegistry()
        registry.register_mirrored_tool(
            _tool_def("a"), _mock_impl("a"), _mock_impl("a").metadata
        )
        registry.register_mirrored_tool(
            _tool_def("b"), _mock_impl("b"), _mock_impl("b").metadata
        )

        mirrors = registry.list_mirrors()
        assert len(mirrors) == 2
        names = {m.tool_name for m in mirrors}
        assert names == {"a", "b"}

    def test_list_mirrors_by_server(self):
        registry = MirroredToolRegistry()

        td = _tool_def("a")
        td.server_name = "server-alpha"
        mi = _mock_impl("a")
        mi.metadata.server_name = "server-alpha"
        registry.register_mirrored_tool(td, mi, mi.metadata)

        td2 = _tool_def("b")
        mi2 = _mock_impl("b")
        registry.register_mirrored_tool(td2, mi2, mi2.metadata)

        alpha_mirrors = registry.list_mirrors_by_server("server-alpha")
        assert len(alpha_mirrors) == 1
        assert alpha_mirrors[0].tool_name == "a"

    def test_unregister_mirror(self):
        registry = MirroredToolRegistry()
        registry.register_mirrored_tool(
            _tool_def(), _mock_impl(), _mock_impl().metadata
        )

        result = registry.unregister_mirror("get_customer")
        assert result is True
        assert registry.get_mock_function("get_customer") is None
        assert registry.get_mirror_info("get_customer") is None

    def test_unregister_nonexistent(self):
        registry = MirroredToolRegistry()
        assert registry.unregister_mirror("ghost") is False

    def test_clear_all(self):
        registry = MirroredToolRegistry()
        registry.register_mirrored_tool(
            _tool_def("a"), _mock_impl("a"), _mock_impl("a").metadata
        )
        registry.register_mirrored_tool(
            _tool_def("b"), _mock_impl("b"), _mock_impl("b").metadata
        )

        count = registry.clear()
        assert count == 2
        assert registry.list_mock_functions() == {}

    def test_clear_by_server(self):
        registry = MirroredToolRegistry()

        td_alpha = _tool_def("a")
        mi_alpha = _mock_impl("a")
        mi_alpha.metadata.server_name = "alpha"
        registry.register_mirrored_tool(td_alpha, mi_alpha, mi_alpha.metadata)
        registry._metadata_cache["a"].server_name = "alpha"

        td_beta = _tool_def("b")
        mi_beta = _mock_impl("b")
        mi_beta.metadata.server_name = "beta"
        registry.register_mirrored_tool(td_beta, mi_beta, mi_beta.metadata)
        registry._metadata_cache["b"].server_name = "beta"

        cleared = registry.clear("alpha")
        assert cleared == 1
        assert registry.get_mock_function("a") is None
        assert registry.get_mock_function("b") is not None

    def test_get_server_list(self):
        registry = MirroredToolRegistry()

        mi1 = _mock_impl("a")
        mi1.metadata.server_name = "server-x"
        registry.register_mirrored_tool(_tool_def("a"), mi1, mi1.metadata)

        mi2 = _mock_impl("b")
        mi2.metadata.server_name = "server-y"
        registry.register_mirrored_tool(_tool_def("b"), mi2, mi2.metadata)

        servers = registry.get_server_list()
        assert servers == ["server-x", "server-y"]


class TestMirroredToolRegistryWithLangGraph:
    """Tests for LangGraph registry integration."""

    def test_registers_in_langgraph_registry(self):
        lg_registry = MagicMock()
        registry = MirroredToolRegistry(langgraph_registry=lg_registry)
        registry.register_mirrored_tool(
            _tool_def(), _mock_impl(), _mock_impl().metadata
        )

        lg_registry.register.assert_called_once()
        call_args = lg_registry.register.call_args
        assert call_args[0][0] == "get_customer"
        assert "mock_fn" in call_args[1]

    def test_unregister_removes_from_langgraph(self):
        lg_registry = MagicMock()
        registry = MirroredToolRegistry(langgraph_registry=lg_registry)
        registry.register_mirrored_tool(
            _tool_def(), _mock_impl(), _mock_impl().metadata
        )

        registry.unregister_mirror("get_customer")
        lg_registry.unregister.assert_called_once_with("get_customer")

    def test_clear_clears_langgraph_registry(self):
        lg_registry = MagicMock()
        registry = MirroredToolRegistry(langgraph_registry=lg_registry)
        registry.register_mirrored_tool(
            _tool_def(), _mock_impl(), _mock_impl().metadata
        )

        registry.clear()
        lg_registry.clear.assert_called_once()

    def test_langgraph_property(self):
        lg_registry = MagicMock()
        registry = MirroredToolRegistry(langgraph_registry=lg_registry)
        assert registry.langgraph_registry is lg_registry

    def test_langgraph_property_none(self):
        registry = MirroredToolRegistry()
        assert registry.langgraph_registry is None


class TestMirroredToolRegistryPersistence:
    """Tests for disk persistence."""

    def test_save_and_reload(self, tmp_path: Path):
        registry = MirroredToolRegistry(storage_dir=tmp_path / "mirrors")
        mi = _mock_impl()
        registry.register_mirrored_tool(_tool_def(), mi, mi.metadata)

        registry2 = MirroredToolRegistry(storage_dir=tmp_path / "mirrors")
        info = registry2.get_mirror_info("get_customer")
        assert info is not None
        assert info.server_name == "test-server"

    def test_unregister_deletes_file(self, tmp_path: Path):
        registry = MirroredToolRegistry(storage_dir=tmp_path / "mirrors")
        mi = _mock_impl()
        registry.register_mirrored_tool(_tool_def(), mi, mi.metadata)

        metadata_file = tmp_path / "mirrors" / "test-server" / "get_customer.json"
        assert metadata_file.exists()

        registry.unregister_mirror("get_customer")
        assert not metadata_file.exists()

    def test_clear_removes_directory(self, tmp_path: Path):
        registry = MirroredToolRegistry(storage_dir=tmp_path / "mirrors")
        mi = _mock_impl()
        registry.register_mirrored_tool(_tool_def(), mi, mi.metadata)

        registry.clear("test-server")
        assert not (tmp_path / "mirrors" / "test-server").exists()


class TestMirroredToolRegistryDynamic:
    """Tests for dynamic mock generation."""

    def test_dynamic_generation_with_generator(self):
        generator = MagicMock()
        generator.generate_dynamic_mock.return_value = {"dynamic": True}

        registry = MirroredToolRegistry(generator=generator)
        td = _tool_def()
        mi = _mock_impl()
        registry.register_mirrored_tool(td, mi, mi.metadata, enable_dynamic=True)

        fn = registry.get_mock_function("get_customer")
        assert fn is not None
        result = fn(customer_id="C1")
        assert result == {"dynamic": True}
        generator.generate_dynamic_mock.assert_called_once()

    def test_static_fallback_without_generator(self):
        registry = MirroredToolRegistry()
        mi = _mock_impl()
        registry.register_mirrored_tool(
            _tool_def(), mi, mi.metadata, enable_dynamic=True
        )

        fn = registry.get_mock_function("get_customer")
        assert fn is not None
        result = fn()
        assert result == {"id": "123", "status": "ok"}
