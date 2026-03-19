"""
Unit tests for mock signature validation.

Tests the validate_mock_signature function and related validation utilities.
"""

import pytest
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

# =============================================================================
# Pydantic v1 Mock Helpers
# =============================================================================


def _create_pydantic_v1_mock_schema(fields: dict[str, bool]):
    """Create a mock Pydantic v1 style schema.

    Args:
        fields: Dict mapping field names to required status (True=required, False=optional)

    Returns:
        MagicMock configured to look like a Pydantic v1 schema
    """
    from unittest.mock import MagicMock

    mock_schema = MagicMock()
    # Remove v2 attribute to simulate v1 - use spec to avoid attribute
    mock_schema.configure_mock(
        **{"model_fields": MagicMock(side_effect=AttributeError)}
    )
    # Actually delete it to trigger hasattr checks
    if hasattr(mock_schema, "model_fields"):
        del mock_schema.model_fields

    mock_fields = {}
    for name, required in fields.items():
        field = MagicMock()
        field.required = required
        field.default = None if required else "default_value"
        mock_fields[name] = field

    mock_schema.__fields__ = mock_fields
    return mock_schema


def _create_mock_tool_with_v1_schema(name: str, fields: dict[str, bool]):
    """Create a mock tool with Pydantic v1 style args_schema.

    Args:
        name: Tool name
        fields: Dict mapping field names to required status

    Returns:
        MagicMock configured as a tool with v1 schema
    """
    from unittest.mock import MagicMock

    mock_tool = MagicMock()
    mock_tool.name = name
    mock_tool.args_schema = _create_pydantic_v1_mock_schema(fields)
    return mock_tool


# =============================================================================
# Test Fixtures
# =============================================================================


class GetWeatherInput(BaseModel):
    """Input schema for get_weather tool."""

    city: str = Field(description="City name")
    units: str = Field(default="celsius", description="Temperature units")


class GetWeatherTool(BaseTool):
    """Test tool with defined schema."""

    name: str = "get_weather"
    description: str = "Get weather for a city"
    args_schema: type[BaseModel] = GetWeatherInput

    def _run(self, city: str, units: str = "celsius") -> str:
        return f"Weather in {city}: 72 {units}"


class ListCustomersInput(BaseModel):
    """Input schema for list_customers tool."""

    tool_input: str = Field(default="", description="Optional input")
    config: dict = Field(default=None, description="Config object")


class ListCustomersTool(BaseTool):
    """Test tool with config parameter."""

    name: str = "list_customers"
    description: str = "List customers"
    args_schema: type[BaseModel] = ListCustomersInput

    def _run(self, tool_input: str = "", config: dict | None = None) -> list:
        return []


# =============================================================================
# Test Classes
# =============================================================================


