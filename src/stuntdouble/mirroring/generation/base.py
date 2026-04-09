# ABOUTME: Coordinates mock generation by routing requests through the selected mirroring strategy.
# ABOUTME: Provides the shared generator foundation used by static and dynamic response builders.
"""
Strategy-based mock generator.

Coordinates mock generation using pluggable strategies:
- StaticStrategy: Fast schema-based mocks with parameter awareness
- DynamicStrategy: LLM-powered high-quality mocks
"""

import logging
from typing import Any

from ..models import (
    MirrorMetadata,
    MockImplementation,
    MockStrategy,
    ToolAnalysis,
    ToolDefinition,
)
from ..strategies import BaseStrategy, DynamicStrategy, StaticStrategy
from .presets import get_preset

logger = logging.getLogger(__name__)


class MockGenerator:
    """
    Strategy-based mock generator.

    Generates mock implementations using pluggable strategies based on
    quality presets (fast/balanced/high). Provides both static mock
    generation (for registration) and dynamic mock generation (for runtime).

    Quality Presets:
    - fast: Static schema-based (CI/CD)
    - balanced: Static parameter-aware (default)
    - high: LLM-powered realistic (evaluation)

    Example:
        >>> # Simple usage with preset
        >>> generator = MockGenerator.from_preset("balanced")
        >>> mock_impl = generator.generate_mock(tool_def, analysis)
        >>>
        >>> # With LLM for high quality
        >>> generator = MockGenerator.from_preset("high", llm_client=client)
        >>> response = generator.generate_dynamic_mock(tool_def, {"id": "123"})
        >>>
        >>> # Custom strategy
        >>> strategy = StaticStrategy(cache=cache)
        >>> generator = MockGenerator(strategy=strategy)
    """

    def __init__(
        self,
        strategy: BaseStrategy | None = None,
        cache: Any | None = None,
    ):
        """
        Initialize mock generator with a strategy.

        Args:
            strategy: Optional strategy instance (default: StaticStrategy)
            cache: Optional cache instance

        Note:
            It's recommended to use from_preset() for most use cases.
        """
        self.cache = cache

        # Use provided strategy or default to StaticStrategy
        if strategy:
            self.strategy = strategy
        else:
            self.strategy = StaticStrategy(cache=cache)

        # For backwards compatibility, keep static generator
        self.static_generator = StaticStrategy()

        # LLM statistics (for DynamicStrategy)
        self._llm_calls = 0
        self._cache_hits = 0

        logger.info(f"MockGenerator initialized with {self.strategy.name}")

    @classmethod
    def from_preset(
        cls,
        preset: str,
        llm_client: Any | None = None,
        cache: Any | None = None,
    ) -> "MockGenerator":
        """
        Create MockGenerator from a quality preset.

        Args:
            preset: Quality preset ("fast", "balanced", or "high")
            llm_client: LLM client (required for "high" preset)
            cache: Optional cache instance

        Returns:
            Configured MockGenerator instance

        Raises:
            ValueError: If preset is invalid or LLM required but not provided

        Example:
            >>> # Balanced preset (default)
            >>> gen = MockGenerator.from_preset("balanced")
            >>>
            >>> # High quality with LLM
            >>> gen = MockGenerator.from_preset("high", llm_client=my_llm)
            >>>
            >>> # Fast for CI
            >>> gen = MockGenerator.from_preset("fast")
        """
        config = get_preset(preset)
        strategy = config.create_strategy(llm_client=llm_client, cache=cache)
        return cls(strategy=strategy, cache=cache)

    @classmethod
    def from_config(
        cls,
        quality: str = "balanced",
        llm_client: Any | None = None,
        cache: Any | None = None,
    ) -> "MockGenerator":
        """
        Create MockGenerator from configuration dict.

        Convenience method for creating generators from config-like parameters.

        Args:
            quality: Quality preset name
            llm_client: Optional LLM client
            cache: Optional cache instance

        Returns:
            Configured MockGenerator instance

        Example:
            >>> config = {"quality": "high", "llm_client": my_llm, "cache": cache}
            >>> gen = MockGenerator.from_config(**config)
        """
        try:
            return cls.from_preset(quality, llm_client=llm_client, cache=cache)
        except ValueError:
            # Fallback to default strategy if preset fails
            logger.warning(f"Invalid preset '{quality}', using default strategy")
            return cls(cache=cache)

    def generate_mock(
        self,
        tool_def: ToolDefinition,
        analysis: ToolAnalysis,
        strategy: MockStrategy = MockStrategy.SCHEMA_ONLY,
        custom_data: dict[str, Any] | None = None,
    ) -> MockImplementation:
        """
        Generate a static mock implementation for registration.

        Used during mirror setup to create registered mock functions.

        Args:
            tool_def: Tool definition
            analysis: Schema analysis
            strategy: Mock strategy (for metadata)
            custom_data: Optional custom mock data

        Returns:
            Mock implementation with function code and data

        Example:
            >>> impl = generator.generate_mock(tool_def, analysis)
            >>> register_mock(tool_def.name, impl.function_code)
        """
        logger.debug(f"Generating static mock for {tool_def.name}")

        # Generate mock data using static generator (for registration)
        if custom_data:
            mock_data = custom_data
        else:
            # Use static strategy for registration mocks
            mock_data = self.static_generator.generate(tool_def)

        # Generate function code
        function_code = self._generate_function_code(tool_def, analysis, mock_data)

        # Create metadata
        metadata = MirrorMetadata(
            tool_name=tool_def.name,
            server_name=tool_def.server_name,
            server_command=[],  # Will be set by registry
            strategy=strategy,
            custom_data_set=custom_data is not None,
        )

        return MockImplementation(
            tool_name=tool_def.name,
            function_code=function_code,
            mock_data=mock_data,
            metadata=metadata,
        )

    def generate_dynamic_mock(self, tool_def: ToolDefinition, input_params: dict[str, Any]) -> dict[str, Any]:
        """
        Generate dynamic mock response at runtime.

        Uses the configured strategy to generate context-aware responses.

        Args:
            tool_def: Tool definition
            input_params: Input parameters from tool call

        Returns:
            Generated mock response

        Example:
            >>> response = generator.generate_dynamic_mock(
            ...     tool_def, {"customer_id": "123"}
            ... )
            >>> assert "customer_id" in response
        """
        logger.debug(f"Generating dynamic mock for {tool_def.name} using {self.strategy.name}")

        try:
            response = self.strategy.generate(tool_def, input_params)

            # Track LLM stats if using DynamicStrategy
            if isinstance(self.strategy, DynamicStrategy):
                stats = self.strategy.get_stats()
                self._llm_calls = stats["llm_calls"]
                self._cache_hits = stats["cache_hits"]

            return response

        except Exception as e:
            logger.error(f"Dynamic mock generation failed for {tool_def.name}: {e}")
            # Ultimate fallback
            return {
                "status": "success",
                "tool": tool_def.name,
                "input": input_params,
                "error": f"Mock generation failed: {str(e)}",
            }

    def _generate_function_code(self, tool_def: ToolDefinition, analysis: ToolAnalysis, mock_data: Any) -> str:
        """
        Generate Python function code for the mock.

        Args:
            tool_def: Tool definition
            analysis: Schema analysis
            mock_data: Mock data to return

        Returns:
            Python function code as string
        """
        import json

        # Build parameter list
        params = []
        for param_name in analysis.required_params:
            params.append(f"{param_name}")
        for param_name in analysis.optional_params:
            params.append(f"{param_name}=None")

        param_str = ", ".join(params) if params else ""

        # Serialize mock data
        mock_data_str = json.dumps(mock_data, indent=4)

        # Generate function code
        function_code = f'''def {tool_def.name}({param_str}):
    """
    Mock implementation of {tool_def.name}.

    {tool_def.description}
    """
    return {mock_data_str}
'''

        return function_code

    def get_llm_stats(self) -> dict[str, Any]:
        """
        Get LLM usage statistics.

        Returns:
            Dictionary with LLM call counts and configuration

        Example:
            >>> stats = generator.get_llm_stats()
            >>> print(f"LLM calls: {stats['llm_calls']}")
        """
        # Get stats from strategy if it's a DynamicStrategy
        if isinstance(self.strategy, DynamicStrategy):
            return self.strategy.get_stats()

        # Otherwise return basic stats
        return {
            "llm_enabled": isinstance(self.strategy, DynamicStrategy),
            "llm_calls": self._llm_calls,
            "llm_cache_hits": self._cache_hits,
            "total_requests": self._llm_calls + self._cache_hits,
            "cache_hit_rate": (
                self._cache_hits / (self._llm_calls + self._cache_hits)
                if (self._llm_calls + self._cache_hits) > 0
                else 0.0
            ),
        }

    @property
    def current_strategy(self) -> str:
        """Get current strategy name."""
        return self.strategy.name

    def switch_strategy(self, strategy: BaseStrategy) -> None:
        """
        Switch to a different generation strategy.

        Args:
            strategy: New strategy instance

        Example:
            >>> gen = MockGenerator.from_preset("fast")
            >>> # Later, switch to LLM
            >>> gen.switch_strategy(DynamicStrategy(llm_client=my_llm))
        """
        old_strategy = self.strategy.name
        self.strategy = strategy
        logger.info(f"Switched strategy from {old_strategy} to {strategy.name}")


__all__ = ["MockGenerator"]
