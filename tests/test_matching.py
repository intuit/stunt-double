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


class TestNotOperator:
    """Test $not negation operator."""

    def test_not_negates_eq(self):
        matcher = InputMatcher()
        assert matcher.matches({"status": {"$not": {"$eq": "deleted"}}}, {"status": "active"}) is True
        assert matcher.matches({"status": {"$not": {"$eq": "deleted"}}}, {"status": "deleted"}) is False

    def test_not_negates_in(self):
        matcher = InputMatcher()
        assert matcher.matches({"status": {"$not": {"$in": ["a", "b"]}}}, {"status": "c"}) is True
        assert matcher.matches({"status": {"$not": {"$in": ["a", "b"]}}}, {"status": "a"}) is False

    def test_not_negates_gt(self):
        matcher = InputMatcher()
        assert matcher.matches({"amount": {"$not": {"$gt": 100}}}, {"amount": 50}) is True
        assert matcher.matches({"amount": {"$not": {"$gt": 100}}}, {"amount": 150}) is False

    def test_not_with_regex(self):
        matcher = InputMatcher()
        assert matcher.matches({"id": {"$not": {"$regex": "^CUST-"}}}, {"id": "ORD-123"}) is True
        assert matcher.matches({"id": {"$not": {"$regex": "^CUST-"}}}, {"id": "CUST-123"}) is False

    def test_not_requires_dict(self):
        matcher = InputMatcher()
        assert matcher.matches({"field": {"$not": "invalid"}}, {"field": "test"}) is False


class TestAllOperator:
    """Test $all operator for array containment."""

    def test_all_matches_when_all_present(self):
        matcher = InputMatcher()
        assert matcher.matches({"tags": {"$all": ["a", "b"]}}, {"tags": ["a", "b", "c"]}) is True

    def test_all_fails_when_missing_element(self):
        matcher = InputMatcher()
        assert matcher.matches({"tags": {"$all": ["a", "d"]}}, {"tags": ["a", "b", "c"]}) is False

    def test_all_exact_match(self):
        matcher = InputMatcher()
        assert matcher.matches({"tags": {"$all": ["x", "y"]}}, {"tags": ["x", "y"]}) is True

    def test_all_empty_pattern(self):
        matcher = InputMatcher()
        assert matcher.matches({"tags": {"$all": []}}, {"tags": ["a", "b"]}) is True

    def test_all_non_list_actual(self):
        matcher = InputMatcher()
        assert matcher.matches({"tags": {"$all": ["a"]}}, {"tags": "not a list"}) is False


class TestElemMatchOperator:
    """Test $elemMatch operator for array element matching."""

    def test_elemmatch_finds_matching_element(self):
        matcher = InputMatcher()
        assert matcher.matches({"scores": {"$elemMatch": {"$gt": 80, "$lt": 90}}}, {"scores": [70, 85, 95]}) is True

    def test_elemmatch_no_matching_element(self):
        matcher = InputMatcher()
        assert matcher.matches({"scores": {"$elemMatch": {"$gt": 80, "$lt": 90}}}, {"scores": [70, 75, 95]}) is False

    def test_elemmatch_with_eq(self):
        matcher = InputMatcher()
        assert matcher.matches({"items": {"$elemMatch": {"$eq": "target"}}}, {"items": ["a", "target", "b"]}) is True
        assert matcher.matches({"items": {"$elemMatch": {"$eq": "target"}}}, {"items": ["a", "b", "c"]}) is False

    def test_elemmatch_non_list_actual(self):
        matcher = InputMatcher()
        assert matcher.matches({"scores": {"$elemMatch": {"$gt": 5}}}, {"scores": 10}) is False

    def test_elemmatch_requires_dict(self):
        matcher = InputMatcher()
        assert matcher.matches({"scores": {"$elemMatch": "invalid"}}, {"scores": [1, 2, 3]}) is False


class TestTypeOperator:
    """Test $type operator for type checking."""

    def test_type_str(self):
        matcher = InputMatcher()
        assert matcher.matches({"field": {"$type": "str"}}, {"field": "hello"}) is True
        assert matcher.matches({"field": {"$type": "str"}}, {"field": 123}) is False

    def test_type_int(self):
        matcher = InputMatcher()
        assert matcher.matches({"field": {"$type": "int"}}, {"field": 42}) is True
        assert matcher.matches({"field": {"$type": "int"}}, {"field": 3.14}) is False

    def test_type_float(self):
        matcher = InputMatcher()
        assert matcher.matches({"field": {"$type": "float"}}, {"field": 3.14}) is True
        assert matcher.matches({"field": {"$type": "float"}}, {"field": 42}) is False

    def test_type_bool(self):
        matcher = InputMatcher()
        assert matcher.matches({"field": {"$type": "bool"}}, {"field": True}) is True
        assert matcher.matches({"field": {"$type": "bool"}}, {"field": "true"}) is False

    def test_type_list(self):
        matcher = InputMatcher()
        assert matcher.matches({"field": {"$type": "list"}}, {"field": [1, 2]}) is True
        assert matcher.matches({"field": {"$type": "list"}}, {"field": "not list"}) is False

    def test_type_dict(self):
        matcher = InputMatcher()
        assert matcher.matches({"field": {"$type": "dict"}}, {"field": {"a": 1}}) is True
        assert matcher.matches({"field": {"$type": "dict"}}, {"field": [1, 2]}) is False

    def test_type_none(self):
        matcher = InputMatcher()
        assert matcher.matches({"field": {"$type": "None"}}, {"field": None}) is True
        assert matcher.matches({"field": {"$type": "None"}}, {"field": "something"}) is False

    def test_type_unknown(self):
        matcher = InputMatcher()
        assert matcher.matches({"field": {"$type": "unknown_type"}}, {"field": "test"}) is False


class TestSizeOperator:
    """Test $size operator for length checking."""

    def test_size_list(self):
        matcher = InputMatcher()
        assert matcher.matches({"items": {"$size": 3}}, {"items": [1, 2, 3]}) is True
        assert matcher.matches({"items": {"$size": 3}}, {"items": [1, 2]}) is False

    def test_size_string(self):
        matcher = InputMatcher()
        assert matcher.matches({"name": {"$size": 5}}, {"name": "hello"}) is True
        assert matcher.matches({"name": {"$size": 5}}, {"name": "hi"}) is False

    def test_size_empty(self):
        matcher = InputMatcher()
        assert matcher.matches({"items": {"$size": 0}}, {"items": []}) is True
        assert matcher.matches({"items": {"$size": 0}}, {"items": [1]}) is False

    def test_size_non_sized_value(self):
        matcher = InputMatcher()
        assert matcher.matches({"field": {"$size": 1}}, {"field": 42}) is False


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
