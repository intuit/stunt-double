"""Tests for MockStrategy enum extensions (STORY-DMG-1.1)."""

from datetime import datetime

import pytest

from stuntdouble.mirroring.models import MirrorMetadata, MockStrategy


class TestMockStrategyEnum:
    """Test suite for MockStrategy enum with LLM_DYNAMIC addition."""

    def test_llm_dynamic_strategy_exists(self):
        """Verify LLM_DYNAMIC enum value exists."""
        assert hasattr(MockStrategy, "LLM_DYNAMIC")
        assert MockStrategy.LLM_DYNAMIC.value == "llm_dynamic"

    def test_enum_has_five_values(self):
        """Verify enum has exactly 5 values."""
        strategies = list(MockStrategy)
        assert len(strategies) == 5

        expected_values = ["schema", "proxy", "live", "custom", "llm_dynamic"]
        actual_values = [s.value for s in strategies]
        assert set(actual_values) == set(expected_values)

    def test_strategy_from_string(self):
        """Test creating MockStrategy from string value."""
        strategy = MockStrategy("llm_dynamic")
        assert strategy == MockStrategy.LLM_DYNAMIC

    def test_all_strategies_have_string_values(self):
        """Verify all strategy values are strings."""
        for strategy in MockStrategy:
            assert isinstance(strategy.value, str)

    def test_strategy_equality(self):
        """Test strategy equality comparisons."""
        assert MockStrategy.LLM_DYNAMIC == MockStrategy("llm_dynamic")
        assert MockStrategy.LLM_DYNAMIC != MockStrategy.SCHEMA_ONLY  # type: ignore[comparison-overlap]

    def test_strategy_in_collection(self):
        """Test strategy can be used in collections."""
        strategies = {MockStrategy.LLM_DYNAMIC, MockStrategy.SCHEMA_ONLY}
        assert MockStrategy.LLM_DYNAMIC in strategies
        assert len(strategies) == 2


class TestMirrorMetadataSerializationWithLLMDynamic:
    """Test MirrorMetadata serialization/deserialization with LLM_DYNAMIC."""

    def test_mirror_metadata_to_dict_with_llm_dynamic(self):
        """Test MirrorMetadata.to_dict() with LLM_DYNAMIC strategy."""
        metadata = MirrorMetadata(
            tool_name="test_tool",
            server_name="test-server",
            server_command=["python", "-m", "server"],
            strategy=MockStrategy.LLM_DYNAMIC,
            created_at=datetime(2024, 1, 1, 12, 0, 0),
            updated_at=datetime(2024, 1, 1, 12, 0, 0),
            schema_version="v1",
            custom_data_set=False,
        )

        data = metadata.to_dict()

        assert data["strategy"] == "llm_dynamic"
        assert data["tool_name"] == "test_tool"
        assert data["server_name"] == "test-server"

    def test_mirror_metadata_from_dict_with_llm_dynamic(self):
        """Test MirrorMetadata.from_dict() with llm_dynamic strategy."""
        data = {
            "tool_name": "test_tool",
            "server_name": "test-server",
            "server_command": ["python", "-m", "server"],
            "strategy": "llm_dynamic",
            "created_at": "2024-01-01T12:00:00",
            "updated_at": "2024-01-01T12:00:00",
            "schema_version": "v1",
            "custom_data_set": False,
        }

        metadata = MirrorMetadata.from_dict(data)

        assert metadata.strategy == MockStrategy.LLM_DYNAMIC
        assert metadata.tool_name == "test_tool"
        assert metadata.server_name == "test-server"

    def test_roundtrip_serialization_llm_dynamic(self):
        """Test roundtrip serialization with LLM_DYNAMIC."""
        original = MirrorMetadata(
            tool_name="test_tool",
            server_name="test-server",
            server_command=["python", "-m", "server"],
            strategy=MockStrategy.LLM_DYNAMIC,
            schema_version="v1",
            custom_data_set=True,
        )

        # Convert to dict and back
        data = original.to_dict()
        restored = MirrorMetadata.from_dict(data)

        assert restored.strategy == MockStrategy.LLM_DYNAMIC
        assert restored.tool_name == original.tool_name
        assert restored.server_name == original.server_name
        assert restored.custom_data_set == original.custom_data_set

    def test_all_strategies_serializable(self):
        """Test all strategies can be serialized/deserialized."""
        for strategy in MockStrategy:
            metadata = MirrorMetadata(
                tool_name=f"test_{strategy.value}",
                server_name="test-server",
                server_command=["python"],
                strategy=strategy,
            )

            data = metadata.to_dict()
            restored = MirrorMetadata.from_dict(data)

            assert restored.strategy == strategy


class TestBackwardCompatibility:
    """Test backward compatibility with existing code."""

    def test_existing_strategies_unchanged(self):
        """Verify existing strategy values haven't changed."""
        assert MockStrategy.SCHEMA_ONLY.value == "schema"
        assert MockStrategy.PROXY_CACHE.value == "proxy"
        assert MockStrategy.PROXY_ALWAYS.value == "live"
        assert MockStrategy.CUSTOM.value == "custom"

    def test_can_iterate_all_strategies(self):
        """Test iteration over all strategies still works."""
        strategies = list(MockStrategy)
        assert len(strategies) == 5

        # All should be MockStrategy instances
        for s in strategies:
            assert isinstance(s, MockStrategy)

    def test_strategy_names(self):
        """Test strategy names are correct."""
        assert MockStrategy.SCHEMA_ONLY.name == "SCHEMA_ONLY"
        assert MockStrategy.PROXY_CACHE.name == "PROXY_CACHE"
        assert MockStrategy.PROXY_ALWAYS.name == "PROXY_ALWAYS"
        assert MockStrategy.CUSTOM.name == "CUSTOM"
        assert MockStrategy.LLM_DYNAMIC.name == "LLM_DYNAMIC"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
