"""
Unit tests for StuntDouble LangGraph call recorder.

Tests:
- CallRecord: Data class for recording call details
- CallRecorder: Recording and verification of tool calls
"""

import pytest

from stuntdouble.exceptions import MockAssertionError
from stuntdouble.recorder import CallRecord, CallRecorder


class TestCallRecord:
    """Tests for CallRecord data class."""

    def test_basic_record_creation(self):
        """Test creating a basic call record."""
        record = CallRecord(
            tool_name="get_customer",
            args={"customer_id": "123"},
        )

        assert record.tool_name == "get_customer"
        assert record.args == {"customer_id": "123"}
        assert record.result is None
        assert record.error is None
        assert record.was_mocked is False
        assert record.scenario_id is None

    def test_record_with_result(self):
        """Test record with result value."""
        record = CallRecord(
            tool_name="get_customer",
            args={"customer_id": "123"},
            result={"name": "Alice"},
            was_mocked=True,
        )

        assert record.result == {"name": "Alice"}
        assert record.was_mocked is True

    def test_record_with_error(self):
        """Test record with error."""
        error = ValueError("Test error")
        record = CallRecord(
            tool_name="failing_tool",
            args={},
            error=error,
        )

        assert record.error is error
        assert record.result is None

    def test_record_repr(self):
        """Test string representation."""
        record = CallRecord(
            tool_name="get_customer",
            args={"customer_id": "123", "include_orders": True},
            was_mocked=True,
        )

        repr_str = repr(record)
        assert "get_customer" in repr_str
        assert "mocked" in repr_str

    def test_record_repr_with_error(self):
        """Test repr shows error when present."""
        error = ValueError("test")
        record = CallRecord(
            tool_name="failing_tool",
            args={},
            error=error,
        )

        repr_str = repr(record)
        assert "error" in repr_str


class TestCallRecorder:
    """Tests for CallRecorder."""

    def test_empty_recorder(self):
        """Test newly created recorder has no calls."""
        recorder = CallRecorder()

        assert len(recorder) == 0
        assert recorder.calls == []
        assert recorder.call_count() == 0

    def test_record_single_call(self):
        """Test recording a single call."""
        recorder = CallRecorder()

        recorder.record(
            tool_name="get_customer",
            args={"customer_id": "123"},
            result={"name": "Test"},
            was_mocked=True,
        )

        assert len(recorder) == 1
        assert recorder.call_count("get_customer") == 1

    def test_record_multiple_calls(self):
        """Test recording multiple calls."""
        recorder = CallRecorder()

        recorder.record("tool_a", {"x": 1})
        recorder.record("tool_b", {"y": 2})
        recorder.record("tool_a", {"x": 3})

        assert len(recorder) == 3
        assert recorder.call_count("tool_a") == 2
        assert recorder.call_count("tool_b") == 1

    def test_clear_calls(self):
        """Test clearing recorded calls."""
        recorder = CallRecorder()

        recorder.record("tool_a", {})
        recorder.record("tool_b", {})

        assert len(recorder) == 2

        recorder.clear()

        assert len(recorder) == 0
        assert recorder.calls == []

    def test_get_calls_all(self):
        """Test getting all calls."""
        recorder = CallRecorder()

        recorder.record("tool_a", {"x": 1})
        recorder.record("tool_b", {"y": 2})

        calls = recorder.get_calls()

        assert len(calls) == 2
        assert calls[0].tool_name == "tool_a"
        assert calls[1].tool_name == "tool_b"

    def test_get_calls_filtered(self):
        """Test getting calls filtered by tool name."""
        recorder = CallRecorder()

        recorder.record("tool_a", {"x": 1})
        recorder.record("tool_b", {"y": 2})
        recorder.record("tool_a", {"x": 3})

        calls = recorder.get_calls("tool_a")

        assert len(calls) == 2
        assert all(c.tool_name == "tool_a" for c in calls)

    def test_was_called_true(self):
        """Test was_called returns True when called."""
        recorder = CallRecorder()

        recorder.record("get_customer", {"id": "123"})

        assert recorder.was_called("get_customer") is True

    def test_was_called_false(self):
        """Test was_called returns False when not called."""
        recorder = CallRecorder()

        recorder.record("other_tool", {})

        assert recorder.was_called("get_customer") is False

    def test_was_called_with_args(self):
        """Test was_called with argument matching."""
        recorder = CallRecorder()

        recorder.record("get_customer", {"customer_id": "123", "include_orders": True})

        assert recorder.was_called("get_customer", customer_id="123") is True
        assert recorder.was_called("get_customer", customer_id="456") is False
        assert recorder.was_called("get_customer", customer_id="123", include_orders=True) is True

    def test_get_last_call(self):
        """Test getting the last call."""
        recorder = CallRecorder()

        recorder.record("tool_a", {"x": 1})
        recorder.record("tool_a", {"x": 2})
        recorder.record("tool_a", {"x": 3})

        last = recorder.get_last_call("tool_a")

        assert last is not None
        assert last.args["x"] == 3

    def test_get_last_call_none(self):
        """Test get_last_call returns None when no calls."""
        recorder = CallRecorder()

        assert recorder.get_last_call("unknown") is None

    def test_get_first_call(self):
        """Test getting the first call."""
        recorder = CallRecorder()

        recorder.record("tool_a", {"x": 1})
        recorder.record("tool_a", {"x": 2})

        first = recorder.get_first_call("tool_a")

        assert first is not None
        assert first.args["x"] == 1

    def test_get_args(self):
        """Test getting arguments from a call."""
        recorder = CallRecorder()

        recorder.record("tool_a", {"x": 1, "y": 2})

        args = recorder.get_args("tool_a")

        assert args == {"x": 1, "y": 2}

    def test_get_args_by_index(self):
        """Test getting arguments by call index."""
        recorder = CallRecorder()

        recorder.record("tool_a", {"x": 1})
        recorder.record("tool_a", {"x": 2})
        recorder.record("tool_a", {"x": 3})

        assert recorder.get_args("tool_a", call_index=0) == {"x": 1}
        assert recorder.get_args("tool_a", call_index=1) == {"x": 2}
        assert recorder.get_args("tool_a", call_index=-1) == {"x": 3}

    def test_get_result(self):
        """Test getting result from a call."""
        recorder = CallRecorder()

        recorder.record("tool_a", {}, result={"data": "test"})

        result = recorder.get_result("tool_a")

        assert result == {"data": "test"}

    def test_summary(self):
        """Test summary output."""
        recorder = CallRecorder()

        recorder.record("tool_a", {"x": 1}, was_mocked=True)
        recorder.record("tool_b", {"y": 2}, was_mocked=False)

        summary = recorder.summary()

        assert "2 call(s)" in summary
        assert "tool_a" in summary
        assert "tool_b" in summary
        assert "MOCKED" in summary
        assert "REAL" in summary

    def test_summary_empty(self):
        """Test summary with no calls."""
        recorder = CallRecorder()

        summary = recorder.summary()

        assert "No calls recorded" in summary


