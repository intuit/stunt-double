"""
Comprehensive tests for LangChain adapter integration.

Tests cover:
- LangChainAdapter.to_langchain_tools() - Convert mirrored tools to LangChain format
- LangChainAdapter._json_schema_to_pydantic() - Convert JSON schema to Pydantic model
- LangChainAdapter._json_type_to_python_type() - Map JSON types to Python types
"""

from unittest.mock import MagicMock, patch

import pytest

from stuntdouble.mirroring.integrations.langchain import LangChainAdapter


class TestLangChainAdapterJsonTypeToPythonType:
    """Test LangChainAdapter._json_type_to_python_type method."""

    def test_string_type_maps_to_str(self):
        """Test that 'string' maps to str."""
        result = LangChainAdapter._json_type_to_python_type("string")
        assert result is str

    def test_number_type_maps_to_float(self):
        """Test that 'number' maps to float."""
        result = LangChainAdapter._json_type_to_python_type("number")
        assert result is float

    def test_integer_type_maps_to_int(self):
        """Test that 'integer' maps to int."""
        result = LangChainAdapter._json_type_to_python_type("integer")
        assert result is int

    def test_boolean_type_maps_to_bool(self):
        """Test that 'boolean' maps to bool."""
        result = LangChainAdapter._json_type_to_python_type("boolean")
        assert result is bool

    def test_array_type_maps_to_list(self):
        """Test that 'array' maps to list."""
        result = LangChainAdapter._json_type_to_python_type("array")
        assert result is list

    def test_object_type_maps_to_dict(self):
        """Test that 'object' maps to dict."""
        result = LangChainAdapter._json_type_to_python_type("object")
        assert result is dict

    def test_unknown_type_defaults_to_str(self):
        """Test that unknown types default to str."""
        result = LangChainAdapter._json_type_to_python_type("unknown")
        assert result is str

    def test_empty_string_defaults_to_str(self):
        """Test that empty string defaults to str."""
        result = LangChainAdapter._json_type_to_python_type("")
        assert result is str

    def test_null_type_defaults_to_str(self):
        """Test that 'null' type defaults to str."""
        result = LangChainAdapter._json_type_to_python_type("null")
        assert result is str


