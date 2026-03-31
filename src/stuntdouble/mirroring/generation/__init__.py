# ABOUTME: Exposes the mock generation package API for presets, strategies, and generator building blocks.
# ABOUTME: Gives the mirroring subsystem a compact import surface for response generation features.
"""
Mock generation system with strategy pattern.

Provides flexible mock generation through:
- Quality presets (fast/balanced/high)
- Pluggable strategies (Static/Dynamic)
- Smart caching and LLM integration

Quick Start:
    >>> from stuntdouble.mirroring.generation import MockGenerator
    >>>
    >>> # Recommended: Use presets
    >>> gen = MockGenerator.from_preset("balanced")
    >>>
    >>> # With LLM for high quality
    >>> gen = MockGenerator.from_preset("high", llm_client=my_llm)

Advanced:
    >>> from stuntdouble.mirroring.strategies import StaticStrategy
    >>> strategy = StaticStrategy(cache=cache)
    >>> gen = MockGenerator(strategy=strategy)
"""

# Strategies (for power users)
from ..strategies import (
    BaseStrategy,
    DynamicStrategy,
    StaticStrategy,
)

# Main generator
from .base import MockGenerator

# Presets
from .presets import (
    PresetConfig,
    QualityPreset,
    get_preset,
    get_recommended_preset,
    list_presets,
)

__all__ = [
    # Main API
    "MockGenerator",
    # Presets
    "QualityPreset",
    "PresetConfig",
    "get_preset",
    "list_presets",
    "get_recommended_preset",
    # Strategies (power users)
    "BaseStrategy",
    "StaticStrategy",
    "DynamicStrategy",
]
