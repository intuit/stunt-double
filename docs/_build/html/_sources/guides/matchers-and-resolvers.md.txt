# Matchers and Resolvers Guide

This guide explains how to use StuntDouble's powerful input matchers and dynamic value resolvers to create flexible, realistic mock responses.

---

## Overview

StuntDouble provides two core components for advanced mocking:

1. **Input Matchers** — Match tool inputs using MongoDB-style operators (`$gt`, `$in`, `$regex`, etc.)
2. **Value Resolvers** — Generate dynamic outputs with placeholders (`{{now}}`, `{{uuid}}`, `{{input.field}}`)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Mock Resolution Pipeline                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Tool Input ──▶ InputMatcher ──▶ Select Mock Case ──▶ ValueResolver ──▶ Output
│                                                                             │
│   {"amount": 1500}     $gt: 1000?      Case 2         {{now}}      "2025-01-05"
│                          ▼              output         {{uuid}}     "a1b2c3..."
│                         YES                                                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Input Matchers

### Basic Usage

The `InputMatcher` class matches tool input parameters against patterns using operators.

```python
from stuntdouble.matching import InputMatcher, matches

matcher = InputMatcher()

# Exact match
matcher.matches({"status": "active"}, {"status": "active"})  # True
matcher.matches({"status": "active"}, {"status": "inactive"})  # False

# Operator match
matcher.matches({"amount": {"$gt": 1000}}, {"amount": 1500})  # True
matcher.matches({"amount": {"$gt": 1000}}, {"amount": 500})  # False

# Convenience function
matches({"status": "active"}, {"status": "active"})  # True
```

### Supported Operators

| Operator | Description | Example Pattern | Matches |
|----------|-------------|-----------------|---------|
| `$eq` | Exact equality (default) | `{"status": {"$eq": "active"}}` | `{"status": "active"}` |
| `$ne` | Not equal | `{"status": {"$ne": "deleted"}}` | `{"status": "active"}` |
| `$gt` | Greater than | `{"amount": {"$gt": 1000}}` | `{"amount": 1500}` |
| `$gte` | Greater than or equal | `{"count": {"$gte": 10}}` | `{"count": 10}` |
| `$lt` | Less than | `{"age": {"$lt": 30}}` | `{"age": 25}` |
| `$lte` | Less than or equal | `{"priority": {"$lte": 5}}` | `{"priority": 3}` |
| `$in` | Value in list | `{"status": {"$in": ["a", "b"]}}` | `{"status": "a"}` |
| `$nin` | Not in list | `{"type": {"$nin": ["deleted"]}}` | `{"type": "active"}` |
| `$contains` | String contains | `{"name": {"$contains": "Corp"}}` | `{"name": "Acme Corp"}` |
| `$regex` | Regex match | `{"id": {"$regex": "^CUST-\\d+"}}` | `{"id": "CUST-123"}` |
| `$exists` | Key exists | `{"email": {"$exists": true}}` | `{"email": "a@b.com"}` |

### Multiple Conditions

Combine multiple operators with AND logic:

```python
# All conditions must match
pattern = {
    "amount": {"$gt": 100, "$lt": 1000},  # 100 < amount < 1000
    "status": "active"
}

matches(pattern, {"amount": 500, "status": "active"})  # True
matches(pattern, {"amount": 500, "status": "pending"})  # False (status mismatch)
matches(pattern, {"amount": 50, "status": "active"})  # False (amount too low)
```

### Catch-All Patterns

Use `None` or empty dict for catch-all matching:

```python
# None matches anything
matches(None, {"any": "input", "goes": "here"})  # True

# Empty dict also matches anything
matches({}, {"any": "input"})  # True
```

### Real-World Examples

#### Example 1: Customer Tier Logic

```python
# Via scenario_metadata (LangGraph)
scenario_metadata = {
    "mocks": {
        "get_customer": [
            {"input": {"customer_id": {"$regex": "^VIP-"}}, "output": {"tier": "platinum", "discount": 0.25}},
            {"input": {"customer_id": {"$contains": "CORP"}}, "output": {"tier": "enterprise", "discount": 0.15}},
            {"input": {"total_purchases": {"$gte": 10000}}, "output": {"tier": "gold", "discount": 0.10}},
            {"output": {"tier": "standard", "discount": 0}}
        ]
    }
}
```

#### Example 2: Bill Filtering

```python
# Via scenario_metadata (LangGraph)
scenario_metadata = {
    "mocks": {
        "list_bills": [
            {"input": {"status": "overdue", "amount": {"$gt": 5000}}, "output": {"priority": "URGENT", "bills": [...]}},
            {"input": {"status": "overdue"}, "output": {"priority": "HIGH", "bills": [...]}},
            {"input": {"status": {"$in": ["paid", "pending"]}}, "output": {"priority": "LOW", "bills": [...]}},
            {"output": {"priority": "NORMAL", "bills": []}}
        ]
    }
}
```

---

## Value Resolvers

### Basic Usage

The `ValueResolver` class resolves dynamic placeholders in mock outputs.