class TestCallRecorderAssertions:
    """Tests for CallRecorder assertion methods."""

    def test_assert_called_passes(self):
        """Test assert_called passes when tool was called."""
        recorder = CallRecorder()

        recorder.record("get_customer", {"id": "123"})

        # Should not raise
        recorder.assert_called("get_customer")

    def test_assert_called_fails(self):
        """Test assert_called fails when tool was not called."""
        recorder = CallRecorder()

        recorder.record("other_tool", {})

        with pytest.raises(MockAssertionError) as exc_info:
            recorder.assert_called("get_customer")

        assert "get_customer" in str(exc_info.value)
        assert "other_tool" in str(exc_info.value)

    def test_assert_not_called_passes(self):
        """Test assert_not_called passes when tool was not called."""
        recorder = CallRecorder()

        recorder.record("other_tool", {})

        # Should not raise
        recorder.assert_not_called("get_customer")

    def test_assert_not_called_fails(self):
        """Test assert_not_called fails when tool was called."""
        recorder = CallRecorder()

        recorder.record("get_customer", {"id": "123"})

        with pytest.raises(MockAssertionError) as exc_info:
            recorder.assert_not_called("get_customer")

        assert "get_customer" in str(exc_info.value)
        assert "1 time" in str(exc_info.value)

    def test_assert_called_once_passes(self):
        """Test assert_called_once passes with exactly one call."""
        recorder = CallRecorder()

        recorder.record("get_customer", {})

        # Should not raise
        recorder.assert_called_once("get_customer")

    def test_assert_called_once_fails_zero(self):
        """Test assert_called_once fails with zero calls."""
        recorder = CallRecorder()

        with pytest.raises(MockAssertionError) as exc_info:
            recorder.assert_called_once("get_customer")

        assert "0 time" in str(exc_info.value)

    def test_assert_called_once_fails_multiple(self):
        """Test assert_called_once fails with multiple calls."""
        recorder = CallRecorder()

        recorder.record("get_customer", {})
        recorder.record("get_customer", {})

        with pytest.raises(MockAssertionError) as exc_info:
            recorder.assert_called_once("get_customer")

        assert "2 time" in str(exc_info.value)

    def test_assert_called_times_passes(self):
        """Test assert_called_times passes with correct count."""
        recorder = CallRecorder()

        recorder.record("tool_a", {})
        recorder.record("tool_a", {})
        recorder.record("tool_a", {})

        # Should not raise
        recorder.assert_called_times("tool_a", 3)

    def test_assert_called_times_fails(self):
        """Test assert_called_times fails with wrong count."""
        recorder = CallRecorder()

        recorder.record("tool_a", {})
        recorder.record("tool_a", {})

        with pytest.raises(MockAssertionError) as exc_info:
            recorder.assert_called_times("tool_a", 5)

        assert "5 time" in str(exc_info.value)
        assert "2 time" in str(exc_info.value)

    def test_assert_called_with_passes(self):
        """Test assert_called_with passes with matching args."""
        recorder = CallRecorder()

        recorder.record("get_customer", {"customer_id": "123", "extra": "data"})

        # Should not raise - partial match
        recorder.assert_called_with("get_customer", customer_id="123")

    def test_assert_called_with_fails_no_calls(self):
        """Test assert_called_with fails when not called."""
        recorder = CallRecorder()

        with pytest.raises(MockAssertionError) as exc_info:
            recorder.assert_called_with("get_customer", customer_id="123")

        assert "never called" in str(exc_info.value)

    def test_assert_called_with_fails_wrong_args(self):
        """Test assert_called_with fails with wrong args."""
        recorder = CallRecorder()

        recorder.record("get_customer", {"customer_id": "456"})

        with pytest.raises(MockAssertionError) as exc_info:
            recorder.assert_called_with("get_customer", customer_id="123")

        assert "123" in str(exc_info.value)
        assert "456" in str(exc_info.value)

    def test_assert_called_with_any_match(self):
        """Test assert_called_with passes if ANY call matches."""
        recorder = CallRecorder()

        recorder.record("tool_a", {"x": 1})
        recorder.record("tool_a", {"x": 2})
        recorder.record("tool_a", {"x": 3})

        # Should pass because second call matches
        recorder.assert_called_with("tool_a", x=2)

    def test_assert_last_called_with_passes(self):
        """Test assert_last_called_with passes with matching last call."""
        recorder = CallRecorder()

        recorder.record("tool_a", {"x": 1})
        recorder.record("tool_a", {"x": 2})

        # Should pass - last call has x=2
        recorder.assert_last_called_with("tool_a", x=2)

    def test_assert_last_called_with_fails(self):
        """Test assert_last_called_with fails with non-matching last call."""
        recorder = CallRecorder()

        recorder.record("tool_a", {"x": 1})
        recorder.record("tool_a", {"x": 2})

        with pytest.raises(MockAssertionError):
            recorder.assert_last_called_with("tool_a", x=1)  # Last call has x=2

    def test_assert_any_call_alias(self):
        """Test assert_any_call works as alias for assert_called_with."""
        recorder = CallRecorder()

        recorder.record("tool_a", {"x": 1})

        # Should not raise
        recorder.assert_any_call("tool_a", x=1)

    def test_assert_call_order_passes(self):
        """Test assert_call_order passes with correct order."""
        recorder = CallRecorder()

        recorder.record("tool_a", {})
        recorder.record("tool_b", {})
        recorder.record("tool_c", {})

        # Should not raise
        recorder.assert_call_order("tool_a", "tool_b", "tool_c")

    def test_assert_call_order_passes_subsequence(self):
        """Test assert_call_order passes with subsequence."""
        recorder = CallRecorder()

        recorder.record("tool_a", {})
        recorder.record("tool_x", {})  # Extra call
        recorder.record("tool_b", {})
        recorder.record("tool_y", {})  # Extra call
        recorder.record("tool_c", {})

        # Should pass - a, b, c appear in order
        recorder.assert_call_order("tool_a", "tool_b", "tool_c")

    def test_assert_call_order_fails(self):
        """Test assert_call_order fails with wrong order."""
        recorder = CallRecorder()

        recorder.record("tool_a", {})
        recorder.record("tool_c", {})
        recorder.record("tool_b", {})

        with pytest.raises(MockAssertionError) as exc_info:
            recorder.assert_call_order("tool_a", "tool_b", "tool_c")

        assert "order" in str(exc_info.value).lower()


