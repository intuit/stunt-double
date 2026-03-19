"""
Value resolvers for dynamic mock outputs.

Provides placeholder resolution for mock outputs, enabling dynamic values
based on timestamps, input references, and generator functions.

Supported placeholders:
- Timestamps: {{now}}, {{now + 7d}}, {{start_of_month}}, etc.
- Input refs: {{input.field_name}}, {{input.field | default(value)}}
- Generators: {{uuid}}, {{random_int(min, max)}}, {{sequence('prefix')}}
"""

from __future__ import annotations

import calendar
import copy
import logging
import random
import re
import string
import uuid as uuid_module
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# Regex patterns for placeholder detection
PLACEHOLDER_PATTERN = re.compile(r"\{\{(.+?)\}\}")
TIMESTAMP_RELATIVE_PATTERN = re.compile(r"^(now|today)\s*([+-])\s*(\d+)\s*([hdwmMy])$")
TIMESTAMP_BOUNDARY_PATTERN = re.compile(
    r"^(start_of_day|end_of_day|start_of_week|end_of_week|start_of_month|end_of_month|start_of_year|end_of_year)$"
)
INPUT_REF_PATTERN = re.compile(r"^input\.(\w+)(?:\s*\|\s*default\((.+)\))?$")
CONFIG_REF_PATTERN = re.compile(r"^config\.(\w+)(?:\s*\|\s*default\((.+)\))?$")
FUNCTION_PATTERN = re.compile(r"^(\w+)\(([^)]*)\)$")


@dataclass
class ResolverContext:
    """
    Context for placeholder resolution.

    Attributes:
        input_data: Input parameters from tool call (for {{input.*}} refs)
        config_data: Values from RunnableConfig (for {{config.*}} refs)
        base_time: Base time for timestamp calculations (default: now)
        sequence_counters: Mutable dict tracking sequence counters
    """

    input_data: dict[str, Any] = field(default_factory=dict)
    config_data: dict[str, Any] = field(default_factory=dict)
    base_time: datetime = field(default_factory=datetime.now)
    sequence_counters: dict[str, int] = field(default_factory=dict)


