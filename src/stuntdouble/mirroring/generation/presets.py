"""
Quality presets for mock generation.

Provides predefined configurations for different quality/speed tradeoffs:
- fast: Static schema-based mocks (CI/CD)
- balanced: Static parameter-aware mocks (default)
- high: LLM-powered realistic mocks (evaluation)
"""

import logging
from enum import Enum
from typing import Any

from ..strategies import BaseStrategy, DynamicStrategy, StaticStrategy

logger = logging.getLogger(__name__)


class QualityPreset(str, Enum):
    """
    Quality preset levels for mock generation.

    Each preset balances speed, realism, and resource usage:
    - FAST: Fastest, static templates, no external calls
    - BALANCED: Good balance, parameter-aware, uses static templates
    - HIGH: Highest quality, LLM-powered, requires LLM client
    """

    FAST = "fast"
    BALANCED = "balanced"
    HIGH = "high"


class PresetConfig:
    """
    Configuration for a quality preset.

    Encapsulates the strategy and settings for each preset level.
    """

    def __init__(
        self,
        name: str,
        description: str,
        strategy_class: type,
        requires_llm: bool = False,
    ):
        """
        Initialize preset configuration.

        Args:
            name: Preset name
            description: Human-readable description
            strategy_class: Strategy class to use
            requires_llm: Whether this preset requires an LLM client
        """
        self.name = name
        self.description = description
        self.strategy_class = strategy_class
        self.requires_llm = requires_llm

    def create_strategy(
        self, llm_client: Any | None = None, cache: Any | None = None
    ) -> BaseStrategy:
        """
        Create a strategy instance for this preset.

        Args:
            llm_client: Optional LLM client (required for HIGH preset)
            cache: Optional cache instance

        Returns:
            Configured strategy instance

        Raises:
            ValueError: If LLM client required but not provided
        """
        if self.requires_llm:
            if llm_client is None:
                raise ValueError(
                    f"Preset '{self.name}' requires an LLM client. "
                    f"Use ToolMirror.with_llm(client) or .enable_llm(client)"
                )
            return self.strategy_class(llm_client=llm_client, cache=cache)
        else:
            return self.strategy_class(cache=cache)


# Predefined quality presets
PRESETS: dict[QualityPreset, PresetConfig] = {
    QualityPreset.FAST: PresetConfig(
        name="fast",
        description="Fast static mocks - Best for CI/CD, deterministic testing",
        strategy_class=StaticStrategy,
        requires_llm=False,
    ),
    QualityPreset.BALANCED: PresetConfig(
        name="balanced",
        description="Balanced parameter-aware mocks - Good for most use cases",
        strategy_class=StaticStrategy,
        requires_llm=False,
    ),
    QualityPreset.HIGH: PresetConfig(
        name="high",
        description="High-quality LLM mocks - Best for evaluation, realistic testing",
        strategy_class=DynamicStrategy,
        requires_llm=True,
    ),
}


def get_preset(preset: str) -> PresetConfig:
    """
    Get preset configuration by name.

    Args:
        preset: Preset name ("fast", "balanced", or "high")

    Returns:
        PresetConfig instance

    Raises:
        ValueError: If preset name is invalid

    Example:
        >>> config = get_preset("balanced")
        >>> strategy = config.create_strategy(cache=my_cache)
    """
    try:
        preset_enum = QualityPreset(preset.lower())
        return PRESETS[preset_enum]
    except (ValueError, KeyError):
        valid = ", ".join([p.value for p in QualityPreset])
        raise ValueError(f"Invalid preset: '{preset}'. Valid options: {valid}")


def list_presets() -> dict[str, str]:
    """
    List all available presets with descriptions.

    Returns:
        Dictionary mapping preset names to descriptions

    Example:
        >>> presets = list_presets()
        >>> for name, desc in presets.items():
        ...     print(f"{name}: {desc}")
        fast: Fast static mocks - Best for CI/CD, deterministic testing
        balanced: Balanced parameter-aware mocks - Good for most use cases
        high: High-quality LLM mocks - Best for evaluation, realistic testing
    """
    return {preset.value: config.description for preset, config in PRESETS.items()}


def get_recommended_preset(
    has_llm: bool = False,
    is_ci: bool = False,
    needs_params: bool = True,
) -> QualityPreset:
    """
    Get recommended preset based on environment and requirements.

    Args:
        has_llm: Whether an LLM client is available
        is_ci: Whether running in CI/CD environment
        needs_params: Whether parameter awareness is needed

    Returns:
        Recommended QualityPreset

    Example:
        >>> # CI environment
        >>> preset = get_recommended_preset(is_ci=True)
        >>> assert preset == QualityPreset.FAST
        >>>
        >>> # LLM available, want quality
        >>> preset = get_recommended_preset(has_llm=True)
        >>> assert preset == QualityPreset.HIGH
    """
    if is_ci:
        logger.info("CI environment detected - recommending FAST preset")
        return QualityPreset.FAST

    if has_llm:
        logger.info("LLM available - recommending HIGH preset")
        return QualityPreset.HIGH

    if needs_params:
        logger.info("Parameter awareness needed - recommending BALANCED preset")
        return QualityPreset.BALANCED

    logger.info("Using default FAST preset")
    return QualityPreset.FAST


__all__ = [
    "QualityPreset",
    "PresetConfig",
    "PRESETS",
    "get_preset",
    "list_presets",
    "get_recommended_preset",
]