class TestCallRecorderThreadSafety:
    """Tests for thread safety of CallRecorder."""

    def test_concurrent_recording(self):
        """Test that concurrent recording is safe."""
        import threading

        recorder = CallRecorder()
        num_threads = 10
        calls_per_thread = 100

        def record_calls(thread_id):
            for i in range(calls_per_thread):
                recorder.record(f"tool_{thread_id}", {"i": i})

        threads = [threading.Thread(target=record_calls, args=(i,)) for i in range(num_threads)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All calls should be recorded
        assert len(recorder) == num_threads * calls_per_thread

    def test_concurrent_read_write(self):
        """Test concurrent reading and writing."""
        import threading

        recorder = CallRecorder()
        stop_event = threading.Event()
        errors = []

        def writer():
            for i in range(100):
                recorder.record("tool", {"i": i})

        def reader():
            while not stop_event.is_set():
                try:
                    _ = recorder.calls  # Read calls
                    _ = recorder.call_count()
                except Exception as e:
                    errors.append(e)

        reader_thread = threading.Thread(target=reader)
        writer_thread = threading.Thread(target=writer)

        reader_thread.start()
        writer_thread.start()

        writer_thread.join()
        stop_event.set()
        reader_thread.join()

        # No errors should have occurred
        assert len(errors) == 0


class TestCallRecorderRepr:
    """Tests for CallRecorder string representation."""

    def test_repr_empty(self):
        """Test repr with no calls."""
        recorder = CallRecorder()

        repr_str = repr(recorder)

        assert "CallRecorder" in repr_str
        assert "0" in repr_str

    def test_repr_with_calls(self):
        """Test repr with calls."""
        recorder = CallRecorder()

        recorder.record("tool_a", {})
        recorder.record("tool_b", {})

        repr_str = repr(recorder)

        assert "CallRecorder" in repr_str
        assert "2" in repr_str
