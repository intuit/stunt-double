"""
Unit tests for ValueResolver placeholder resolution.
"""

import re
from datetime import datetime

from stuntdouble.resolving import (
    ResolverContext,
    ValueResolver,
    has_placeholders,
    resolve_output,
)


class TestValueResolverTimestamps:
    """Test timestamp placeholder resolution."""

    def test_now_placeholder(self):
        """{{now}} returns current ISO timestamp."""
        resolver = ValueResolver()
        ctx = ResolverContext()
        result = resolver.resolve_dynamic_values("{{now}}", ctx)

        # Should be valid ISO format
        datetime.fromisoformat(result)

    def test_today_placeholder(self):
        """{{today}} returns current date only."""
        resolver = ValueResolver()
        ctx = ResolverContext()
        result = resolver.resolve_dynamic_values("{{today}}", ctx)

        # Should be date-only format (no time component)
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", result)

    def test_relative_timestamp_plus_days(self):
        """{{now + 7d}} returns timestamp 7 days in future."""
        resolver = ValueResolver()
        base_time = datetime(2025, 1, 1, 12, 0, 0)
        ctx = ResolverContext(base_time=base_time)

        result = resolver.resolve_dynamic_values("{{now + 7d}}", ctx)
        expected = datetime(2025, 1, 8, 12, 0, 0)

        assert result == expected.isoformat()

    def test_relative_timestamp_minus_days(self):
        """{{now - 30d}} returns timestamp 30 days in past."""
        resolver = ValueResolver()
        base_time = datetime(2025, 1, 31, 12, 0, 0)
        ctx = ResolverContext(base_time=base_time)

        result = resolver.resolve_dynamic_values("{{now - 30d}}", ctx)
        expected = datetime(2025, 1, 1, 12, 0, 0)

        assert result == expected.isoformat()

    def test_relative_timestamp_weeks(self):
        """{{now + 2w}} returns timestamp 2 weeks in future."""
        resolver = ValueResolver()
        base_time = datetime(2025, 1, 1, 12, 0, 0)
        ctx = ResolverContext(base_time=base_time)

        result = resolver.resolve_dynamic_values("{{now + 2w}}", ctx)
        expected = datetime(2025, 1, 15, 12, 0, 0)

        assert result == expected.isoformat()

    def test_relative_timestamp_hours(self):
        """{{now - 6h}} returns timestamp 6 hours in past."""
        resolver = ValueResolver()
        base_time = datetime(2025, 1, 1, 12, 0, 0)
        ctx = ResolverContext(base_time=base_time)

        result = resolver.resolve_dynamic_values("{{now - 6h}}", ctx)
        expected = datetime(2025, 1, 1, 6, 0, 0)

        assert result == expected.isoformat()

    def test_today_relative(self):
        """{{today + 7d}} returns date 7 days in future."""
        resolver = ValueResolver()
        base_time = datetime(2025, 1, 1, 12, 0, 0)
        ctx = ResolverContext(base_time=base_time)

        result = resolver.resolve_dynamic_values("{{today + 7d}}", ctx)

        assert result == "2025-01-08"

    def test_start_of_month(self):
        """{{start_of_month}} returns first day of month at midnight."""
        resolver = ValueResolver()
        base_time = datetime(2025, 1, 15, 14, 30, 0)
        ctx = ResolverContext(base_time=base_time)

        result = resolver.resolve_dynamic_values("{{start_of_month}}", ctx)
        expected = datetime(2025, 1, 1, 0, 0, 0)

        assert result == expected.isoformat()

    def test_end_of_month(self):
        """{{end_of_month}} returns last day of month at 23:59:59."""
        resolver = ValueResolver()
        base_time = datetime(2025, 1, 15, 14, 30, 0)
        ctx = ResolverContext(base_time=base_time)

        result = resolver.resolve_dynamic_values("{{end_of_month}}", ctx)

        # January has 31 days
        assert "2025-01-31T23:59:59" in result

    def test_start_of_day(self):
        """{{start_of_day}} returns current day at midnight."""
        resolver = ValueResolver()
        base_time = datetime(2025, 1, 15, 14, 30, 45)
        ctx = ResolverContext(base_time=base_time)

        result = resolver.resolve_dynamic_values("{{start_of_day}}", ctx)
        expected = datetime(2025, 1, 15, 0, 0, 0)

        assert result == expected.isoformat()

    def test_end_of_day(self):
        """{{end_of_day}} returns current day at 23:59:59."""
        resolver = ValueResolver()
        base_time = datetime(2025, 1, 15, 14, 30, 45)
        ctx = ResolverContext(base_time=base_time)

        result = resolver.resolve_dynamic_values("{{end_of_day}}", ctx)

        assert "2025-01-15T23:59:59" in result