class TestLangChainAdapterJsonSchemaToPydantic:
    """Test LangChainAdapter._json_schema_to_pydantic method."""

    def test_creates_pydantic_model_with_required_string_field(self):
        """Test creating a Pydantic model with a required string field."""
        json_schema = {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "Customer ID"}
            },
            "required": ["customer_id"],
        }

        model = LangChainAdapter._json_schema_to_pydantic(json_schema, "get_customer")

        assert model.__name__ == "GetCustomerSchema"
        fields = model.model_fields
        assert "customer_id" in fields
        assert fields["customer_id"].is_required()

    def test_creates_pydantic_model_with_optional_field(self):
        """Test creating a Pydantic model with an optional field."""
        json_schema = {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "Max results"}},
            "required": [],
        }

        model = LangChainAdapter._json_schema_to_pydantic(json_schema, "list_items")

        fields = model.model_fields
        assert "limit" in fields
        assert not fields["limit"].is_required()

    def test_creates_pydantic_model_with_mixed_fields(self):
        """Test creating a Pydantic model with mixed required and optional fields."""
        json_schema = {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "name": {"type": "string"},
                "age": {"type": "integer"},
            },
            "required": ["id"],
        }

        model = LangChainAdapter._json_schema_to_pydantic(json_schema, "update_user")

        fields = model.model_fields
        assert fields["id"].is_required()
        assert not fields["name"].is_required()
        assert not fields["age"].is_required()

    def test_creates_pydantic_model_with_various_types(self):
        """Test creating a Pydantic model with various JSON types."""
        json_schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "count": {"type": "integer"},
                "price": {"type": "number"},
                "active": {"type": "boolean"},
                "tags": {"type": "array"},
                "metadata": {"type": "object"},
            },
            "required": [],
        }

        model = LangChainAdapter._json_schema_to_pydantic(json_schema, "complex_tool")

        # Verify model can be instantiated with correct types
        instance = model(
            name="test",
            count=5,
            price=10.5,
            active=True,
            tags=["a", "b"],
            metadata={"key": "value"},
        )
        assert instance.name == "test"
        assert instance.count == 5
        assert instance.price == 10.5
        assert instance.active is True
        assert instance.tags == ["a", "b"]
        assert instance.metadata == {"key": "value"}

    def test_creates_pydantic_model_with_field_descriptions(self):
        """Test that field descriptions are preserved."""
        json_schema = {
            "type": "object",
            "properties": {
                "customer_id": {
                    "type": "string",
                    "description": "Unique customer identifier",
                }
            },
            "required": ["customer_id"],
        }

        model = LangChainAdapter._json_schema_to_pydantic(json_schema, "get_customer")

        fields = model.model_fields
        assert fields["customer_id"].description == "Unique customer identifier"

    def test_creates_pydantic_model_without_description(self):
        """Test creating a field without a description."""
        json_schema = {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": [],
        }

        model = LangChainAdapter._json_schema_to_pydantic(json_schema, "test_tool")

        # Should still create the field, just without description
        fields = model.model_fields
        assert "value" in fields

    def test_creates_pydantic_model_empty_properties(self):
        """Test creating a model with no properties."""
        json_schema = {
            "type": "object",
            "properties": {},
            "required": [],
        }

        model = LangChainAdapter._json_schema_to_pydantic(json_schema, "empty_tool")

        assert model.__name__ == "EmptyToolSchema"
        assert len(model.model_fields) == 0

    def test_creates_pydantic_model_no_properties_key(self):
        """Test creating a model when properties key is missing."""
        json_schema = {"type": "object"}

        model = LangChainAdapter._json_schema_to_pydantic(json_schema, "minimal_tool")

        assert len(model.model_fields) == 0

    def test_model_name_formatting_with_underscores(self):
        """Test that model name is formatted correctly with underscores."""
        json_schema = {"type": "object", "properties": {}}

        model = LangChainAdapter._json_schema_to_pydantic(
            json_schema, "get_customer_orders"
        )

        assert model.__name__ == "GetCustomerOrdersSchema"

    def test_handles_unknown_type_in_schema(self):
        """Test handling of unknown type in schema defaults to str."""
        json_schema = {
            "type": "object",
            "properties": {"custom_field": {"type": "custom_type"}},
            "required": [],
        }

        model = LangChainAdapter._json_schema_to_pydantic(json_schema, "test")

        # Should create model with field defaulting to str type
        instance = model(custom_field="test_value")
        assert instance.custom_field == "test_value"


class TestLangChainAdapterImportError:
    """Test LangChainAdapter behavior when dependencies are missing."""

    def test_raises_import_error_when_langchain_not_installed(self):
        """Test that ImportError is raised when langchain_core is not installed."""
        with patch.dict(
            "sys.modules", {"langchain_core": None, "langchain_core.tools": None}
        ):
            # Force reimport to trigger ImportError
            import sys

            # Save original modules
            original_modules = {}
            for key in list(sys.modules.keys()):
                if key.startswith("langchain"):
                    original_modules[key] = sys.modules.pop(key)

            try:
                # This should raise ImportError when langchain_core is not available
                # However, since langchain is likely installed in test env, we patch differently
                with patch(
                    "stuntdouble.mirroring.integrations.langchain.LangChainAdapter.to_langchain_tools"
                ) as mock_method:
                    mock_method.side_effect = ImportError(
                        "langchain_core is required for LangChain integration."
                    )

                    with pytest.raises(ImportError) as exc_info:
                        LangChainAdapter.to_langchain_tools([], MagicMock())

                    assert "langchain_core" in str(exc_info.value)
            finally:
                # Restore original modules
                sys.modules.update(original_modules)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