class TestValidateMockSignature:
    """Tests for validate_mock_signature function."""

    def test_exact_match_passes_validation(self):
        """Test that exact signature match passes validation."""
        from stuntdouble.validation import validate_mock_signature

        tool = GetWeatherTool()

        # Mock with exact same signature
        def good_mock(scenario_metadata: dict):
            def mock_fn(city: str, units: str = "celsius"):
                return {"temp": 72}

            return mock_fn

        is_valid, error = validate_mock_signature(tool, good_mock)

        assert is_valid is True
        assert error is None

    def test_missing_required_parameter_fails(self):
        """Test that missing required parameter fails validation."""
        from stuntdouble.validation import validate_mock_signature

        tool = GetWeatherTool()

        # Mock missing 'city' parameter
        def bad_mock(scenario_metadata: dict):
            def mock_fn(units: str = "celsius"):
                return {"temp": 72}

            return mock_fn

        is_valid, error = validate_mock_signature(tool, bad_mock)

        assert is_valid is False
        assert error is not None
        assert "city" in error.lower() or "missing" in error.lower()

    def test_missing_optional_parameter_fails_exact_match(self):
        """Test that missing optional parameter fails in exact match mode."""
        from stuntdouble.validation import validate_mock_signature

        tool = GetWeatherTool()

        # Mock missing 'units' optional parameter
        def bad_mock(scenario_metadata: dict):
            def mock_fn(city: str):  # Missing 'units'
                return {"temp": 72}

            return mock_fn

        is_valid, error = validate_mock_signature(tool, bad_mock)

        # Should fail for exact match
        assert is_valid is False
        assert error is not None
        assert "units" in error.lower() or "missing" in error.lower()

    def test_extra_required_parameter_fails(self):
        """Test that extra required parameter in mock fails validation."""
        from stuntdouble.validation import validate_mock_signature

        tool = GetWeatherTool()

        # Mock with extra required parameter
        def bad_mock(scenario_metadata: dict):
            def mock_fn(city: str, units: str, extra_required: str):
                return {"temp": 72}

            return mock_fn

        is_valid, error = validate_mock_signature(tool, bad_mock)

        assert is_valid is False
        assert error is not None
        assert "extra" in error.lower()

    def test_extra_optional_parameter_passes(self):
        """Test that extra optional parameter in mock passes validation."""
        from stuntdouble.validation import validate_mock_signature

        tool = GetWeatherTool()

        # Mock with extra optional parameter
        def good_mock(scenario_metadata: dict):
            def mock_fn(city: str, units: str = "celsius", extra: str | None = None):
                return {"temp": 72}

            return mock_fn

        is_valid, error = validate_mock_signature(tool, good_mock)

        # Should pass - extra optional params are ok
        assert is_valid is True
        assert error is None

    def test_with_config_parameter(self):
        """Test validation with config parameter in tool signature."""
        from stuntdouble.validation import validate_mock_signature

        tool = ListCustomersTool()

        # Mock with matching config parameter
        def good_mock(scenario_metadata: dict):
            def mock_fn(tool_input: str = "", config: dict | None = None):
                return []

            return mock_fn

        is_valid, error = validate_mock_signature(tool, good_mock)

        assert is_valid is True
        assert error is None

    def test_missing_config_parameter_fails(self):
        """Test that missing config parameter fails validation."""
        from stuntdouble.validation import validate_mock_signature

        tool = ListCustomersTool()

        # Mock missing config parameter
        def bad_mock(scenario_metadata: dict):
            def mock_fn(tool_input: str = ""):  # Missing 'config'
                return []

            return mock_fn

        is_valid, error = validate_mock_signature(tool, bad_mock)

        assert is_valid is False
        assert error is not None
        assert "config" in error.lower() or "missing" in error.lower()

    def test_with_scenario_metadata(self):
        """Test validation works when scenario_metadata is provided."""
        from stuntdouble.validation import validate_mock_signature

        tool = GetWeatherTool()

        def mock_that_uses_metadata(scenario_metadata: dict):
            city_override = scenario_metadata.get("city_override", "NYC")

            def mock_fn(city: str, units: str = "celsius"):
                return {"temp": 72, "city": city_override}

            return mock_fn

        is_valid, error = validate_mock_signature(
            tool, mock_that_uses_metadata, scenario_metadata={"city_override": "LA"}
        )

        assert is_valid is True
        assert error is None

    def test_non_callable_mock_fn_result_fails(self):
        """Test that mock_fn returning non-callable fails validation."""
        from stuntdouble.validation import validate_mock_signature

        tool = GetWeatherTool()

        def bad_mock(scenario_metadata: dict):
            return "not a callable"  # Should return a callable

        is_valid, error = validate_mock_signature(tool, bad_mock)

        assert is_valid is False
        assert error is not None
        assert "callable" in error.lower()

    def test_mock_fn_exception_handled(self):
        """Test that exceptions in mock_fn are handled gracefully."""
        from stuntdouble.validation import validate_mock_signature

        tool = GetWeatherTool()

        def failing_mock(scenario_metadata: dict):
            raise RuntimeError("Mock factory failed")

        is_valid, error = validate_mock_signature(tool, failing_mock)

        assert is_valid is False
        assert error is not None
        assert "error" in error.lower()