class TestValueResolverConfigRefs:
    """Test config reference placeholder resolution."""

    def test_simple_config_ref(self):
        """{{config.field_name}} returns config value."""
        resolver = ValueResolver()
        ctx = ResolverContext(config_data={"realm_id": "R-123"})
        result = resolver.resolve_dynamic_values("{{config.realm_id}}", ctx)
        assert result == "R-123"

    def test_config_ref_with_default(self):
        """{{config.field | default(value)}} uses default when missing."""
        resolver = ValueResolver()
        ctx = ResolverContext(config_data={})
        result = resolver.resolve_dynamic_values("{{config.env | default('prod')}}", ctx)
        assert result == "prod"

    def test_config_ref_preserves_type(self):
        """Config refs preserve non-string types."""
        resolver = ValueResolver()
        ctx = ResolverContext(config_data={"count": 42})
        result = resolver.resolve_dynamic_values("{{config.count}}", ctx)
        assert result == 42

    def test_config_and_input_refs_in_same_output(self):
        """Both config and input refs resolve in the same structure."""
        resolver = ValueResolver()
        ctx = ResolverContext(
            input_data={"query": "bills"},
            config_data={"realm_id": "R-1"},
        )
        result = resolver.resolve_dynamic_values({"q": "{{input.query}}", "r": "{{config.realm_id}}"}, ctx)
        assert result == {"q": "bills", "r": "R-1"}

    def test_config_ref_in_string_interpolation(self):
        """Config refs work in string interpolation."""
        resolver = ValueResolver()
        ctx = ResolverContext(config_data={"env": "staging"})
        result = resolver.resolve_dynamic_values("Environment: {{config.env}}", ctx)
        assert result == "Environment: staging"


class TestValueResolverInputRefs:
    """Test input reference placeholder resolution."""

    def test_simple_input_ref(self):
        """{{input.field_name}} returns input value."""
        resolver = ValueResolver()
        ctx = ResolverContext(input_data={"customer_id": "CUST-123"})

        result = resolver.resolve_dynamic_values("{{input.customer_id}}", ctx)

        assert result == "CUST-123"

    def test_input_ref_with_default(self):
        """{{input.field | default(value)}} uses default when missing."""
        resolver = ValueResolver()
        ctx = ResolverContext(input_data={})

        result = resolver.resolve_dynamic_values("{{input.page | default(1)}}", ctx)

        assert result == 1

    def test_input_ref_with_string_default(self):
        """{{input.field | default('value')}} uses string default."""
        resolver = ValueResolver()
        ctx = ResolverContext(input_data={})

        result = resolver.resolve_dynamic_values("{{input.status | default('active')}}", ctx)

        assert result == "active"

    def test_input_ref_in_nested_dict(self):
        """Input refs work in nested dict values."""
        resolver = ValueResolver()
        ctx = ResolverContext(input_data={"customer_id": "CUST-123"})

        result = resolver.resolve_dynamic_values(
            {"id": "{{input.customer_id}}", "nested": {"ref": "{{input.customer_id}}"}},
            ctx,
        )

        assert result == {"id": "CUST-123", "nested": {"ref": "CUST-123"}}

    def test_input_ref_preserves_type(self):
        """Input refs preserve the original value type."""
        resolver = ValueResolver()
        ctx = ResolverContext(input_data={"count": 42, "active": True})

        result = resolver.resolve_dynamic_values({"count": "{{input.count}}", "active": "{{input.active}}"}, ctx)

        assert result["count"] == 42
        assert result["active"] is True


class TestValueResolverGenerators:
    """Test generator function placeholder resolution."""

    def test_uuid_generator(self):
        """{{uuid}} generates valid UUID."""
        resolver = ValueResolver()
        ctx = ResolverContext()

        result = resolver.resolve_dynamic_values("{{uuid}}", ctx)

        # UUID format: 8-4-4-4-12 hex chars
        assert re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", result)

    def test_uuid_unique(self):
        """Each {{uuid}} generates unique value."""
        resolver = ValueResolver()
        ctx = ResolverContext()

        result1 = resolver.resolve_dynamic_values("{{uuid}}", ctx)
        result2 = resolver.resolve_dynamic_values("{{uuid}}", ctx)

        assert result1 != result2

    def test_random_int(self):
        """{{random_int(min, max)}} generates int in range."""
        resolver = ValueResolver()
        ctx = ResolverContext()

        for _ in range(10):  # Test multiple times
            result = resolver.resolve_dynamic_values("{{random_int(1, 100)}}", ctx)
            assert isinstance(result, int)
            assert 1 <= result <= 100

    def test_random_float(self):
        """{{random_float(min, max)}} generates float in range."""
        resolver = ValueResolver()
        ctx = ResolverContext()

        for _ in range(10):
            result = resolver.resolve_dynamic_values("{{random_float(0, 1000)}}", ctx)
            assert isinstance(result, float)
            assert 0 <= result <= 1000

    def test_choice(self):
        """{{choice('a', 'b', 'c')}} returns one of the choices."""
        resolver = ValueResolver()
        ctx = ResolverContext()

        for _ in range(10):
            result = resolver.resolve_dynamic_values("{{choice('active', 'pending', 'completed')}}", ctx)
            assert result in ["active", "pending", "completed"]

    def test_sequence(self):
        """{{sequence('prefix')}} generates incrementing IDs."""
        resolver = ValueResolver()
        counters: dict[str, int] = {}
        ctx = ResolverContext(sequence_counters=counters)

        result1 = resolver.resolve_dynamic_values("{{sequence('BILL')}}", ctx)
        result2 = resolver.resolve_dynamic_values("{{sequence('BILL')}}", ctx)
        result3 = resolver.resolve_dynamic_values("{{sequence('ORDER')}}", ctx)

        assert result1 == "BILL-001"
        assert result2 == "BILL-002"
        assert result3 == "ORDER-001"


