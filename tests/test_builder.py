"""Tests for MockBuilder fluent API."""

from __future__ import annotations

import pytest

from stuntdouble.builder import MockBuilder
from stuntdouble.exceptions import InputNotMatchedError
from stuntdouble.mock_registry import MockToolsRegistry


class TestReturns:
    def test_static_returns(self):
        registry = MockToolsRegistry()
        registry.mock("get_weather").returns({"temp": 72})

        fn = registry.resolve("get_weather", {})
        assert fn is not None
        assert fn() == {"temp": 72}

    def test_returns_deep_copies(self):
        registry = MockToolsRegistry()
        registry.mock("tool").returns({"items": [1, 2, 3]})

        fn = registry.resolve("tool", {})
        assert fn is not None
        result1 = fn()
        result1["items"].append(99)
        result2 = fn()
        assert result2 == {"items": [1, 2, 3]}

    def test_returns_string(self):
        registry = MockToolsRegistry()
        registry.mock("tool").returns("hello")

        fn = registry.resolve("tool", {})
        assert fn is not None
        assert fn() == "hello"

    def test_returns_list(self):
        registry = MockToolsRegistry()
        registry.mock("tool").returns([1, 2, 3])

        fn = registry.resolve("tool", {})
        assert fn is not None
        assert fn() == [1, 2, 3]


class TestReturnsFn:
    def test_returns_fn(self):
        registry = MockToolsRegistry()
        registry.mock("calc").returns_fn(lambda items, tax: {"total": sum(items) * (1 + tax)})

        fn = registry.resolve("calc", {})
        assert fn is not None
        assert fn(items=[100, 200], tax=0.1) == {"total": 330.0}

    def test_returns_fn_no_args(self):
        registry = MockToolsRegistry()
        registry.mock("ping").returns_fn(lambda: "pong")

        fn = registry.resolve("ping", {})
        assert fn is not None
        assert fn() == "pong"


class TestEchoesInput:
    def test_echoes_single_field(self):
        registry = MockToolsRegistry()
        registry.mock("update").echoes_input("customer_id").returns({"updated": True})

        fn = registry.resolve("update", {})
        assert fn is not None
        result = fn(customer_id="C1", name="Acme")
        assert result == {"updated": True, "customer_id": "C1"}

    def test_echoes_multiple_fields(self):
        registry = MockToolsRegistry()
        registry.mock("update").echoes_input("id", "name").returns({"ok": True})

        fn = registry.resolve("update", {})
        assert fn is not None
        result = fn(id="1", name="Test", extra="ignored")
        assert result == {"ok": True, "id": "1", "name": "Test"}

    def test_echoes_missing_field_skipped(self):
        registry = MockToolsRegistry()
        registry.mock("tool").echoes_input("a", "b").returns({"x": 1})

        fn = registry.resolve("tool", {})
        assert fn is not None
        result = fn(a="val")
        assert result == {"x": 1, "a": "val"}

    def test_echoes_with_non_dict_returns_unchanged(self):
        registry = MockToolsRegistry()
        registry.mock("tool").echoes_input("a").returns("string_value")

        fn = registry.resolve("tool", {})
        assert fn is not None
        assert fn(a="val") == "string_value"


class TestWhen:
    def test_when_scenario_predicate(self):
        registry = MockToolsRegistry()
        registry.mock("send_email").when(lambda md: md.get("mode") == "test").returns({"sent": True})

        # Should resolve when predicate matches
        fn = registry.resolve("send_email", {"mode": "test"})
        assert fn is not None
        assert fn() == {"sent": True}

        # Should not resolve when predicate doesn't match
        fn = registry.resolve("send_email", {"mode": "production"})
        assert fn is None

    def test_when_input_conditions(self):
        registry = MockToolsRegistry()
        registry.mock("get_bills").when(status="active").returns({"bills": []})

        fn = registry.resolve("get_bills", {})
        assert fn is not None
        assert fn(status="active") == {"bills": []}
        with pytest.raises(InputNotMatchedError):
            fn(status="inactive")

    def test_when_with_operators(self):
        registry = MockToolsRegistry()
        registry.mock("query").when(amount={"$gt": 1000}).returns({"tier": "high"})

        fn = registry.resolve("query", {})
        assert fn is not None
        assert fn(amount=1500) == {"tier": "high"}
        with pytest.raises(InputNotMatchedError):
            fn(amount=500)

    def test_when_predicate_and_conditions(self):
        registry = MockToolsRegistry()
        registry.mock("tool").when(
            lambda md: md.get("mode") == "test",
            status="active",
        ).returns({"result": "ok"})

        # Predicate matches -> resolved
        fn = registry.resolve("tool", {"mode": "test"})
        assert fn is not None

        # Predicate doesn't match -> not resolved
        fn = registry.resolve("tool", {"mode": "prod"})
        assert fn is None


class TestChaining:
    def test_full_chain(self):
        registry = MockToolsRegistry()
        registry.mock("update_customer").when(lambda md: "update_customer" in md.get("mocks", {})).echoes_input(
            "customer_id"
        ).returns({"updated": True})

        fn = registry.resolve("update_customer", {"mocks": {"update_customer": []}})
        assert fn is not None
        result = fn(customer_id="C-123", name="Test")
        assert result == {"updated": True, "customer_id": "C-123"}


class TestImports:
    def test_import_from_top_level(self):
        from stuntdouble import MockBuilder

        assert MockBuilder is not None

    def test_import_from_builder_module(self):
        from stuntdouble.builder import MockBuilder

        assert MockBuilder is not None


class TestMockMethod:
    def test_returns_mock_builder(self):
        registry = MockToolsRegistry()
        builder = registry.mock("tool")
        assert isinstance(builder, MockBuilder)

    def test_registers_on_registry(self):
        registry = MockToolsRegistry()
        registry.mock("my_tool").returns("ok")
        assert registry.is_registered("my_tool")
