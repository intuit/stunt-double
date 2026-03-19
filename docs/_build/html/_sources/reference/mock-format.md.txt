# Mock Data Format Reference

Complete reference for StuntDouble's data-driven mock format, including input matching operators and dynamic placeholders resolved by `register_data_driven()` and `DataDrivenMockFactory`.

---

## Basic Structure

### Single Case

```json
{
  "tool_name": [
    {"output": {"key": "value"}}
  ]
}
```

### Multiple Cases with Input Matching

```json
{
  "tool_name": [
    {"input": {"field": "match_value"}, "output": {"result": "matched"}},
    {"input": {"field": {"$gt": 100}}, "output": {"result": "large"}},
    {"output": {"result": "default"}}
  ]
}
```

### Case Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `input` | `object` | No | Pattern to match. `null` or omitted = catch-all |
| `output` | `any` | **Yes** | Value to return (supports placeholders) |

---

## Input Matching Operators

Use MongoDB-style operators for flexible pattern matching.

### Comparison Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `$eq` | Exact equality (default) | `{"status": {"$eq": "active"}}` |
| `$ne` | Not equal | `{"status": {"$ne": "deleted"}}` |
| `$gt` | Greater than | `{"amount": {"$gt": 1000}}` |
| `$gte` | Greater than or equal | `{"count": {"$gte": 10}}` |
| `$lt` | Less than | `{"age": {"$lt": 18}}` |
| `$lte` | Less than or equal | `{"priority": {"$lte": 5}}` |

**Examples:**

```json
{
  "get_bills": [
    {
      "input": {"amount": {"$gt": 5000}},
      "output": {"priority": "high"}
    },
    {
      "input": {"amount": {"$lte": 100}},
      "output": {"priority": "low"}
    }
  ]
}
```

### Set Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `$in` | Value in list | `{"status": {"$in": ["active", "pending"]}}` |
| `$nin` | Value not in list | `{"type": {"$nin": ["deleted", "archived"]}}` |

**Examples:**

```json
{
  "get_customer": [
    {
      "input": {"tier": {"$in": ["gold", "platinum"]}},
      "output": {"discount": 0.2}
    },
    {
      "input": {"tier": {"$nin": ["free", "trial"]}},
      "output": {"discount": 0.1}
    }
  ]
}
```

### String Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `$contains` | String contains substring | `{"name": {"$contains": "Corp"}}` |
| `$regex` | Regular expression match | `{"id": {"$regex": "^CUST-\\d+"}}` |

**Examples:**

```json
{
  "search": [
    {
      "input": {"query": {"$contains": "invoice"}},
      "output": {"category": "billing"}
    },
    {
      "input": {"id": {"$regex": "^VIP-[A-Z]{3}"}},
      "output": {"tier": "vip"}
    }
  ]
}
```

### Existence Operator

| Operator | Description | Example |
|----------|-------------|---------|
| `$exists` | Key exists (or not) | `{"optional_field": {"$exists": true}}` |

**Examples:**

```json
{
  "create_invoice": [
    {
      "input": {"discount_code": {"$exists": true}},
      "output": {"discount_applied": true}
    },
    {
      "input": {"discount_code": {"$exists": false}},
      "output": {"discount_applied": false}
    }
  ]
}
```

### Combined Operators

Multiple operators on the same field use AND logic:

```json
{
  "get_products": [
    {
      "input": {
        "price": {"$gte": 100, "$lt": 500}
      },
      "output": {"category": "mid-range"}
    }
  ]
}
```

Multiple fields also use AND logic:

```json
{
  "get_orders": [
    {
      "input": {
        "status": "pending",
        "amount": {"$gt": 1000}
      },
      "output": {"priority": "urgent"}
    }
  ]
}
```

---

## Dynamic Placeholders

Use `{{placeholder}}` syntax for dynamic values in outputs.

### Timestamp Placeholders

| Placeholder | Description | Example Output |
|-------------|-------------|----------------|
| `{{now}}` | Current ISO timestamp | `2025-01-04T10:30:00` |
| `{{today}}` | Current date | `2025-01-04` |
| `{{now + Nd}}` | N days from now | `2025-01-11` (7 days later) |
| `{{now - Nd}}` | N days ago | `2024-12-05` (30 days ago) |
| `{{now + Nh}}` | N hours from now | Time + hours |
| `{{now + Nw}}` | N weeks from now | Date + weeks |
| `{{now + NM}}` | N months from now | Date + ~30*N days |
| `{{now + Ny}}` | N years from now | Date + ~365*N days |

**Boundary Timestamps:**

| Placeholder | Description |
|-------------|-------------|
| `{{start_of_day}}` | Midnight today |
| `{{end_of_day}}` | 23:59:59 today |
| `{{start_of_week}}` | Monday 00:00:00 |
| `{{end_of_week}}` | Sunday 23:59:59 |
| `{{start_of_month}}` | 1st of month 00:00:00 |
| `{{end_of_month}}` | Last day of month 23:59:59 |
| `{{start_of_year}}` | Jan 1 00:00:00 |
| `{{end_of_year}}` | Dec 31 23:59:59 |

**Examples:**

```json
{
  "create_invoice": [{
    "output": {
      "created_at": "{{now}}",
      "due_date": "{{now + 30d}}",
      "fiscal_year_start": "{{start_of_year}}"
    }
  }]
}
```

### Input Reference Placeholders

| Placeholder | Description |
|-------------|-------------|
| `{{input.field}}` | Value from tool input |
| `{{input.field \| default(value)}}` | With default if missing |

### Config Reference Placeholders

| Placeholder | Description |
|-------------|-------------|
| `{{config.field}}` | Value from merged `RunnableConfig.configurable` data |
| `{{config.field \| default(value)}}` | With default if missing |

