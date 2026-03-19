"""
Mock generation strategies.

Provides a strategy pattern for different mock generation approaches:
- StaticStrategy: Fast, schema-based mocks with static templates
- DynamicStrategy: High-quality LLM-powered mocks

Example:
    >>> from stuntdouble.mirroring.strategies import StaticStrategy
    >>> strategy = StaticStrategy()
    >>> response = strategy.generate(tool_def, input_params)
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

from .generation.entity import EntityInference, StaticFieldGenerator
from .generation.responses import ResponseBuilder
from .models import ToolDefinition

logger = logging.getLogger(__name__)


# ============================================================================
# BASE STRATEGY - Abstract interface
# ============================================================================


class BaseStrategy(ABC):
    """
    Abstract base class for mock generation strategies.

    All strategies must implement the generate() method to create
    mock responses based on tool definitions and input parameters.
    """

    def __init__(self, cache: Any | None = None):
        """
        Initialize strategy with optional caching.

        Args:
            cache: Optional ResponseCache instance for caching responses
        """
        self.cache = cache

    @abstractmethod
    def generate(
        self, tool_def: ToolDefinition, input_params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Generate a mock response for the given tool and parameters.

        Args:
            tool_def: Tool definition containing schema and metadata
            input_params: Optional input parameters from tool call

        Returns:
            Generated mock response as a dictionary

        Raises:
            Exception: If generation fails
        """
        pass

    def _check_cache(
        self, tool_def: ToolDefinition, input_params: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        """
        Check cache for existing response.

        Args:
            tool_def: Tool definition
            input_params: Input parameters

        Returns:
            Cached response if found, None otherwise
        """
        if self.cache and input_params:
            cached = self.cache.get(tool_def.name, input_params)
            if cached:
                logger.debug(f"Cache hit for {tool_def.name}")
                return cached
        return None

    def _store_cache(
        self,
        tool_def: ToolDefinition,
        input_params: dict[str, Any] | None,
        response: dict[str, Any],
    ) -> None:
        """
        Store response in cache.

        Args:
            tool_def: Tool definition
            input_params: Input parameters
            response: Generated response to cache
        """
        if self.cache and input_params:
            self.cache.set(tool_def.name, input_params, response)
            logger.debug(f"Cached response for {tool_def.name}")

    @property
    def name(self) -> str:
        """Get strategy name."""
        return self.__class__.__name__


# ============================================================================
# STATIC STRATEGY - Fast, template-based mocks
# ============================================================================


class StaticStrategy(BaseStrategy):
    """
    Static mock generation strategy.

    Generates mock responses based on tool schema and entity type inference.
    Uses deterministic templates for realistic but predictable data.

    Characteristics:
    - Fast: No complex logic or external calls
    - Deterministic: Predictable output based on entity type
    - Schema-based: Uses tool definition to infer entity types
    - Parameter-aware: Echoes IDs and respects pagination

    Use this strategy when:
    - Speed is critical (CI/CD pipelines)
    - You need predictable, consistent responses
    - You want parameter-aware mock responses

    Example:
        >>> strategy = StaticStrategy()
        >>> response = strategy.generate(tool_def, {"customer_id": "123"})
        >>> assert response["customer_id"] == "123"
    """

    def __init__(self, cache: Any | None = None):
        """
        Initialize static strategy.

        Args:
            cache: Optional cache for response consistency
        """
        super().__init__(cache)
        self.field_generator = StaticFieldGenerator()
        self.response_builder = ResponseBuilder(self.field_generator)

    def generate(
        self, tool_def: ToolDefinition, input_params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Generate static mock response with parameter awareness.

        Args:
            tool_def: Tool definition
            input_params: Input parameters to echo/respect

        Returns:
            Generated mock response

        Example:
            >>> tool_def = ToolDefinition(name="get_customer", ...)
            >>> response = strategy.generate(tool_def, {"customer_id": "123"})
            >>> assert response["customer_id"] == "123"
        """
        # Check cache first
        cached = self._check_cache(tool_def, input_params)
        if cached:
            return cached

        logger.debug(f"Generating static mock for {tool_def.name}")

        # Infer entity type from tool name and description
        entity_type = EntityInference.infer_entity_type(tool_def)

        # Determine operation type from tool name
        name_lower = tool_def.name.lower()

        # Route to appropriate response generator based on operation
        if any(
            keyword in name_lower for keyword in ["list", "search", "query", "find"]
        ):
            response = self.response_builder.build_list_response(entity_type)
        elif any(
            keyword in name_lower for keyword in ["get", "fetch", "retrieve", "read"]
        ):
            response = self.response_builder.build_entity_response(entity_type)
        elif any(keyword in name_lower for keyword in ["create", "add", "insert"]):
            response = self.response_builder.build_creation_response(entity_type)
        elif any(
            keyword in name_lower for keyword in ["update", "modify", "edit", "patch"]
        ):
            response = self.response_builder.build_update_response(entity_type)
        elif any(keyword in name_lower for keyword in ["delete", "remove", "destroy"]):
            response = self.response_builder.build_deletion_response(entity_type)
        else:
            response = self.response_builder.build_generic_response(
                tool_def, entity_type
            )

        # Apply parameter awareness if we have input
        if input_params:
            response = self._apply_parameter_awareness(response, input_params)

        # Cache the response
        self._store_cache(tool_def, input_params, response)

        return response

    def _apply_parameter_awareness(
        self, response: dict[str, Any], input_params: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Make response parameter-aware by echoing IDs and applying filters.

        Args:
            response: Base generated response
            input_params: Input parameters

        Returns:
            Modified response with parameter awareness
        """
        # Echo back ID fields
        id_fields = [k for k in input_params.keys() if k.endswith("_id") or k == "id"]
        for field in id_fields:
            response[field] = input_params[field]

        # Handle pagination parameters
        if "limit" in input_params and "items" in response:
            limit = int(input_params["limit"])
            response["items"] = response["items"][:limit]

        if "page" in input_params:
            response["page"] = int(input_params["page"])

        if "offset" in input_params:
            response["offset"] = int(input_params["offset"])

        # Handle filter parameters
        filter_fields = ["status", "type", "category", "filter"]
        for field in filter_fields:
            if field in input_params:
                response[field] = input_params[field]

        # Echo other simple parameters
        simple_types = (str, int, float, bool)
        for key, value in input_params.items():
            if isinstance(value, simple_types) and key not in response:
                response[key] = value

        return response


# ============================================================================
# DYNAMIC STRATEGY - LLM-powered, high-quality mocks
# ============================================================================


class DynamicStrategy(BaseStrategy):
    """
    LLM-powered dynamic mock generation strategy.

    Generates high-quality, context-aware mock responses using LLMs.
    Understands complex schemas and generates realistic, varied responses.

    Characteristics:
    - High quality: LLM-generated responses are contextually appropriate
    - Context-aware: Understands relationships between parameters
    - Realistic: Generates varied, human-like data
    - Expensive: Requires LLM API calls (mitigated by caching)
    - Slower: Network latency and model inference time

    Use this strategy when:
    - Quality is more important than speed
    - You need varied, realistic responses
    - Testing complex business logic
    - Evaluating conversation flows

    Example:
        >>> from langchain_openai import ChatOpenAI
        >>> client = ChatOpenAI(model="gpt-4o")
        >>> strategy = DynamicStrategy(llm_client=client, cache=cache)
        >>> response = strategy.generate(tool_def, {"customer_id": "123"})
        >>> # LLM generates contextually appropriate response
    """

    def __init__(self, llm_client: Any, cache: Any | None = None):
        """
        Initialize LLM-powered strategy.

        Args:
            llm_client: LangChain-compatible LLM client instance
            cache: Optional ResponseCache to reduce LLM calls

        Raises:
            ValueError: If llm_client is None
        """
        if llm_client is None:
            raise ValueError("DynamicStrategy requires an LLM client")

        super().__init__(cache)
        self.llm_client = llm_client
        self.llm_calls = 0
        self.cache_hits = 0

    def generate(
        self, tool_def: ToolDefinition, input_params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Generate LLM-powered mock response.

        Args:
            tool_def: Tool definition
            input_params: Input parameters for context

        Returns:
            Generated mock response from LLM

        Example:
            >>> response = strategy.generate(tool_def, {"customer_id": "123"})
            >>> # Response generated by LLM based on schema and params
        """
        # Check cache first (saves LLM costs)
        cached = self._check_cache(tool_def, input_params)
        if cached:
            self.cache_hits += 1
            return cached

        logger.debug(f"Generating LLM-powered mock for {tool_def.name}")

        try:
            # Import LLM provider
            from .integrations.llm import LLMProvider

            llm_provider = LLMProvider(self.llm_client, cache=self.cache)
            response = llm_provider.generate_with_llm(tool_def, input_params or {})

            # Track statistics
            self.llm_calls += 1

            # Cache for future use
            self._store_cache(tool_def, input_params, response)

            return response

        except Exception as e:
            logger.error(f"LLM generation failed for {tool_def.name}: {e}")
            # Fallback to simple response
            return {
                "status": "success",
                "tool": tool_def.name,
                "input": input_params or {},
                "note": "LLM generation failed, using fallback",
            }

    def get_stats(self) -> dict[str, Any]:
        """
        Get LLM usage statistics.

        Returns:
            Dictionary with LLM call counts and cache hit rate

        Example:
            >>> stats = strategy.get_stats()
            >>> print(f"Cache hit rate: {stats['cache_hit_rate']:.1%}")
        """
        total = self.llm_calls + self.cache_hits
        return {
            "llm_calls": self.llm_calls,
            "cache_hits": self.cache_hits,
            "total_requests": total,
            "cache_hit_rate": (self.cache_hits / total) if total > 0 else 0.0,
        }


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "BaseStrategy",
    "StaticStrategy",
    "DynamicStrategy",
]