class TestSignatureMismatchError:
    """Tests for SignatureMismatchError exception."""

    def test_error_contains_tool_name(self):
        """Test that error contains tool name."""
        from stuntdouble.exceptions import SignatureMismatchError

        error = SignatureMismatchError(
            tool_name="my_tool",
            expected="(city, units=...)",
            actual="(city)",
        )

        assert "my_tool" in str(error)
        assert error.tool_name == "my_tool"

    def test_error_contains_signatures(self):
        """Test that error contains expected and actual signatures."""
        from stuntdouble.exceptions import SignatureMismatchError

        error = SignatureMismatchError(
            tool_name="my_tool",
            expected="(city, units=...)",
            actual="(city)",
        )

        assert error.expected == "(city, units=...)"
        assert error.actual == "(city)"
        assert "Expected" in str(error)
        assert "Actual" in str(error)


class TestRegistryWithValidation:
    """Tests for MockToolsRegistry.register with tool parameter."""

    def test_register_with_valid_tool_succeeds(self):
        """Test that registration with valid mock succeeds."""
        from stuntdouble import MockToolsRegistry

        registry = MockToolsRegistry()
        tool = GetWeatherTool()

        def good_mock(scenario_metadata: dict):
            def mock_fn(city: str, units: str = "celsius"):
                return {"temp": 72}

            return mock_fn

        # Should not raise
        registry.register("get_weather", mock_fn=good_mock, tool=tool)

        assert registry.is_registered("get_weather")

    def test_register_with_invalid_tool_raises(self):
        """Test that registration with invalid mock raises SignatureMismatchError."""
        from stuntdouble.exceptions import SignatureMismatchError
        from stuntdouble import MockToolsRegistry

        registry = MockToolsRegistry()
        tool = GetWeatherTool()

        def bad_mock(scenario_metadata: dict):
            def mock_fn(city: str):  # Missing 'units'
                return {"temp": 72}

            return mock_fn

        with pytest.raises(SignatureMismatchError):
            registry.register("get_weather", mock_fn=bad_mock, tool=tool)

    def test_register_without_tool_skips_validation(self):
        """Test that registration without tool parameter skips validation."""
        from stuntdouble import MockToolsRegistry

        registry = MockToolsRegistry()

        # Any mock should work without tool validation
        def any_mock(scenario_metadata: dict):
            def mock_fn():  # Doesn't match any tool, but that's ok
                return "anything"

            return mock_fn

        # Should not raise
        registry.register("any_tool", mock_fn=any_mock)

        assert registry.is_registered("any_tool")


class TestWrapperWithSignatureValidation:
    """Tests for wrapper with runtime signature validation."""

    def _create_request(
        self,
        tool_name: str = "test_tool",
        tool_args: dict | None = None,
        scenario_metadata: dict | None = None,
    ):
        """Create a mock ToolCallRequest using native LangGraph types."""
        from unittest.mock import MagicMock

        from langgraph.prebuilt.tool_node import ToolCallRequest, ToolRuntime

        tool_call = {
            "name": tool_name,
            "args": tool_args or {},
            "id": "call-123",
        }

        config = {}
        if scenario_metadata is not None:
            config = {"configurable": {"scenario_metadata": scenario_metadata}}

        tool = MagicMock()
        tool.name = tool_name

        runtime = ToolRuntime(
            state={},
            context=None,
            config=config,
            stream_writer=None,
            tool_call_id=None,
            store=None,
        )

        return ToolCallRequest(
            tool_call=tool_call,
            tool=tool,
            state={},
            runtime=runtime,
        )

    def test_wrapper_with_signature_validation_enabled(self):
        """Test wrapper validates signatures when tools are provided."""
        import asyncio

        from stuntdouble import MockToolsRegistry
        from stuntdouble.wrapper import create_mockable_tool_wrapper

        registry = MockToolsRegistry()
        tool = GetWeatherTool()

        # Register a good mock
        def good_mock(scenario_metadata: dict):
            def mock_fn(city: str, units: str = "celsius"):
                return {"temp": 72}

            return mock_fn

        registry.register("get_weather", mock_fn=good_mock)

        # Create wrapper with tools for validation
        wrapper = create_mockable_tool_wrapper(
            registry,
            tools=[tool],
            validate_signatures=True,
        )

        request = self._create_request(
            tool_name="get_weather",
            tool_args={"city": "NYC"},
            scenario_metadata={"mode": "mock"},
        )

        async def mock_execute(req):
            raise AssertionError("Should not reach execute")

        result = asyncio.run(wrapper(request, mock_execute))
        assert "72" in result.content

    def test_wrapper_skips_validation_when_disabled(self):
        """Test wrapper skips validation when validate_signatures=False."""
        import asyncio

        from stuntdouble import MockToolsRegistry
        from stuntdouble.wrapper import create_mockable_tool_wrapper

        registry = MockToolsRegistry()
        tool = GetWeatherTool()

        # Register a bad mock (missing parameter)
        def bad_mock(scenario_metadata: dict):
            def mock_fn(city: str):  # Missing 'units'
                return {"temp": 72}

            return mock_fn

        registry.register("get_weather", mock_fn=bad_mock)

        # Create wrapper with validation disabled
        wrapper = create_mockable_tool_wrapper(
            registry,
            tools=[tool],
            validate_signatures=False,  # Disabled
        )

        request = self._create_request(
            tool_name="get_weather",
            tool_args={"city": "NYC"},
            scenario_metadata={"mode": "mock"},
        )

        async def mock_execute(req):
            raise AssertionError("Should not reach execute")

        # Should work since validation is disabled
        result = asyncio.run(wrapper(request, mock_execute))
        assert "72" in result.content