class ValueResolver:
    """
    Resolves dynamic placeholders in mock outputs.

    Recursively processes values, resolving placeholders in strings,
    lists, and nested dictionaries.

    Examples:
        >>> resolver = ValueResolver()
        >>> ctx = ResolverContext(input_data={"customer_id": "CUST-123"})
        >>> resolver.resolve_dynamic_values("{{input.customer_id}}", ctx)
        'CUST-123'
        >>> resolver.resolve_dynamic_values({"id": "{{uuid}}", "created": "{{now}}"}, ctx)
        {'id': 'a1b2c3d4-...', 'created': '2025-12-18T10:30:00'}
    """

    def resolve_dynamic_values(self, value: Any, context: ResolverContext | None = None) -> Any:
        """
        Recursively resolve all placeholders in a value.

        Args:
            value: Value to resolve (string, dict, list, or primitive)
            context: Resolution context with input data and state

        Returns:
            Resolved value with all placeholders replaced
        """
        if context is None:
            context = ResolverContext()

        if isinstance(value, str):
            return self._resolve_string(value, context)
        elif isinstance(value, dict):
            return {k: self.resolve_dynamic_values(v, context) for k, v in value.items()}
        elif isinstance(value, list):
            return [self.resolve_dynamic_values(item, context) for item in value]
        else:
            # Primitives (int, float, bool, None) pass through
            return value

    def _resolve_string(self, value: str, context: ResolverContext) -> Any:
        """
        Resolve placeholders in a string value.

        If the entire string is a single placeholder, return the resolved
        value directly (preserving type). Otherwise, do string interpolation.

        Args:
            value: String value to resolve
            context: Resolution context

        Returns:
            Resolved value (may be non-string if entire value was placeholder)
        """
        # Check if entire string is a single placeholder
        match = PLACEHOLDER_PATTERN.fullmatch(value)
        if match:
            expr = match.group(1).strip()
            return self._resolve_expression(expr, context)

        # Otherwise, do string interpolation
        def replace_placeholder(m: re.Match[str]) -> str:
            expr = m.group(1).strip()
            resolved = self._resolve_expression(expr, context)
            return str(resolved)

        return PLACEHOLDER_PATTERN.sub(replace_placeholder, value)

    def _resolve_expression(self, expr: str, context: ResolverContext) -> Any:
        """
        Resolve a single placeholder expression.

        Args:
            expr: Expression without {{ }} delimiters
            context: Resolution context

        Returns:
            Resolved value
        """
        # Try each resolver in order
        resolvers = [
            self._try_timestamp,
            self._try_input_ref,
            self._try_config_ref,
            self._try_generator,
        ]

        for resolver in resolvers:
            result = resolver(expr, context)
            if result is not None:
                return result

        # Unknown expression - return as-is with warning
        logger.warning(f"Unknown placeholder expression: {{{{{expr}}}}}")
        return f"{{{{{expr}}}}}"

    def _try_timestamp(self, expr: str, context: ResolverContext) -> Any | None:
        """
        Try to resolve timestamp expressions.

        Supports:
        - now, today
        - now +/- Nd, Nw, Nh, Nm, NM, Ny
        - start_of_day, end_of_day, start_of_month, etc.

        Args:
            expr: Expression to resolve
            context: Resolution context

        Returns:
            ISO timestamp string or None if not a timestamp expr
        """
        base = context.base_time

        # Simple "now" or "today"
        if expr == "now":
            return base.isoformat()
        if expr == "today":
            return base.date().isoformat()

        # Relative timestamps: now + 7d, now - 30d, today + 1w
        rel_match = TIMESTAMP_RELATIVE_PATTERN.match(expr)
        if rel_match:
            base_type = rel_match.group(1)  # now or today
            operator = rel_match.group(2)  # + or -
            amount = int(rel_match.group(3))
            unit = rel_match.group(4)

            if operator == "-":
                amount = -amount

            delta = self._get_timedelta(amount, unit)
            result = base + delta

            if base_type == "today":
                return result.date().isoformat()
            return result.isoformat()

        # Boundary timestamps
        boundary_match = TIMESTAMP_BOUNDARY_PATTERN.match(expr)
        if boundary_match:
            return self._resolve_boundary(expr, base).isoformat()

        return None

    def _get_timedelta(self, amount: int, unit: str) -> timedelta:
        """
        Convert amount and unit to timedelta.

        Args:
            amount: Numeric amount (can be negative)
            unit: Time unit (h=hours, d=days, w=weeks, m=minutes, M=months, y=years)

        Returns:
            timedelta object
        """
        match unit:
            case "h":
                return timedelta(hours=amount)
            case "d":
                return timedelta(days=amount)
            case "w":
                return timedelta(weeks=amount)
            case "m":
                return timedelta(minutes=amount)
            case "M":
                # Approximate months as 30 days
                return timedelta(days=amount * 30)
            case "y":
                # Approximate years as 365 days
                return timedelta(days=amount * 365)
            case _:
                logger.warning(f"Unknown time unit '{unit}', defaulting to days")
                return timedelta(days=amount)

    def _resolve_boundary(self, boundary: str, base: datetime) -> datetime:
        """
        Resolve boundary timestamps (start_of_day, end_of_month, etc.).

        Args:
            boundary: Boundary type
            base: Base datetime

        Returns:
            Datetime at boundary
        """
        match boundary:
            case "start_of_day":
                return base.replace(hour=0, minute=0, second=0, microsecond=0)
            case "end_of_day":
                return base.replace(hour=23, minute=59, second=59, microsecond=999999)
            case "start_of_week":
                # Monday = 0
                days_since_monday = base.weekday()
                start = base - timedelta(days=days_since_monday)
                return start.replace(hour=0, minute=0, second=0, microsecond=0)
            case "end_of_week":
                # Sunday = 6
                days_until_sunday = 6 - base.weekday()
                end = base + timedelta(days=days_until_sunday)
                return end.replace(hour=23, minute=59, second=59, microsecond=999999)
            case "start_of_month":
                return base.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            case "end_of_month":
                _, last_day = calendar.monthrange(base.year, base.month)
                return base.replace(day=last_day, hour=23, minute=59, second=59, microsecond=999999)
            case "start_of_year":
                return base.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            case "end_of_year":
                return base.replace(month=12, day=31, hour=23, minute=59, second=59, microsecond=999999)
            case _:
                return base

    def _try_input_ref(self, expr: str, context: ResolverContext) -> Any | None:
        """
        Try to resolve input references.

        Supports:
        - input.field_name
        - input.field_name | default(value)

        Args:
            expr: Expression to resolve
            context: Resolution context

        Returns:
            Input value or None if not an input ref
        """
        match = INPUT_REF_PATTERN.match(expr)
        if not match:
            return None

        field_name = match.group(1)
        default_value = match.group(2)

        if field_name in context.input_data:
            return context.input_data[field_name]

        if default_value is not None:
            return self._parse_literal(default_value)

        logger.debug(f"Input field '{field_name}' not found and no default provided")
        return f"<{field_name}>"

    def _try_config_ref(self, expr: str, context: ResolverContext) -> Any | None:
        """
        Try to resolve config references.

        Supports:
        - config.field_name
        - config.field_name | default(value)

        Args:
            expr: Expression to resolve
            context: Resolution context

        Returns:
            Config value or None if not a config ref
        """
        match = CONFIG_REF_PATTERN.match(expr)
        if not match:
            return None

        field_name = match.group(1)
        default_value = match.group(2)

        if field_name in context.config_data:
            return context.config_data[field_name]

        if default_value is not None:
            return self._parse_literal(default_value)

        logger.debug(f"Config field '{field_name}' not found and no default provided")
        return f"<{field_name}>"

    def _try_generator(self, expr: str, context: ResolverContext) -> Any | None:
        """
        Try to resolve generator functions.

        Supports:
        - uuid
        - random_int(min, max)
        - random_float(min, max)
        - choice('a', 'b', 'c')
        - sequence('prefix')

        Args:
            expr: Expression to resolve
            context: Resolution context

        Returns:
            Generated value or None if not a generator
        """
        # Simple generators (no args)
        if expr == "uuid":
            return str(uuid_module.uuid4())

        # Function-style generators
        func_match = FUNCTION_PATTERN.match(expr)
        if not func_match:
            return None

        func_name = func_match.group(1)
        args_str = func_match.group(2)
        args = self._parse_args(args_str)

        match func_name:
            case "random_int":
                if len(args) >= 2:
                    return random.randint(int(args[0]), int(args[1]))
                logger.warning("random_int requires 2 arguments")
                return random.randint(0, 100)

            case "random_float":
                if len(args) >= 2:
                    return round(random.uniform(float(args[0]), float(args[1])), 2)
                logger.warning("random_float requires 2 arguments")
                return round(random.uniform(0, 100), 2)

            case "choice":
                if args:
                    return random.choice(args)
                logger.warning("choice requires at least 1 argument")
                return None

            case "sequence":
                prefix = args[0] if args else "SEQ"
                key = f"sequence_{prefix}"
                current = context.sequence_counters.get(key, 0) + 1
                context.sequence_counters[key] = current
                return f"{prefix}-{current:03d}"

            case "random_string":
                length = int(args[0]) if args else 8
                chars = string.ascii_letters + string.digits
                return "".join(random.choices(chars, k=length))

            case _:
                return None

    def _parse_args(self, args_str: str) -> list[Any]:
        """
        Parse function arguments from string.

        Args:
            args_str: Comma-separated arguments

        Returns:
            List of parsed argument values
        """
        if not args_str.strip():
            return []

        args = []
        for arg in args_str.split(","):
            arg = arg.strip()
            args.append(self._parse_literal(arg))
        return args

    def _parse_literal(self, value: str) -> Any:
        """
        Parse a literal value from string.

        Args:
            value: String representation of value

        Returns:
            Parsed value (string, int, float, bool, or None)
        """
        value = value.strip()

        # Remove quotes for strings
        if (value.startswith("'") and value.endswith("'")) or (value.startswith('"') and value.endswith('"')):
            return value[1:-1]

        # Boolean
        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False

        # None
        if value.lower() in ("null", "none"):
            return None

        # Integer
        try:
            return int(value)
        except ValueError:
            pass

        # Float
        try:
            return float(value)
        except ValueError:
            pass

        # Return as string
        return value


