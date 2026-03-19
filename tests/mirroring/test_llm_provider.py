"""
Comprehensive tests for LLM-powered mock generation.

Tests cover:
- LLMProvider initialization
- Generate with LLM (including JSON extraction from markdown)
- Build LLM prompt
- Call LLM client (invoke and chat methods)
- Validate LLM response
"""

import json
from unittest.mock import Mock, patch

import pytest

from stuntdouble.mirroring.integrations.llm import LLMProvider
from stuntdouble.mirroring.models import ToolDefinition


class TestLLMProviderInit:
    """Test LLMProvider initialization."""

    def test_init_with_llm_client(self):
        """Test initialization with LLM client."""
        mock_client = Mock()
        provider = LLMProvider(llm_client=mock_client)

        assert provider.llm_client is mock_client
        assert provider.cache is None

    def test_init_with_cache(self):
        """Test initialization with cache."""
        mock_client = Mock()
        mock_cache = Mock()
        provider = LLMProvider(llm_client=mock_client, cache=mock_cache)

        assert provider.llm_client is mock_client
        assert provider.cache is mock_cache


class TestGenerateWithLLM:
    """Test LLMProvider.generate_with_llm method."""

    def setup_method(self):
        """Setup for each test."""
        self.mock_client = Mock()
        self.provider = LLMProvider(llm_client=self.mock_client)
        self.tool_def = ToolDefinition(
            name="get_customer",
            description="Get customer by ID",
            input_schema={
                "type": "object",
                "properties": {"customer_id": {"type": "string", "description": "Customer ID"}},
                "required": ["customer_id"],
            },
        )

    def test_generate_with_llm_invoke_method(self):
        """Test successful generation with invoke() method (LangChain style)."""
        mock_response = Mock()
        mock_response.content = '{"id": "123", "name": "Test Customer"}'
        self.mock_client.invoke = Mock(return_value=mock_response)

        with patch("langchain_core.messages.HumanMessage") as mock_msg:
            mock_msg.return_value = "mocked_message"
            result = self.provider.generate_with_llm(self.tool_def, {"customer_id": "123"})

        assert result == {"id": "123", "name": "Test Customer"}
        self.mock_client.invoke.assert_called_once()

    def test_generate_with_llm_extracts_json_from_markdown_json_block(self):
        """Test JSON extraction from markdown code blocks with json tag."""
        mock_response = Mock()
        mock_response.content = '```json\n{"id": "123", "name": "Test"}\n```'
        self.mock_client.invoke = Mock(return_value=mock_response)

        with patch("langchain_core.messages.HumanMessage") as mock_msg:
            mock_msg.return_value = "mocked_message"
            result = self.provider.generate_with_llm(self.tool_def, {"customer_id": "123"})

        assert result == {"id": "123", "name": "Test"}

    def test_generate_with_llm_extracts_json_from_plain_markdown_block(self):
        """Test JSON extraction from plain markdown code blocks."""
        mock_response = Mock()
        mock_response.content = '```\n{"id": "456", "name": "Plain"}\n```'
        self.mock_client.invoke = Mock(return_value=mock_response)

        with patch("langchain_core.messages.HumanMessage") as mock_msg:
            mock_msg.return_value = "mocked_message"
            result = self.provider.generate_with_llm(self.tool_def, {"customer_id": "456"})

        assert result == {"id": "456", "name": "Plain"}

    def test_generate_with_llm_invalid_json_raises_error(self):
        """Test that invalid JSON response raises JSONDecodeError."""
        mock_response = Mock()
        mock_response.content = "not valid json"
        self.mock_client.invoke = Mock(return_value=mock_response)

        with patch("langchain_core.messages.HumanMessage") as mock_msg:
            mock_msg.return_value = "mocked_message"
            with pytest.raises(json.JSONDecodeError):
                self.provider.generate_with_llm(self.tool_def, {"customer_id": "123"})