```python
from stuntdouble.resolving import ValueResolver, ResolverContext, resolve_output

resolver = ValueResolver()
ctx = ResolverContext(input_data={"customer_id": "CUST-123"})

# Simple placeholder
resolver.resolve_dynamic_values("{{uuid}}", ctx)  # "a1b2c3d4-e5f6-7890-..."

# Input reference
resolver.resolve_dynamic_values("{{input.customer_id}}", ctx)  # "CUST-123"

# Nested structure
resolver.resolve_dynamic_values({
    "id": "{{uuid}}",
    "created_at": "{{now}}",
    "customer": "{{input.customer_id}}"
}, ctx)
# {'id': 'a1b2...', 'created_at': '2025-01-05T...', 'customer': 'CUST-123'}

# Convenience function
resolve_output({"id": "{{uuid}}"}, input_data={"customer_id": "123"})
```

### Timestamp Placeholders

| Placeholder | Description | Example Output |
|-------------|-------------|----------------|
| `{{now}}` | Current datetime (ISO format) | `2025-01-05T10:30:00` |
| `{{today}}` | Current date | `2025-01-05` |
| `{{now + 7d}}` | 7 days from now | `2025-01-12T10:30:00` |
| `{{now - 30d}}` | 30 days ago | `2024-12-06T10:30:00` |
| `{{today + 1w}}` | 1 week from today | `2025-01-12` |
| `{{now + 2h}}` | 2 hours from now | `2025-01-05T12:30:00` |
| `{{start_of_day}}` | Start of today | `2025-01-05T00:00:00` |
| `{{end_of_day}}` | End of today | `2025-01-05T23:59:59` |
| `{{start_of_week}}` | Monday of current week | `2025-01-01T00:00:00` |
| `{{end_of_week}}` | Sunday of current week | `2025-01-05T23:59:59` |
| `{{start_of_month}}` | First day of month | `2025-01-01T00:00:00` |
| `{{end_of_month}}` | Last day of month | `2025-01-31T23:59:59` |
| `{{start_of_year}}` | First day of year | `2025-01-01T00:00:00` |
| `{{end_of_year}}` | Last day of year | `2025-12-31T23:59:59` |

**Time units:**
- `h` — hours
- `d` — days
- `w` — weeks
- `m` — minutes
- `M` — months (approximate, 30 days)
- `y` — years (approximate, 365 days)

### Input Reference Placeholders

| Placeholder | Description | Example |
|-------------|-------------|---------|
| `{{input.field_name}}` | Value from tool input | `{{input.customer_id}}` |
| `{{input.field \| default(value)}}` | With default if missing | `{{input.email \| default('n/a')}}` |

```python
ctx = ResolverContext(input_data={"customer_id": "CUST-123", "amount": 500})

resolver.resolve_dynamic_values("Customer: {{input.customer_id}}", ctx)  # "Customer: CUST-123"
resolver.resolve_dynamic_values("{{input.email | default('none')}}", ctx)  # "none" (field missing)
```

### Generator Placeholders

| Placeholder | Description | Example Output |
|-------------|-------------|----------------|
| `{{uuid}}` | Random UUID | `a1b2c3d4-e5f6-7890-abcd-ef1234567890` |
| `{{random_int(1, 100)}}` | Random integer in range | `42` |
| `{{random_float(0, 10)}}` | Random float (2 decimals) | `7.35` |
| `{{choice('a', 'b', 'c')}}` | Random choice from list | `b` |
| `{{sequence('INV')}}` | Sequential ID with prefix | `INV-001`, `INV-002`, ... |
| `{{random_string(8)}}` | Random alphanumeric string | `xK9mQ2wP` |

### Real-World Examples

#### Example 1: Invoice Creation

```python
mock("create_invoice", {
    "id": "{{sequence('INV')}}",
    "created_at": "{{now}}",
    "due_date": "{{now + 30d}}",
    "customer_id": "{{input.customer_id}}",
    "amount": "{{input.amount}}",
    "status": "pending",
    "reference": "{{uuid}}"
})
```

#### Example 2: User Profile

```python
mock("get_user", {
    "id": "{{input.user_id}}",
    "email": "{{input.user_id}}@example.com",
    "created_at": "{{now - 90d}}",
    "last_login": "{{now - 2h}}",
    "session_token": "{{random_string(32)}}",
    "loyalty_points": "{{random_int(100, 5000)}}"
})
```

#### Example 3: Billing Period

```python
# Via scenario_metadata (LangGraph)
scenario_metadata = {
    "mocks": {
        "get_billing_period": [{
            "output": {
                "period_start": "{{start_of_month}}",
                "period_end": "{{end_of_month}}",
                "invoice_due": "{{end_of_month + 15d}}",
                "customer": "{{input.customer_id}}",
                "status": "{{choice('pending', 'processing', 'complete')}}"
            }
        }]
    }
}
```

---

## Combining Matchers and Resolvers

The real power comes from combining input matching with dynamic outputs:

```python
# Via scenario_metadata (LangGraph)
scenario_metadata = {
    "mocks": {
        "process_payment": [
            {
                "input": {"amount": {"$gt": 10000}},
                "output": {
                    "transaction_id": "{{uuid}}",
                    "status": "pending_review",
                    "review_deadline": "{{now + 24h}}",
                    "amount": "{{input.amount}}",
                    "requires_approval": True
                }
            },
            {
                "input": {"amount": {"$gt": 0}},
                "output": {
                    "transaction_id": "{{uuid}}",
                    "status": "completed",
                    "processed_at": "{{now}}",
                    "amount": "{{input.amount}}",
                    "requires_approval": False
                }
            },
            {
                "output": {
                    "transaction_id": None,
                    "status": "invalid",
                    "error": "Invalid payment amount"
                }
            }
        ]
    }
}
```

---

## Using with LangGraph

Matchers and resolvers work seamlessly with the LangGraph approach via `scenario_metadata`:

```python
from stuntdouble import inject_scenario_metadata

# Pass mock data with operators and placeholders in scenario_metadata
config = inject_scenario_metadata({}, {
    "mocks": {
        "get_customer": [
            # Match VIP customers
            {
                "input": {"customer_id": {"$regex": "^VIP-"}},
                "output": {
                    "id": "{{input.customer_id}}",
                    "tier": "platinum",
                    "since": "{{now - 365d}}"
                }
            },
            # Catch-all
            {
                "output": {
                    "id": "{{input.customer_id}}",
                    "tier": "standard",
                    "since": "{{now}}"
                }
            }
        ]
    }
})

result = await graph.ainvoke(state, config=config)
```

---

## Best Practices

### 1. Order Patterns from Specific to General

```python
# Most specific first, catch-all last
scenario_metadata = {
    "mocks": {
        "process": [
            {"input": {"type": "premium", "amount": {"$gt": 1000}}, "output": {...}},
            {"input": {"type": "premium"}, "output": {...}},
            {"input": {"amount": {"$gt": 1000}}, "output": {...}},
            {"output": {...}}  # Catch-all
        ]
    }
}
```

### 2. Use Defaults for Missing Fields

```python
# Good: Handle missing input gracefully
{"email": "{{input.email | default('unknown@example.com')}}"}

# Risky: May produce None if field missing
{"email": "{{input.email}}"}
```

### 3. Use Sequences for Related IDs

```python
# IDs will be INV-001, INV-002, etc. across multiple calls
scenario_metadata = {
    "mocks": {
        "create_invoice": [{
            "output": {
                "invoice_id": "{{sequence('INV')}}",
                "line_items": [
                    {"id": "{{sequence('LINE')}}"},
                    {"id": "{{sequence('LINE')}}"}
                ]
            }
        }]
    }
}
```

### 4. Combine Operators for Range Matching

```python
# Match amounts between 100 and 1000
({"amount": {"$gte": 100, "$lte": 1000}}, {...})
```

### 5. Use $exists for Optional Fields

```python
# Only match if email is provided
({"email": {"$exists": true}}, {"verified": True})

# Match when email is NOT provided
({"email": {"$exists": false}}, {"verified": False})
```

---

## Debugging

### Check if a Pattern Matches

```python
from stuntdouble.matching import matches

pattern = {"amount": {"$gt": 100}}
actual = {"amount": 50}

if not matches(pattern, actual):
    print(f"Pattern {pattern} does not match {actual}")
```

### Check for Placeholders

```python
from stuntdouble.resolving import has_placeholders

output = {"id": "{{uuid}}", "name": "static"}
print(has_placeholders(output))  # True

output = {"id": "123", "name": "static"}
print(has_placeholders(output))  # False
```

### Enable Debug Logging

```python
import logging
logging.getLogger("stuntdouble.matching").setLevel(logging.DEBUG)
logging.getLogger("stuntdouble.resolving").setLevel(logging.DEBUG)
```

---

## API Reference

### Matchers

| Function/Class | Description |
|---------------|-------------|
| `InputMatcher` | Class for pattern matching with operators |
| `InputMatcher.matches(pattern, actual)` | Check if actual matches pattern |
| `matches(pattern, actual)` | Convenience function using singleton matcher |

### Resolvers

| Function/Class | Description |
|---------------|-------------|
| `ValueResolver` | Class for placeholder resolution |
| `ValueResolver.resolve_dynamic_values(value, context)` | Resolve placeholders in value |
| `ResolverContext` | Context with input data and state |
| `resolve_output(output, input_data)` | Convenience function for resolution |
| `has_placeholders(value)` | Check if value contains placeholders |

---

## Next Steps

| Topic | Guide |
|-------|-------|
| LangGraph integration | [LangGraph Approach](langgraph-integration.md) |
| Custom mocked tools | [Custom Mocked Tools](langgraph-integration.md#custom-mocked-tools) |
| Mock format reference | [Mock Format](../reference/mock-format.md) |
| Evaluation workflows | [Quickstart](quickstart.md) |

