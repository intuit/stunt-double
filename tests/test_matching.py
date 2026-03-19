"""
Unit tests for InputMatcher operator-based matching.
"""

from stuntdouble.matching import InputMatcher, matches


class TestInputMatcherBasic:
    """Test basic matching functionality."""

    def test_none_pattern_matches_anything(self):
        """None pattern (catch-all) matches any input."""
        matcher = InputMatcher()
        assert matcher.matches(None, {"any": "input"}) is True
        assert matcher.matches(None, {}) is True
        assert matcher.matches(None, {"a": 1, "b": 2, "c": 3}) is True

    def test_empty_pattern_matches_anything(self):
        """Empty dict pattern matches any input."""
        matcher = InputMatcher()
        assert matcher.matches({}, {"any": "input"}) is True
        assert matcher.matches({}, {}) is True

    def test_exact_match(self):
        """Exact value matching (implicit $eq)."""
        matcher = InputMatcher()
        assert matcher.matches({"status": "active"}, {"status": "active"}) is True
        assert matcher.matches({"status": "active"}, {"status": "inactive"}) is False

    def test_extra_keys_ignored(self):
        """Extra keys in actual input are ignored (lenient matching)."""
        matcher = InputMatcher()
        assert (
            matcher.matches(
                {"status": "active"},
                {"status": "active", "extra": "ignored", "more": 123},
            )
            is True
        )

    def test_missing_key_fails(self):
        """Missing required key fails match."""
        matcher = InputMatcher()
        assert matcher.matches({"status": "active"}, {"other_field": "value"}) is False

    def test_multiple_conditions_and(self):
        """Multiple conditions are AND-ed together."""
        matcher = InputMatcher()
        pattern = {"status": "active", "tier": "premium"}

        assert matcher.matches(pattern, {"status": "active", "tier": "premium"}) is True
        assert matcher.matches(pattern, {"status": "active", "tier": "basic"}) is False
        assert matcher.matches(pattern, {"status": "inactive", "tier": "premium"}) is False