class TestCallLLM:
    """Test LLMProvider._call_llm method."""

    def test_call_llm_with_invoke_method_returns_content(self):
        """Test _call_llm with invoke() returning response with content attribute."""
        mock_client = Mock()
        mock_response = Mock()
        mock_response.content = "test response"
        mock_client.invoke = Mock(return_value=mock_response)
        provider = LLMProvider(llm_client=mock_client)

        with patch("langchain_core.messages.HumanMessage") as mock_msg:
            mock_msg.return_value = "mocked_message"
            result = provider._call_llm("test prompt")

        assert result == "test response"

    def test_call_llm_with_invoke_method_no_content_attribute(self):
        """Test _call_llm with invoke() returning response without content attribute."""
        mock_client = Mock()
        mock_response = Mock(spec=[])  # No content attribute
        mock_client.invoke = Mock(return_value=mock_response)
        provider = LLMProvider(llm_client=mock_client)

        with patch("langchain_core.messages.HumanMessage") as mock_msg:
            mock_msg.return_value = "mocked_message"
            result = provider._call_llm("test prompt")

        assert result == str(mock_response)

    def test_call_llm_with_chat_method_choices(self):
        """Test _call_llm with chat() method returning choices format."""
        mock_client = Mock(spec=["chat"])  # Only chat, no invoke
        mock_message = Mock()
        mock_message.content = "chat response"
        mock_choice = Mock()
        mock_choice.message = mock_message
        mock_response = Mock()
        mock_response.choices = [mock_choice]
        mock_client.chat = Mock(return_value=mock_response)
        provider = LLMProvider(llm_client=mock_client)

        result = provider._call_llm("test prompt")

        assert result == "chat response"
        mock_client.chat.assert_called_once()

    def test_call_llm_with_chat_method_content_attribute(self):
        """Test _call_llm with chat() method returning content attribute."""
        mock_client = Mock(spec=["chat"])  # Only chat, no invoke
        mock_response = Mock(spec=["content"])  # Only content, no choices
        mock_response.content = "direct content"
        mock_client.chat = Mock(return_value=mock_response)
        provider = LLMProvider(llm_client=mock_client)

        result = provider._call_llm("test prompt")

        assert result == "direct content"

    def test_call_llm_with_chat_method_string_fallback(self):
        """Test _call_llm with chat() method returning unknown format."""
        mock_client = Mock(spec=["chat"])  # Only chat, no invoke
        mock_response = Mock(spec=[])  # No content, no choices
        mock_client.chat = Mock(return_value=mock_response)
        provider = LLMProvider(llm_client=mock_client)

        result = provider._call_llm("test prompt")

        assert result == str(mock_response)

    def test_call_llm_unsupported_client_raises_error(self):
        """Test _call_llm raises ValueError for unsupported client type."""
        mock_client = Mock(spec=[])  # No invoke, no chat
        provider = LLMProvider(llm_client=mock_client)

        with pytest.raises(ValueError) as exc_info:
            provider._call_llm("test prompt")

        assert "Unsupported LLM client type" in str(exc_info.value)
        assert "invoke()" in str(exc_info.value)
        assert "chat()" in str(exc_info.value)


class TestValidateLLMResponse:
    """Test LLMProvider._validate_llm_response method."""

    def setup_method(self):
        """Setup for each test."""
        mock_client = Mock()
        self.provider = LLMProvider(llm_client=mock_client)
        self.tool_def = ToolDefinition(
            name="test_tool",
            description="Test tool",
            input_schema={"type": "object", "properties": {}},
        )

    def test_validate_empty_response_raises_error(self):
        """Test that empty response raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            self.provider._validate_llm_response({}, self.tool_def)

        assert "empty response" in str(exc_info.value)

    def test_validate_none_response_raises_error(self):
        """Test that None response raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            self.provider._validate_llm_response(None, self.tool_def)  # type: ignore[arg-type]

        assert "empty response" in str(exc_info.value)

    def test_validate_response_with_error_field_raises_error(self):
        """Test that response with error field raises ValueError."""
        response = {"error": "Something went wrong", "data": None}

        with pytest.raises(ValueError) as exc_info:
            self.provider._validate_llm_response(response, self.tool_def)

        assert "contains error" in str(exc_info.value)
        assert "Something went wrong" in str(exc_info.value)

    def test_validate_valid_response_passes(self):
        """Test that valid response passes validation."""
        response = {"id": "123", "name": "Test", "status": "active"}

        # Should not raise any exception
        self.provider._validate_llm_response(response, self.tool_def)


class TestBuildLLMPrompt:
    """Test LLMProvider._build_llm_prompt method."""

    def setup_method(self):
        """Setup for each test."""
        mock_client = Mock()
        self.provider = LLMProvider(llm_client=mock_client)
        self.tool_def = ToolDefinition(
            name="get_customer",
            description="Get customer by ID",
            input_schema={
                "type": "object",
                "properties": {"customer_id": {"type": "string", "description": "Customer ID"}},
                "required": ["customer_id"],
            },
        )

    def test_build_prompt_includes_tool_name(self):
        """Test that prompt includes tool name."""
        prompt = self.provider._build_llm_prompt(self.tool_def, {"customer_id": "123"})

        assert "Tool Name: get_customer" in prompt

    def test_build_prompt_includes_description(self):
        """Test that prompt includes tool description."""
        prompt = self.provider._build_llm_prompt(self.tool_def, {"customer_id": "123"})

        assert "Description: Get customer by ID" in prompt

    def test_build_prompt_includes_input_schema(self):
        """Test that prompt includes input schema."""
        prompt = self.provider._build_llm_prompt(self.tool_def, {"customer_id": "123"})

        assert "Input Schema:" in prompt
        assert "customer_id" in prompt

    def test_build_prompt_includes_parameters(self):
        """Test that prompt includes called parameters."""
        prompt = self.provider._build_llm_prompt(self.tool_def, {"customer_id": "123", "include_orders": True})

        assert "Called With Parameters:" in prompt
        assert '"customer_id": "123"' in prompt
        assert '"include_orders": true' in prompt

    def test_build_prompt_with_empty_params(self):
        """Test that prompt handles empty parameters."""
        prompt = self.provider._build_llm_prompt(self.tool_def, {})

        assert "Called With Parameters: (none" in prompt
        assert "generate realistic sample data" in prompt

    def test_build_prompt_includes_requirements(self):
        """Test that prompt includes generation requirements."""
        prompt = self.provider._build_llm_prompt(self.tool_def, {"customer_id": "123"})

        assert "Requirements:" in prompt
        assert "valid JSON" in prompt
        assert "realistic" in prompt


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