# =============================================================================
# Tests for validate_mock_parameters
# =============================================================================


class TestValidateMockParameters:
    """Tests for validate_mock_parameters function."""

    def test_valid_mock_cases_return_no_errors(self):
        """Test that valid mock cases pass validation with no errors."""
        from stuntdouble.validation import validate_mock_parameters

        tool = GetWeatherTool()
        mock_cases = [
            {"input": {"city": "NYC"}, "output": {"temp": 72}},
            {"input": {"city": "LA", "units": "fahrenheit"}, "output": {"temp": 85}},
        ]

        errors = validate_mock_parameters(tool, mock_cases)

        assert errors == []

    def test_unknown_parameter_returns_error(self):
        """Test that unknown parameter in input returns an error."""
        from stuntdouble.validation import validate_mock_parameters

        tool = GetWeatherTool()
        mock_cases = [
            {"input": {"wrong_param": "value"}, "output": {"temp": 70}},
        ]

        errors = validate_mock_parameters(tool, mock_cases)

        assert len(errors) == 1
        assert "Unknown parameter 'wrong_param'" in errors[0]
        assert "Valid parameters:" in errors[0]

    def test_non_dict_input_returns_error(self):
        """Test that non-dict input returns an error."""
        from stuntdouble.validation import validate_mock_parameters

        tool = GetWeatherTool()
        mock_cases = [
            {"input": "not a dict", "output": {"temp": 70}},
        ]

        errors = validate_mock_parameters(tool, mock_cases)

        assert len(errors) == 1
        assert "'input' must be a dict" in errors[0]
        assert "str" in errors[0]

    def test_catch_all_pattern_skips_validation(self):
        """Test that cases without input key (catch-all) skip validation."""
        from stuntdouble.validation import validate_mock_parameters

        tool = GetWeatherTool()
        mock_cases = [
            {"output": {"temp": 72}},  # No input key - catch-all pattern
        ]

        errors = validate_mock_parameters(tool, mock_cases)

        assert errors == []

    def test_multiple_unknown_parameters_returns_multiple_errors(self):
        """Test that multiple unknown parameters return multiple errors."""
        from stuntdouble.validation import validate_mock_parameters

        tool = GetWeatherTool()
        mock_cases = [
            {"input": {"bad_param1": "a", "bad_param2": "b"}, "output": "result"},
        ]

        errors = validate_mock_parameters(tool, mock_cases)

        assert len(errors) == 2
        assert any("bad_param1" in e for e in errors)
        assert any("bad_param2" in e for e in errors)

    def test_mixed_valid_and_invalid_cases(self):
        """Test validation with mix of valid and invalid cases."""
        from stuntdouble.validation import validate_mock_parameters

        tool = GetWeatherTool()
        mock_cases = [
            {"input": {"city": "NYC"}, "output": {"temp": 72}},  # Valid
            {"input": {"unknown": "x"}, "output": {"temp": 70}},  # Invalid
            {"input": {"city": "LA"}, "output": {"temp": 85}},  # Valid
        ]

        errors = validate_mock_parameters(tool, mock_cases)

        assert len(errors) == 1
        assert "Case 2" in errors[0]
        assert "unknown" in errors[0]