class TestInputMatcherOperators:
    """Test operator-based matching."""

    def test_eq_operator(self):
        """$eq operator for explicit equality."""
        matcher = InputMatcher()
        assert matcher.matches({"status": {"$eq": "active"}}, {"status": "active"}) is True
        assert matcher.matches({"status": {"$eq": "active"}}, {"status": "inactive"}) is False

    def test_ne_operator(self):
        """$ne operator for not equal."""
        matcher = InputMatcher()
        assert matcher.matches({"status": {"$ne": "deleted"}}, {"status": "active"}) is True
        assert matcher.matches({"status": {"$ne": "deleted"}}, {"status": "deleted"}) is False

    def test_gt_operator(self):
        """$gt operator for greater than."""
        matcher = InputMatcher()
        assert matcher.matches({"amount": {"$gt": 100}}, {"amount": 150}) is True
        assert matcher.matches({"amount": {"$gt": 100}}, {"amount": 100}) is False
        assert matcher.matches({"amount": {"$gt": 100}}, {"amount": 50}) is False

    def test_gte_operator(self):
        """$gte operator for greater than or equal."""
        matcher = InputMatcher()
        assert matcher.matches({"amount": {"$gte": 100}}, {"amount": 150}) is True
        assert matcher.matches({"amount": {"$gte": 100}}, {"amount": 100}) is True
        assert matcher.matches({"amount": {"$gte": 100}}, {"amount": 50}) is False

    def test_lt_operator(self):
        """$lt operator for less than."""
        matcher = InputMatcher()
        assert matcher.matches({"amount": {"$lt": 100}}, {"amount": 50}) is True
        assert matcher.matches({"amount": {"$lt": 100}}, {"amount": 100}) is False
        assert matcher.matches({"amount": {"$lt": 100}}, {"amount": 150}) is False

    def test_lte_operator(self):
        """$lte operator for less than or equal."""
        matcher = InputMatcher()
        assert matcher.matches({"amount": {"$lte": 100}}, {"amount": 50}) is True
        assert matcher.matches({"amount": {"$lte": 100}}, {"amount": 100}) is True
        assert matcher.matches({"amount": {"$lte": 100}}, {"amount": 150}) is False

    def test_in_operator(self):
        """$in operator for value in list."""
        matcher = InputMatcher()
        assert matcher.matches({"status": {"$in": ["active", "pending"]}}, {"status": "active"}) is True
        assert matcher.matches({"status": {"$in": ["active", "pending"]}}, {"status": "pending"}) is True
        assert matcher.matches({"status": {"$in": ["active", "pending"]}}, {"status": "deleted"}) is False

    def test_nin_operator(self):
        """$nin operator for value not in list."""
        matcher = InputMatcher()
        assert matcher.matches({"status": {"$nin": ["deleted", "archived"]}}, {"status": "active"}) is True
        assert matcher.matches({"status": {"$nin": ["deleted", "archived"]}}, {"status": "deleted"}) is False

    def test_contains_operator(self):
        """$contains operator for substring match."""
        matcher = InputMatcher()
        assert matcher.matches({"name": {"$contains": "Corp"}}, {"name": "Acme Corporation"}) is True
        assert matcher.matches({"name": {"$contains": "Corp"}}, {"name": "Acme LLC"}) is False

    def test_regex_operator(self):
        """$regex operator for regex pattern match."""
        matcher = InputMatcher()
        assert matcher.matches({"id": {"$regex": "^CUST-\\d+"}}, {"id": "CUST-123"}) is True
        assert matcher.matches({"id": {"$regex": "^CUST-\\d+"}}, {"id": "CUST-999"}) is True
        assert matcher.matches({"id": {"$regex": "^CUST-\\d+"}}, {"id": "ORD-123"}) is False

    def test_exists_operator_true(self):
        """$exists: true operator for key existence."""
        matcher = InputMatcher()
        assert matcher.matches({"optional_field": {"$exists": True}}, {"optional_field": "value"}) is True
        assert matcher.matches({"optional_field": {"$exists": True}}, {"other_field": "value"}) is False

    def test_exists_operator_false(self):
        """$exists: false operator for key absence."""
        matcher = InputMatcher()
        assert matcher.matches({"optional_field": {"$exists": False}}, {"other_field": "value"}) is True
        assert matcher.matches({"optional_field": {"$exists": False}}, {"optional_field": "value"}) is False

    def test_multiple_operators_same_field(self):
        """Multiple operators on same field (AND logic)."""
        matcher = InputMatcher()
        pattern = {"amount": {"$gt": 100, "$lt": 500}}

        assert matcher.matches(pattern, {"amount": 250}) is True
        assert matcher.matches(pattern, {"amount": 50}) is False
        assert matcher.matches(pattern, {"amount": 600}) is False


class TestInputMatcherEdgeCases:
    """Test edge cases and error handling."""

    def test_numeric_string_comparison(self):
        """String numbers should be converted for numeric comparison."""
        matcher = InputMatcher()
        assert matcher.matches({"amount": {"$gt": 100}}, {"amount": "150"}) is True
        assert matcher.matches({"amount": {"$gt": "100"}}, {"amount": 150}) is True

    def test_none_value_handling(self):
        """None values should be handled gracefully."""
        matcher = InputMatcher()
        assert matcher.matches({"field": {"$exists": True}}, {"field": None}) is False
        assert matcher.matches({"field": {"$contains": "x"}}, {"field": None}) is False

    def test_unknown_operator_warning(self):
        """Unknown operators should return False with warning."""
        matcher = InputMatcher()
        assert matcher.matches({"field": {"$unknown": "value"}}, {"field": "test"}) is False

    def test_type_mismatch_in_comparison(self):
        """Type mismatches in comparison should return False."""
        matcher = InputMatcher()
        assert matcher.matches({"amount": {"$gt": 100}}, {"amount": "not a number"}) is False


class TestConvenienceFunction:
    """Test the module-level matches() convenience function."""

    def test_matches_function(self):
        """matches() function should work same as InputMatcher.matches()."""
        assert matches({"status": "active"}, {"status": "active"}) is True
        assert matches({"amount": {"$gt": 100}}, {"amount": 150}) is True
        assert matches(None, {"any": "input"}) is True
