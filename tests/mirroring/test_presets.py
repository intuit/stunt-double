"""Unit tests for mirroring quality presets."""

import pytest

from stuntdouble.mirroring.generation.presets import (
    PRESETS,
    PresetConfig,
    QualityPreset,
    get_preset,
    get_recommended_preset,
    list_presets,
)
from stuntdouble.mirroring.strategies import (
    DynamicStrategy,
    StaticStrategy,
)


class TestQualityPreset:
    """Tests for QualityPreset enum."""

    def test_values(self):
        """All expected presets exist."""
        assert QualityPreset.FAST.value == "fast"
        assert QualityPreset.BALANCED.value == "balanced"
        assert QualityPreset.HIGH.value == "high"

    def test_from_string(self):
        """Can construct from string."""
        assert QualityPreset("fast") == QualityPreset.FAST
        assert QualityPreset("balanced") == QualityPreset.BALANCED
        assert QualityPreset("high") == QualityPreset.HIGH

    def test_invalid_value_raises(self):
        """Invalid string raises ValueError."""
        with pytest.raises(ValueError):
            QualityPreset("ultra")

    def test_is_str_subclass(self):
        """QualityPreset values are strings."""
        assert isinstance(QualityPreset.FAST.value, str)


class TestPresetConfig:
    """Tests for PresetConfig."""

    def test_basic_construction(self):
        """Can create a PresetConfig."""
        config = PresetConfig(
            name="test",
            description="Test preset",
            strategy_class=StaticStrategy,
            requires_llm=False,
        )
        assert config.name == "test"
        assert config.description == "Test preset"
        assert config.strategy_class is StaticStrategy
        assert config.requires_llm is False

    def test_create_strategy_static(self):
        """Creates StaticStrategy from non-LLM preset."""
        config = PresetConfig(
            name="fast",
            description="Fast",
            strategy_class=StaticStrategy,
            requires_llm=False,
        )
        strategy = config.create_strategy()
        assert isinstance(strategy, StaticStrategy)

    def test_create_strategy_llm_required_without_client_raises(self):
        """Creating LLM strategy without client raises ValueError."""
        config = PresetConfig(
            name="high",
            description="High",
            strategy_class=DynamicStrategy,
            requires_llm=True,
        )
        with pytest.raises(ValueError, match="requires an LLM client"):
            config.create_strategy()

    def test_create_strategy_llm_with_client(self):
        """Creating LLM strategy with client succeeds."""
        config = PresetConfig(
            name="high",
            description="High",
            strategy_class=DynamicStrategy,
            requires_llm=True,
        )

        class FakeLLM:
            pass

        strategy = config.create_strategy(llm_client=FakeLLM())
        assert isinstance(strategy, DynamicStrategy)


class TestPresetsCatalog:
    """Tests for the PRESETS catalog."""

    def test_all_presets_defined(self):
        """All QualityPreset values have a PresetConfig."""
        for preset in QualityPreset:
            assert preset in PRESETS

    def test_fast_preset(self):
        """FAST preset uses StaticStrategy and no LLM."""
        config = PRESETS[QualityPreset.FAST]
        assert config.strategy_class is StaticStrategy
        assert config.requires_llm is False

    def test_balanced_preset(self):
        """BALANCED preset uses StaticStrategy and no LLM."""
        config = PRESETS[QualityPreset.BALANCED]
        assert config.strategy_class is StaticStrategy
        assert config.requires_llm is False

    def test_high_preset(self):
        """HIGH preset uses DynamicStrategy and requires LLM."""
        config = PRESETS[QualityPreset.HIGH]
        assert config.strategy_class is DynamicStrategy
        assert config.requires_llm is True


class TestGetPreset:
    """Tests for get_preset function."""

    def test_get_fast(self):
        """Can get 'fast' preset."""
        config = get_preset("fast")
        assert config.name == "fast"

    def test_get_balanced(self):
        """Can get 'balanced' preset."""
        config = get_preset("balanced")
        assert config.name == "balanced"

    def test_get_high(self):
        """Can get 'high' preset."""
        config = get_preset("high")
        assert config.name == "high"

    def test_case_insensitive(self):
        """get_preset is case-insensitive."""
        config = get_preset("FAST")
        assert config.name == "fast"

    def test_invalid_name_raises(self):
        """Invalid preset name raises ValueError."""
        with pytest.raises(ValueError, match="Invalid preset"):
            get_preset("ultra_mega")


class TestListPresets:
    """Tests for list_presets function."""

    def test_returns_all_presets(self):
        """list_presets returns all preset names."""
        presets = list_presets()
        assert "fast" in presets
        assert "balanced" in presets
        assert "high" in presets

    def test_returns_descriptions(self):
        """Each preset has a non-empty description."""
        presets = list_presets()
        for name, desc in presets.items():
            assert isinstance(desc, str)
            assert len(desc) > 0


class TestGetRecommendedPreset:
    """Tests for get_recommended_preset function."""

    def test_ci_environment(self):
        """CI environments get FAST preset."""
        assert get_recommended_preset(is_ci=True) == QualityPreset.FAST

    def test_ci_overrides_llm(self):
        """CI environment overrides LLM availability."""
        assert get_recommended_preset(has_llm=True, is_ci=True) == QualityPreset.FAST

    def test_llm_available(self):
        """LLM availability recommends HIGH preset."""
        assert get_recommended_preset(has_llm=True) == QualityPreset.HIGH

    def test_needs_params(self):
        """Parameter awareness recommends BALANCED preset."""
        assert get_recommended_preset(needs_params=True) == QualityPreset.BALANCED

    def test_default_fast(self):
        """Default with no special requirements is FAST."""
        assert get_recommended_preset(needs_params=False) == QualityPreset.FAST