def resolve_output(
    output: Any,
    input_data: dict[str, Any] | None = None,
    config_data: dict[str, Any] | None = None,
    sequence_counters: dict[str, int] | None = None,
) -> Any:
    """
    Convenience function to resolve placeholders in mock output.

    Args:
        output: Output value to resolve
        input_data: Input parameters for {{input.*}} references
        config_data: RunnableConfig values for {{config.*}} references
        sequence_counters: Optional shared sequence state

    Returns:
        Resolved output with all placeholders replaced
    """
    resolver = ValueResolver()
    context = ResolverContext(
        input_data=input_data or {},
        config_data=config_data or {},
        sequence_counters=sequence_counters if sequence_counters is not None else {},
    )
    # Deep copy to avoid mutating original
    return resolver.resolve_dynamic_values(copy.deepcopy(output), context)


def has_placeholders(value: Any) -> bool:
    """
    Check if a value contains any placeholders.

    Args:
        value: Value to check

    Returns:
        True if value contains {{...}} placeholders
    """
    if isinstance(value, str):
        return bool(PLACEHOLDER_PATTERN.search(value))
    elif isinstance(value, dict):
        return any(has_placeholders(v) for v in value.values())
    elif isinstance(value, list):
        return any(has_placeholders(item) for item in value)
    return False


__all__ = [
    "ValueResolver",
    "ResolverContext",
    "resolve_output",
    "has_placeholders",
]
