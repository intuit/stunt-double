"""
Input matchers for enhanced mock pattern matching.

Provides operator-based matching for input patterns, enabling conditional
mocking based on input values using MongoDB-style query operators.

Supported operators:
- $eq: Exact equality (default)
- $ne: Not equal
- $gt, $gte, $lt, $lte: Numeric comparisons
- $in, $nin: Value in/not in list
- $contains: String contains substring
- $regex: Regular expression match
- $exists: Key existence check
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class InputMatcher:
    """
    Handles operator-based input pattern matching.

    Supports MongoDB-style query operators for flexible input matching.
    Patterns can use exact values or operator dictionaries.

    Examples:
        >>> matcher = InputMatcher()
        >>> # Exact match
        >>> matcher.matches({"status": "active"}, {"status": "active"})
        True
        >>> # Operator match
        >>> matcher.matches({"amount": {"$gt": 1000}}, {"amount": 1500})
        True
        >>> # Multiple conditions
        >>> matcher.matches(
        ...     {"status": "active", "amount": {"$gte": 100}},
        ...     {"status": "active", "amount": 150}
        ... )
        True
    """

    # Operator functions: (actual_value, pattern_value) -> bool
    OPERATORS: dict[str, Any] = {
        "$eq": lambda a, b: a == b,
        "$ne": lambda a, b: a != b,
        "$gt": lambda a, b: _compare_numeric(a, b, lambda x, y: x > y),
        "$gte": lambda a, b: _compare_numeric(a, b, lambda x, y: x >= y),
        "$lt": lambda a, b: _compare_numeric(a, b, lambda x, y: x < y),
        "$lte": lambda a, b: _compare_numeric(a, b, lambda x, y: x <= y),
        "$in": lambda a, b: a in b if isinstance(b, list | tuple | set) else False,
        "$nin": lambda a, b: a not in b if isinstance(b, list | tuple | set) else True,
        "$contains": lambda a, b: b in str(a) if a is not None else False,
        "$regex": lambda a, b: bool(re.search(b, str(a))) if a is not None else False,
        "$exists": lambda a, b: (a is not None) == b,
    }

    def matches(self, pattern: dict[str, Any] | None, actual: dict[str, Any]) -> bool:
        """
        Check if actual input matches the pattern.

        Args:
            pattern: Input pattern to match against. None matches any input (catch-all).
            actual: Actual input parameters from tool call.

        Returns:
            True if all pattern conditions are satisfied.

        Examples:
            >>> matcher = InputMatcher()
            >>> # Catch-all pattern
            >>> matcher.matches(None, {"any": "input"})
            True
            >>> # Exact match
            >>> matcher.matches({"key": "value"}, {"key": "value", "extra": "ok"})
            True
            >>> # Operator match
            >>> matcher.matches({"count": {"$gt": 5}}, {"count": 10})
            True
        """
        # None pattern = catch-all, matches anything
        if pattern is None:
            return True

        # Empty pattern matches any input
        if not pattern:
            return True

        # Check each field in pattern
        for field, expected in pattern.items():
            if not self._match_field(field, expected, actual):
                return False

        return True

    def _match_field(self, field: str, expected: Any, actual: dict[str, Any]) -> bool:
        """
        Match a single field against expected value or operator.

        Args:
            field: Field name to match
            expected: Expected value or operator dict
            actual: Actual input dict

        Returns:
            True if field matches
        """
        # Handle $exists specially - check key presence
        if isinstance(expected, dict) and "$exists" in expected:
            exists_value = expected["$exists"]
            key_exists = field in actual and actual[field] is not None
            return key_exists == exists_value

        # For non-$exists operators, field must exist
        if field not in actual:
            return False

        actual_value = actual[field]

        # Check if expected is an operator dict
        if isinstance(expected, dict):
            return self._match_operators(actual_value, expected)

        # Direct value comparison (implicit $eq)
        return actual_value == expected

    def _match_operators(
        self, actual_value: Any, operator_dict: dict[str, Any]
    ) -> bool:
        """
        Match actual value against operator dictionary.

        Supports multiple operators combined with AND logic.

        Args:
            actual_value: Value from actual input
            operator_dict: Dict with operator keys and values

        Returns:
            True if all operators match

        Examples:
            >>> matcher = InputMatcher()
            >>> # Single operator
            >>> matcher._match_operators(150, {"$gt": 100})
            True
            >>> # Multiple operators (AND)
            >>> matcher._match_operators(150, {"$gt": 100, "$lt": 200})
            True
        """
        for op, op_value in operator_dict.items():
            if op.startswith("$"):
                if op not in self.OPERATORS:
                    logger.warning(f"Unknown operator '{op}', treating as no match")
                    return False

                try:
                    op_func = self.OPERATORS[op]
                    if not op_func(actual_value, op_value):
                        return False
                except (TypeError, ValueError, re.error) as e:
                    logger.warning(
                        f"Operator '{op}' failed for value {actual_value}: {e}"
                    )
                    return False
            else:
                # Non-operator key in expected dict - do nested comparison
                if not isinstance(actual_value, dict):
                    return False
                if op not in actual_value or actual_value[op] != op_value:
                    return False

        return True


def _compare_numeric(actual: Any, expected: Any, comparator: Any) -> bool:
    """
    Safely compare numeric values.

    Args:
        actual: Actual value (may be non-numeric)
        expected: Expected value to compare against
        comparator: Comparison function

    Returns:
        True if comparison succeeds, False if types incompatible
    """
    try:
        # Handle string numbers
        if isinstance(actual, str):
            actual = float(actual)
        if isinstance(expected, str):
            expected = float(expected)

        # Ensure both are numeric
        if not isinstance(actual, int | float) or not isinstance(expected, int | float):
            return False

        return comparator(actual, expected)
    except (ValueError, TypeError):
        return False


# Singleton instance for convenience
_matcher = InputMatcher()


def matches(pattern: dict[str, Any] | None, actual: dict[str, Any]) -> bool:
    """
    Convenience function for pattern matching.

    Args:
        pattern: Input pattern to match against
        actual: Actual input parameters

    Returns:
        True if pattern matches actual
    """
    return _matcher.matches(pattern, actual)


__all__ = [
    "InputMatcher",
    "matches",
]