`{{config.*}}` placeholders resolve from the merged configurable data passed to the data-driven mock. If both `configurable.field` and `configurable.config_data.field` exist, `config_data` takes precedence.

**Examples:**

```json
{
  "get_customer": [{
    "output": {
      "id": "{{input.customer_id}}",
      "query_time": "{{now}}",
      "name": "Customer {{input.customer_id}}"
    }
  }]
}
```

With defaults:

```json
{
  "search": [{
    "output": {
      "query": "{{input.query | default('*')}}",
      "limit": "{{input.limit | default(10)}}"
    }
  }]
}
```

### Generator Placeholders

| Placeholder | Description | Example Output |
|-------------|-------------|----------------|
| `{{uuid}}` | Random UUID | `a1b2c3d4-e5f6-7890-abcd-ef1234567890` |
| `{{random_int(min, max)}}` | Random integer | `42` (for range 1-100) |
| `{{random_float(min, max)}}` | Random float (2 decimals) | `47.53` |
| `{{choice('a', 'b', 'c')}}` | Random choice from list | `b` |
| `{{sequence('prefix')}}` | Incrementing ID | `prefix-001`, `prefix-002` |
| `{{random_string(length)}}` | Random alphanumeric | `xK9mP2qR` |

**Examples:**

```json
{
  "create_invoice": [{
    "output": {
      "id": "{{uuid}}",
      "invoice_number": "{{sequence('INV')}}",
      "verification_code": "{{random_string(8)}}",
      "priority_score": "{{random_int(1, 10)}}"
    }
  }],
  "get_status": [{
    "output": {
      "status": "{{choice('pending', 'processing', 'complete')}}",
      "progress": "{{random_float(0, 100)}}"
    }
  }]
}
```

---

## Complete Examples

### Customer Service Mock

```json
{
  "get_customer": [
    {
      "input": {"customer_id": {"$regex": "^VIP"}},
      "output": {
        "id": "{{input.customer_id}}",
        "tier": "platinum",
        "discount": 0.25,
        "account_manager": "dedicated"
      }
    },
    {
      "input": {"customer_id": {"$regex": "^CORP"}},
      "output": {
        "id": "{{input.customer_id}}",
        "tier": "enterprise",
        "discount": 0.15,
        "account_manager": "team"
      }
    },
    {
      "output": {
        "id": "{{input.customer_id | default('UNKNOWN')}}",
        "tier": "standard",
        "discount": 0,
        "account_manager": null
      }
    }
  ]
}
```

### Invoice Creation Mock

```json
{
  "create_invoice": [
    {
      "input": {"amount": {"$gt": 10000}},
      "output": {
        "id": "{{uuid}}",
        "invoice_number": "{{sequence('INV')}}",
        "amount": "{{input.amount}}",
        "customer_id": "{{input.customer_id}}",
        "created_at": "{{now}}",
        "due_date": "{{now + 45d}}",
        "status": "pending_approval",
        "requires_approval": true
      }
    },
    {
      "output": {
        "id": "{{uuid}}",
        "invoice_number": "{{sequence('INV')}}",
        "amount": "{{input.amount}}",
        "customer_id": "{{input.customer_id}}",
        "created_at": "{{now}}",
        "due_date": "{{now + 30d}}",
        "status": "created",
        "requires_approval": false
      }
    }
  ]
}
```

### Bills Query Mock

```json
{
  "list_bills": [
    {
      "input": {"status": "overdue", "amount": {"$gt": 5000}},
      "output": {
        "bills": [
          {"id": "B-001", "amount": 7500, "status": "overdue", "days_overdue": 45},
          {"id": "B-002", "amount": 12000, "status": "overdue", "days_overdue": 30}
        ],
        "total_overdue": 19500,
        "priority": "CRITICAL"
      }
    },
    {
      "input": {"status": "overdue"},
      "output": {
        "bills": [
          {"id": "B-003", "amount": 250, "status": "overdue", "days_overdue": 5}
        ],
        "total_overdue": 250,
        "priority": "normal"
      }
    },
    {
      "input": {"status": {"$in": ["paid", "processing"]}},
      "output": {
        "bills": [],
        "message": "No action required"
      }
    },
    {
      "output": {
        "bills": [],
        "message": "No matching bills"
      }
    }
  ]
}
```

---

## Matching Precedence

Cases are evaluated in order. First match wins:

```json
{
  "tool": [
    {"input": {"specific": "value"}, "output": "first"},   // Checked first
    {"input": {"field": {"$gt": 0}}, "output": "second"},  // Checked second
    {"output": "default"}                                   // Catch-all (always last)
  ]
}
```

**Best practice:** Order cases from most specific to least specific, with catch-all last.

### No-Match Behavior

When no case matches and no catch-all is present, the behavior depends on how the mock was registered:

| Configuration | No-match result |
|--------------|-----------------|
| `echo_input=True` | Returns the input kwargs as-is |
| `fallback=value` | Returns the fallback value |
| Catch-all case (no `input` key) | Returns catch-all output |
| None of the above | Raises `InputNotMatchedError` |

`InputNotMatchedError` ensures broken mock specs are caught early rather than producing plausible-looking but incorrect data. To opt into lenient behavior, add a catch-all case or set `fallback=` when registering.

---

## Validation

### Required Fields

- `output` is always required
- `input` is optional (omit for catch-all)

### Type Coercion

Numeric comparisons support string-to-number coercion:

```text
{
  "input": {"amount": {"$gt": 1000}},  // Works with "1500" or 1500
  "output": {...}
}
```

### Null Handling

- `null` input pattern = match any input
- `$exists: false` = field is missing or null
- `$exists: true` = field is present and not null

