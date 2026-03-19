"""
LangChain integration for mirrored tools.

Provides adapters to convert mirrored MCP tools into LangChain-compatible
StructuredTool instances for use with LangChain agents.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..models import ToolDefinition

if TYPE_CHECKING:
    from ..mirror_registry import MirroredToolRegistry

logger = logging.getLogger(__name__)


class LangChainAdapter:
    """
    Adapter for converting mirrored tools to LangChain format.

    Converts MCP tool definitions and their mocked implementations
    into LangChain StructuredTool instances, complete with:
    - Pydantic schema validation
    - Mocked implementations
    - Proper signatures and documentation
    """

    @staticmethod
    def to_langchain_tools(
        tool_definitions: list[ToolDefinition],
        mock_registry: MirroredToolRegistry,
    ) -> list[Any]:
        """
        Convert mirrored tools to LangChain StructuredTool format.

        This method creates LangChain-compatible tools with mocked implementations
        already bound, ready to use with LangChain agents.

        Args:
            tool_definitions: List of tool definitions to convert
            mock_registry: MirroredToolRegistry that holds mock callables

        Returns:
            List of LangChain StructuredTool instances with mocked implementations

        Raises:
            ImportError: If langchain_core is not installed

        Example:
            >>> tools = LangChainAdapter.to_langchain_tools(tool_defs, mirror_registry)
            >>> agent_with_tools = agent_llm.bind_tools(tools)
        """
        try:
            from langchain_core.tools import StructuredTool
        except ImportError:
            raise ImportError(
                "langchain_core is required for LangChain integration. "
                "Install with: pip install langchain-core"
            )

        available_mocks = mock_registry.list_mock_functions()

        langchain_tools = []
        for tool_def in tool_definitions:
            mock_fn = available_mocks.get(tool_def.name)
            if mock_fn is None:
                logger.warning(
                    f"Tool {tool_def.name} discovered but not mocked, skipping"
                )
                continue

            args_schema = None
            if tool_def.input_schema:
                try:
                    args_schema = LangChainAdapter._json_schema_to_pydantic(
                        tool_def.input_schema, tool_def.name
                    )
                except Exception as e:
                    logger.debug(
                        f"Could not convert schema to Pydantic for {tool_def.name}: {e}"
                    )

            if args_schema:
                lc_tool = StructuredTool(
                    func=mock_fn,
                    name=tool_def.name,
                    description=tool_def.description or f"Execute {tool_def.name}",
                    args_schema=args_schema,
                )
            else:
                lc_tool = StructuredTool.from_function(
                    func=mock_fn,
                    name=tool_def.name,
                    description=tool_def.description or f"Execute {tool_def.name}",
                )
            langchain_tools.append(lc_tool)

        logger.info(f"Converted {len(langchain_tools)} tools to LangChain format")
        return langchain_tools

    @staticmethod
    def _json_schema_to_pydantic(json_schema: dict[str, Any], tool_name: str) -> Any:
        """
        Convert JSON schema to Pydantic BaseModel.

        Args:
            json_schema: JSON schema dict
            tool_name: Name of the tool (used for model name)

        Returns:
            Pydantic BaseModel class

        Raises:
            ImportError: If pydantic is not available
        """
        try:
            from pydantic import Field, create_model
        except ImportError:
            raise ImportError(
                "pydantic is required for schema conversion. "
                "Install with: pip install pydantic"
            )

        # Extract properties and required fields
        properties = json_schema.get("properties", {})
        required = json_schema.get("required", [])

        # Build field definitions for Pydantic
        field_definitions = {}
        for prop_name, prop_schema in properties.items():
            # Get type
            prop_type = LangChainAdapter._json_type_to_python_type(
                prop_schema.get("type", "string")
            )

            # Get description
            description = prop_schema.get("description", "")

            # Determine if required
            is_required = prop_name in required
            default = ... if is_required else None

            # Create field with description
            if description:
                field_definitions[prop_name] = (
                    prop_type,
                    Field(default=default, description=description),
                )
            else:
                field_definitions[prop_name] = (prop_type, default)

        # Create dynamic Pydantic model
        model_name = f"{tool_name.title().replace('_', '')}Schema"
        return create_model(model_name, **field_definitions)

    @staticmethod
    def _json_type_to_python_type(json_type: str) -> type:
        """
        Map JSON schema types to Python types.

        Args:
            json_type: JSON schema type string

        Returns:
            Python type
        """
        type_mapping = {
            "string": str,
            "number": float,
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        return type_mapping.get(json_type, str)


__all__ = ["LangChainAdapter"]