# =============================================================================
# Tests for validate_registry_mocks
# =============================================================================


class TestValidateRegistryMocks:
    """Tests for validate_registry_mocks function."""

    def test_valid_mocks_return_no_errors(self):
        """Test that valid mocks return no errors."""
        from stuntdouble.validation import validate_registry_mocks

        tools = [GetWeatherTool(), ListCustomersTool()]
        scenario_metadata = {
            "mocks": {
                "get_weather": [
                    {"input": {"city": "NYC"}, "output": {"temp": 72}},
                ],
            }
        }

        errors = validate_registry_mocks(tools, scenario_metadata)

        assert errors == {}

    def test_tool_not_found_returns_error(self):
        """Test that referencing unknown tool returns error."""
        from stuntdouble.validation import validate_registry_mocks

        tools = [GetWeatherTool()]
        scenario_metadata = {
            "mocks": {
                "nonexistent_tool": [{"output": "value"}],
            }
        }

        errors = validate_registry_mocks(tools, scenario_metadata)

        assert "nonexistent_tool" in errors
        assert "No tool named 'nonexistent_tool'" in errors["nonexistent_tool"][0]

    def test_single_dict_mock_case_normalized_to_list(self):
        """Test that single dict mock case is normalized to list."""
        from stuntdouble.validation import validate_registry_mocks

        tools = [GetWeatherTool()]
        scenario_metadata = {
            "mocks": {
                "get_weather": {"input": {"city": "NYC"}, "output": {"temp": 72}},
            }
        }

        errors = validate_registry_mocks(tools, scenario_metadata)

        assert errors == {}

    def test_direct_output_value_normalized(self):
        """Test that direct output value is normalized to mock case format."""
        from stuntdouble.validation import validate_registry_mocks

        tools = [GetWeatherTool()]
        scenario_metadata = {
            "mocks": {
                "get_weather": {"temp": 72},  # Direct output value
            }
        }

        errors = validate_registry_mocks(tools, scenario_metadata)

        # Should be normalized to [{"output": {"temp": 72}}] - no validation errors
        assert errors == {}

    def test_invalid_mock_parameter_returns_error(self):
        """Test that invalid parameter in mock returns error."""
        from stuntdouble.validation import validate_registry_mocks

        tools = [GetWeatherTool()]
        scenario_metadata = {
            "mocks": {
                "get_weather": [
                    {"input": {"invalid_param": "x"}, "output": {"temp": 72}},
                ],
            }
        }

        errors = validate_registry_mocks(tools, scenario_metadata)

        assert "get_weather" in errors
        assert any("invalid_param" in e for e in errors["get_weather"])

    def test_empty_mocks_returns_no_errors(self):
        """Test that empty mocks dict returns no errors."""
        from stuntdouble.validation import validate_registry_mocks

        tools = [GetWeatherTool()]
        scenario_metadata: dict[str, dict[str, str]] = {"mocks": {}}

        errors = validate_registry_mocks(tools, scenario_metadata)

        assert errors == {}

    def test_no_mocks_key_returns_no_errors(self):
        """Test that missing mocks key returns no errors."""
        from stuntdouble.validation import validate_registry_mocks

        tools = [GetWeatherTool()]
        scenario_metadata: dict[str, str] = {}

        errors = validate_registry_mocks(tools, scenario_metadata)

        assert errors == {}


# =============================================================================
# Tests for _get_tool_parameters
# =============================================================================


