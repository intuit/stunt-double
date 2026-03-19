"""
Unit tests for stuntdouble.exceptions module.
"""

import pytest


class TestMissingMockError:
    """Tests for MissingMockError exception."""

    def test_basic_construction(self):
        """Test basic exception construction."""
        from stuntdouble.exceptions import MissingMockError

        error = MissingMockError("my_tool")

        assert error.tool_name == "my_tool"
        assert "my_tool" in str(error)

    def test_default_message(self):
        """Test default error message includes tool name and instructions."""
        from stuntdouble.exceptions import MissingMockError

        error = MissingMockError("get_weather")

        message = str(error)
        assert "get_weather" in message
        assert "scenario_metadata present" in message
        assert "registry.register" in message

    def test_custom_message(self):
        """Test custom error message overrides default."""
        from stuntdouble.exceptions import MissingMockError

        custom_msg = "Custom error message for testing"
        error = MissingMockError("my_tool", message=custom_msg)

        assert str(error) == custom_msg
        assert error.tool_name == "my_tool"

    def test_is_exception_subclass(self):
        """Test that MissingMockError is an Exception subclass."""
        from stuntdouble.exceptions import MissingMockError

        error = MissingMockError("test")
        assert isinstance(error, Exception)

    def test_can_be_raised_and_caught(self):
        """Test that MissingMockError can be raised and caught."""
        from stuntdouble.exceptions import MissingMockError

        with pytest.raises(MissingMockError) as exc_info:
            raise MissingMockError("unknown_tool")

        assert exc_info.value.tool_name == "unknown_tool"