class TestValueResolverNested:
    """Test resolution in nested structures."""

    def test_resolve_dict(self):
        """Resolve placeholders in dict values."""
        resolver = ValueResolver()
        ctx = ResolverContext(input_data={"id": "123"})

        result = resolver.resolve_dynamic_values(
            {
                "id": "{{input.id}}",
                "created_at": "{{now}}",
                "status": "active",  # Static value
            },
            ctx,
        )

        assert result["id"] == "123"
        assert "T" in result["created_at"]  # ISO format
        assert result["status"] == "active"

    def test_resolve_list(self):
        """Resolve placeholders in list items."""
        resolver = ValueResolver()
        ctx = ResolverContext()

        result = resolver.resolve_dynamic_values(["{{uuid}}", "static", "{{now}}"], ctx)

        assert len(result) == 3
        assert "-" in result[0]  # UUID format
        assert result[1] == "static"
        assert "T" in result[2]  # ISO format

    def test_resolve_deeply_nested(self):
        """Resolve in deeply nested structures."""
        resolver = ValueResolver()
        ctx = ResolverContext(input_data={"customer_id": "CUST-1"})

        result = resolver.resolve_dynamic_values(
            {
                "data": {
                    "customer": {
                        "id": "{{input.customer_id}}",
                        "orders": [
                            {"id": "{{sequence('ORD')}}"},
                            {"id": "{{sequence('ORD')}}"},
                        ],
                    }
                }
            },
            ctx,
        )

        assert result["data"]["customer"]["id"] == "CUST-1"
        assert result["data"]["customer"]["orders"][0]["id"] == "ORD-001"
        assert result["data"]["customer"]["orders"][1]["id"] == "ORD-002"

    def test_mixed_static_and_dynamic(self):
        """Static values pass through unchanged."""
        resolver = ValueResolver()
        ctx = ResolverContext()

        result = resolver.resolve_dynamic_values({"count": 42, "active": True, "price": 19.99, "name": None}, ctx)

        assert result["count"] == 42
        assert result["active"] is True
        assert result["price"] == 19.99
        assert result["name"] is None


class TestValueResolverStringInterpolation:
    """Test string interpolation with multiple placeholders."""

    def test_multiple_placeholders_in_string(self):
        """Multiple placeholders in same string."""
        resolver = ValueResolver()
        ctx = ResolverContext(input_data={"first": "John", "last": "Doe"})

        result = resolver.resolve_dynamic_values("Hello {{input.first}} {{input.last}}!", ctx)

        assert result == "Hello John Doe!"

    def test_text_around_placeholder(self):
        """Text before and after placeholder."""
        resolver = ValueResolver()
        ctx = ResolverContext(input_data={"id": "123"})

        result = resolver.resolve_dynamic_values("Customer ID: {{input.id}} (active)", ctx)

        assert result == "Customer ID: 123 (active)"


class TestHasPlaceholders:
    """Test has_placeholders detection function."""

    def test_string_with_placeholder(self):
        """Detect placeholder in string."""
        assert has_placeholders("{{now}}") is True
        assert has_placeholders("Created: {{now}}") is True

    def test_string_without_placeholder(self):
        """No false positives for regular strings."""
        assert has_placeholders("regular string") is False
        assert has_placeholders("{ not a placeholder }") is False

    def test_dict_with_placeholder(self):
        """Detect placeholder in dict values."""
        assert has_placeholders({"key": "{{now}}"}) is True
        assert has_placeholders({"nested": {"key": "{{now}}"}}) is True

    def test_list_with_placeholder(self):
        """Detect placeholder in list items."""
        assert has_placeholders(["{{now}}", "static"]) is True

    def test_primitive_values(self):
        """Primitives never have placeholders."""
        assert has_placeholders(42) is False
        assert has_placeholders(3.14) is False
        assert has_placeholders(True) is False
        assert has_placeholders(None) is False


class TestResolveOutputConvenience:
    """Test the resolve_output convenience function."""

    def test_resolve_output_basic(self):
        """resolve_output works with basic input."""
        result = resolve_output({"id": "{{input.customer_id}}"}, input_data={"customer_id": "CUST-123"})

        assert result == {"id": "CUST-123"}

    def test_resolve_output_with_counters(self):
        """resolve_output uses shared sequence counters."""
        counters: dict[str, int] = {}

        result1 = resolve_output({"id": "{{sequence('TEST')}}"}, sequence_counters=counters)
        result2 = resolve_output({"id": "{{sequence('TEST')}}"}, sequence_counters=counters)

        assert result1["id"] == "TEST-001"
        assert result2["id"] == "TEST-002"