class TestGetToolParameters:
    """Tests for _get_tool_parameters function."""

    def test_pydantic_v2_model_fields(self):
        """Test extraction with Pydantic v2 model (model_fields)."""
        from stuntdouble.validation import _get_tool_parameters

        tool = GetWeatherTool()

        params = _get_tool_parameters(tool)

        assert params == {"city", "units"}

    def test_pydantic_v1_model_fallback(self):
        """Test extraction with Pydantic v1 model (__fields__)."""
        from stuntdouble.validation import _get_tool_parameters

        mock_tool = _create_mock_tool_with_v1_schema(
            "test_tool",
            {"param1": True, "param2": True},
        )

        params = _get_tool_parameters(mock_tool)

        assert params == {"param1", "param2"}

    def test_tool_args_fallback(self):
        """Test extraction using tool.args fallback."""
        from unittest.mock import MagicMock

        from stuntdouble.validation import _get_tool_parameters

        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.args_schema = None
        mock_tool.args = {"city": {"type": "string"}, "units": {"type": "string"}}

        params = _get_tool_parameters(mock_tool)

        assert params == {"city", "units"}

    def test_no_schema_returns_empty_set(self):
        """Test that tool with no schema returns empty set."""
        from unittest.mock import MagicMock

        from stuntdouble.validation import _get_tool_parameters

        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.args_schema = None
        mock_tool.args = None

        params = _get_tool_parameters(mock_tool)

        assert params == set()


# =============================================================================
# Tests for _get_required_parameters
# =============================================================================


class TestGetRequiredParameters:
    """Tests for _get_required_parameters function."""

    def test_pydantic_v2_required_fields(self):
        """Test extraction of required parameters with Pydantic v2."""
        from stuntdouble.validation import _get_required_parameters

        tool = GetWeatherTool()

        required = _get_required_parameters(tool)

        # city is required, units has a default
        assert "city" in required
        assert "units" not in required

    def test_pydantic_v1_required_fields(self):
        """Test extraction of required parameters with Pydantic v1 style."""
        from stuntdouble.validation import _get_required_parameters

        mock_tool = _create_mock_tool_with_v1_schema(
            "test_tool",
            {"required_param": True, "optional_param": False},
        )

        required = _get_required_parameters(mock_tool)

        assert required == {"required_param"}

    def test_no_schema_returns_empty_set(self):
        """Test that tool with no schema returns empty set."""
        from unittest.mock import MagicMock

        from stuntdouble.validation import _get_required_parameters

        mock_tool = MagicMock()
        mock_tool.args_schema = None

        required = _get_required_parameters(mock_tool)

        assert required == set()

    def test_all_optional_parameters(self):
        """Test tool where all parameters are optional."""
        from stuntdouble.validation import _get_required_parameters

        # ListCustomersTool has all optional parameters
        tool = ListCustomersTool()

        required = _get_required_parameters(tool)

        # Both tool_input and config have defaults
        assert required == set()


# =============================================================================
# Tests for _get_tool_parameter_info (JSON Schema dict support)
# =============================================================================


class TestGetToolParameterInfo:
    """Tests for _get_tool_parameter_info function (JSON Schema dict support)."""

    def test_json_schema_dict_with_required_params(self):
        """Test extraction from JSON Schema dict with required params."""
        from unittest.mock import MagicMock

        from stuntdouble.validation import _get_tool_parameter_info

        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        # JSON Schema format from MCP tools
        mock_tool.args_schema = {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name"},
                "units": {
                    "type": "string",
                    "default": "celsius",
                    "description": "Units",
                },
            },
            "required": ["city"],
        }

        params = _get_tool_parameter_info(mock_tool)

        assert "city" in params
        assert params["city"]["required"] is True
        assert "units" in params
        assert params["units"]["required"] is False
        assert params["units"]["has_default"] is True

    def test_json_schema_dict_wrong_type(self):
        """Test that JSON Schema with wrong type returns empty params."""
        from unittest.mock import MagicMock

        from stuntdouble.validation import _get_tool_parameter_info

        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        # Wrong type - not "object"
        mock_tool.args_schema = {
            "type": "string",  # Wrong type
            "description": "Just a string",
        }

        params = _get_tool_parameter_info(mock_tool)

        assert params == {}

    def test_json_schema_dict_no_properties(self):
        """Test JSON Schema dict with no properties."""
        from unittest.mock import MagicMock

        from stuntdouble.validation import _get_tool_parameter_info

        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.args_schema = {
            "type": "object",
            # No properties key
        }

        params = _get_tool_parameter_info(mock_tool)

        assert params == {}

    def test_tool_args_fallback_in_parameter_info(self):
        """Test _get_tool_parameter_info uses tool.args fallback."""
        from unittest.mock import MagicMock

        from stuntdouble.validation import _get_tool_parameter_info

        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.args_schema = None
        mock_tool.args = {"city": {"type": "string"}, "units": {"type": "string"}}

        params = _get_tool_parameter_info(mock_tool)

        assert "city" in params
        assert params["city"]["required"] is True  # Fallback assumes required
        assert "units" in params


