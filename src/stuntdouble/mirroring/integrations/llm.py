"""
LLM-powered mock generation.

Provides high-quality mock generation using any LangChain-compatible LLM client
as a fallback for complex or novel schemas.
"""

import json
import logging
from typing import Any

from ..models import ToolDefinition

logger = logging.getLogger(__name__)


class LLMProvider:
    """
    LLM-powered mock generation provider.

    Uses any LangChain-compatible LLM client to generate realistic mock responses for tools,
    especially useful for complex or novel schemas that don't
    match standard patterns.
    """

    def __init__(self, llm_client: Any, cache: Any | None = None):
        """
        Initialize LLM provider.

        Args:
            llm_client: LangChain-compatible LLM client (e.g., ChatOpenAI)
            cache: Optional ResponseCache for caching LLM responses
        """
        self.llm_client = llm_client
        self.cache = cache

        logger.info(f"LLMProvider initialized with client: {type(llm_client).__name__}")

    def generate_with_llm(self, tool_def: ToolDefinition, input_params: dict[str, Any]) -> dict[str, Any]:
        """
        Generate mock response using LLM.

        Creates a prompt with tool definition and input params,
        asks LLM to generate realistic JSON response.

        This is used when static patterns don't match
        the tool's schema or when the tool is too complex/novel.

        Args:
            tool_def: Tool definition
            input_params: Input parameters

        Returns:
            Generated mock response

        Raises:
            json.JSONDecodeError: If LLM returns invalid JSON
            ValueError: If LLM response validation fails
            Exception: If LLM API call fails

        Example:
            >>> provider = LLMProvider(llm_client)
            >>> tool = ToolDefinition("analyze_sentiment", "Analyze sentiment", ...)
            >>> response = provider.generate_with_llm(tool, {"text": "Great product!"})
            >>> assert "sentiment" in response
        """
        logger.info(f"Calling LLM for {tool_def.name}")

        # Build prompt
        prompt = self._build_llm_prompt(tool_def, input_params)

        # Call LLM
        llm_response = self._call_llm(prompt)

        # Parse and validate
        try:
            # Extract JSON from markdown code blocks if present
            llm_response = llm_response.strip()
            if "```json" in llm_response:
                llm_response = llm_response.split("```json")[1].split("```")[0].strip()
            elif "```" in llm_response:
                llm_response = llm_response.split("```")[1].split("```")[0].strip()

            mock_response = json.loads(llm_response)
            self._validate_llm_response(mock_response, tool_def)
            return mock_response
        except json.JSONDecodeError as e:
            logger.error(f"LLM returned invalid JSON: {e}\nResponse: {llm_response[:200]}")
            raise

    def _build_llm_prompt(self, tool_def: ToolDefinition, input_params: dict[str, Any]) -> str:
        """
        Build prompt for LLM mock generation.

        Creates a detailed prompt that includes:
        - Tool name and description
        - Input schema
        - Actual parameters provided
        - Requirements for response generation

        Args:
            tool_def: Tool definition
            input_params: Input parameters

        Returns:
            Formatted prompt string
        """
        # Format parameters section
        if input_params:
            params_section = f"""Called With Parameters:
{json.dumps(input_params, indent=2)}"""
        else:
            params_section = "Called With Parameters: (none - generate realistic sample data)"

        prompt = f"""Generate a realistic JSON response for this tool call. If there are no parameters, generate realistic sample data based on the schema and or tool name.

Tool Name: {tool_def.name}
Description: {tool_def.description}

Input Schema:
{json.dumps(tool_def.input_schema, indent=2)}

{params_section}

Requirements:
1. Generate ONLY valid JSON (no markdown, no explanation)
2. Response should be realistic and match the tool's purpose
3. Include all relevant fields based on the tool description
4. If input parameters were provided, echo any ID fields back in the response
5. Use realistic values (names, emails, dates, amounts, etc.)
6. Ensure the response is appropriate for the operation (list, get, create, update, delete)
7. If no parameters were provided, generate realistic sample data based on the schema

Generate the JSON response now:"""
        return prompt

    def _call_llm(self, prompt: str) -> str:
        """
        Call LLM client with prompt.

        Args:
            prompt: Prompt text

        Returns:
            LLM response text

        Raises:
            ValueError: If client type is unsupported
            Exception: If LLM API call fails
        """
        try:
            # LangChain-compatible clients - uses invoke() with LangChain messages
            if hasattr(self.llm_client, "invoke"):
                from langchain_core.messages import HumanMessage

                response = self.llm_client.invoke([HumanMessage(content=prompt)])
                # LangChain returns AIMessage with .content attribute
                if hasattr(response, "content"):
                    return response.content
                else:
                    return str(response)

            # Legacy chat method (for compatibility)
            elif hasattr(self.llm_client, "chat"):
                response = self.llm_client.chat(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,  # Low temp for consistency
                )
                # Handle different response formats
                if hasattr(response, "choices"):
                    return response.choices[0].message.content
                elif hasattr(response, "content"):
                    return response.content
                else:
                    return str(response)

            else:
                raise ValueError(
                    f"Unsupported LLM client type: {type(self.llm_client)}. "
                    "Expected LangChain-compatible client with invoke() or chat() method."
                )

        except Exception as e:
            logger.error(f"LLM API call failed: {e}")
            raise

    def _validate_llm_response(self, response: dict[str, Any], tool_def: ToolDefinition) -> None:
        """
        Validate LLM-generated response.

        Basic checks:
        - Is valid JSON (already validated by caller)
        - Contains data (not empty)
        - No obvious errors or refusals

        Args:
            response: Parsed JSON response
            tool_def: Tool definition

        Raises:
            ValueError: If validation fails
        """
        if not response:
            raise ValueError("LLM returned empty response")

        if "error" in response:
            raise ValueError(f"LLM response contains error: {response['error']}")

        # Could add more sophisticated validation based on output schema
        logger.debug(f"LLM response validated for {tool_def.name}")


__all__ = ["LLMProvider"]