# =============================================================================
# Tests for mock_fn with two-argument signature (new signature)
# =============================================================================


class TestMockFnWithConfigSignature:
    """Tests for validate_mock_signature with two-argument mock factories."""

    def test_mock_fn_with_config_parameter(self):
        """Test validation with mock_fn that accepts config parameter."""
        from stuntdouble.validation import validate_mock_signature

        tool = GetWeatherTool()

        # New signature: mock_fn(scenario_metadata, config)
        def mock_with_config(scenario_metadata: dict, config: dict):
            def mock_fn(city: str, units: str = "celsius"):
                return {"temp": 72}

            return mock_fn

        is_valid, error = validate_mock_signature(
            tool,
            mock_with_config,
            scenario_metadata={"test": True},
            config={"configurable": {}},
        )

        assert is_valid is True
        assert error is None


# =============================================================================
# Tests for _get_callable_parameter_info edge cases
# =============================================================================


class TestGetCallableParameterInfo:
    """Tests for _get_callable_parameter_info function."""

    def test_callable_without_signature(self):
        """Test that callable without inspectable signature returns empty dict."""
        from stuntdouble.validation import _get_callable_parameter_info

        # Built-in functions don't have inspectable signatures in some cases
        # Using a mock that raises when inspected
        class NoSignature:
            def __call__(self):
                pass

        # Create an object that will raise when signature is inspected
        NoSignature()
        # Override __signature__ to cause issues - but inspect.signature still works
        # Let's use a built-in instead
        params = _get_callable_parameter_info(len)  # Built-in without full signature

        # Should return empty dict without raising
        assert isinstance(params, dict)

    def test_callable_with_var_args(self):
        """Test that *args and **kwargs are skipped."""
        from stuntdouble.validation import _get_callable_parameter_info

        def func_with_varargs(a: str, *args, b: str = "default", **kwargs):
            pass

        params = _get_callable_parameter_info(func_with_varargs)

        # Only 'a' and 'b' should be included, not args/kwargs
        assert "a" in params
        assert params["a"]["required"] is True
        assert "b" in params
        assert params["b"]["required"] is False
        assert "args" not in params
        assert "kwargs" not in params


class TestGetToolParameterInfoPydanticV1:
    """Tests for _get_tool_parameter_info with Pydantic v1 style schema."""

    def test_pydantic_v1_style_schema(self):
        """Test parameter info extraction with Pydantic v1 style schema."""
        from stuntdouble.validation import _get_tool_parameter_info

        mock_tool = _create_mock_tool_with_v1_schema(
            "test_tool",
            {"required_param": True, "optional_param": False},
        )

        params = _get_tool_parameter_info(mock_tool)

        assert "required_param" in params
        assert params["required_param"]["required"] is True
        assert "optional_param" in params
        assert params["optional_param"]["required"] is False


class TestGetCallableParameterInfoExceptionHandling:
    """Tests for _get_callable_parameter_info exception handling."""

    def test_uninspectable_callable_returns_empty_dict(self):
        """Test that uninspectable callable returns empty dict."""
        from unittest.mock import MagicMock

        from stuntdouble.validation import _get_callable_parameter_info

        # Create a mock that will raise ValueError when signature is inspected
        mock_callable = MagicMock()
        # Mock __signature__ to raise ValueError
        type(mock_callable).__signature__ = property(
            lambda self: (_ for _ in ()).throw(ValueError("No signature"))
        )

        params = _get_callable_parameter_info(mock_callable)

        # Should return empty dict without raising
        assert params == {}
