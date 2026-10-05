# Scenario files

A scenario is the `scenario_metadata` dict that travels in `RunnableConfig.configurable`. Keep one JSON file per scenario under `AGENT_DIR/scenarios/` and load it in tests, smoke tests and eval rows. Full format reference: https://intuit.github.io/stunt-double/reference/mock-format.html

## Shape

```json
{
  "scenario_id": "overdue-bills",
  "invoice_policy": "reject_large",
  "mocks": {
    "<tool_name>": [
      {"input": {...}, "output": {...}},
      {"output": {...}}
    ]
  }
}
```

- `scenario_id` is recorded on every `CallRecord`; always set it.
- Any other top-level key is free-form and readable by hand-written factories (`invoice_policy` above).
- `mocks.<tool_name>` is a list of cases evaluated **in order**; the first whose `input` matches wins. A case without `input` is a catch-all — put it last.
- A tool the agent calls that has no entry under `mocks` raises `MissingMockError` in strict mode (default). That is intentional.

## Sample 1 — static outputs (happy path)

```json
{
  "scenario_id": "happy-path",
  "mocks": {
    "get_customer": [{"output": {"id": "CUST-001", "name": "Acme Corp", "tier": "enterprise"}}],
    "list_bills": [{"output": {"bills": [], "total_due": 0}}]
  }
}
```

## Sample 2 — input matching with operators

```json
{
  "scenario_id": "billing-edge-cases",
  "mocks": {
    "list_bills": [
      {"input": {"status": {"$in": ["overdue", "late"]}},
       "output": {"bills": [{"id": "BILL-901", "amount": 3200.0, "status": "overdue"}], "total_due": 3200.0}},
      {"input": {"status": "paid", "customer_id": {"$regex": "^CUST-"}},
       "output": {"bills": [], "total_due": 0}},
      {"input": {"customer_id": {"$contains": "TEST"}},
       "output": {"error": "customer not found"}},
      {"output": {"bills": [], "total_due": 0}}
    ],
    "create_invoice": [
      {"input": {"amount": {"$gt": 10000}}, "output": {"error": "approval required", "status": "pending_approval"}},
      {"output": {"invoice_id": "INV-1", "status": "draft"}}
    ]
  }
}
```

Operators (combine several on one field for AND): `$eq` (default), `$ne`, `$gt`, `$gte`, `$lt`, `$lte`, `$in`, `$nin`, `$contains`, `$regex`, `$exists`. Matching is partial — fields the LLM passes that the pattern doesn't mention are ignored. Operators apply to top-level fields; a nested dict pattern is compared literally.

## Sample 3 — dynamic placeholders

```json
{
  "scenario_id": "dynamic-values",
  "mocks": {
    "create_invoice": [{
      "output": {
        "invoice_id": "{{uuid}}",
        "invoice_number": "{{sequence('INV')}}",
        "customer_id": "{{input.customer_id}}",
        "amount": "{{input.amount}}",
        "due_date": "{{input.due_date | default('2026-12-31')}}",
        "created_at": "{{now}}",
        "reminder_at": "{{now + 30d}}",
        "created_by": "{{config.user_id | default('system')}}",
        "note": "Invoice for {{input.customer_id}} issued {{today}}"
      }
    }]
  }
}
```

| Placeholder | Resolves to |
|---|---|
| `{{now}}`, `{{today}}` | ISO timestamp / date |
| `{{now + 7d}}`, `{{now - 2h}}`, `{{today + 1w}}` | Relative; units `m h d w M y` |
| `{{start_of_day}}` … `{{end_of_year}}` | Boundary timestamps |
| `{{input.field}}`, `{{input.field \| default(v)}}` | Tool call argument |
| `{{config.field}}`, `{{config.field \| default(v)}}` | `RunnableConfig.configurable` value |
| `{{uuid}}` | Random UUID4 |
| `{{sequence('PFX')}}` | `PFX-001`, `PFX-002`, … |
| `{{random_int(a, b)}}`, `{{random_float(a, b)}}`, `{{choice('x', 'y')}}`, `{{random_string(n)}}` | Random values |

A string that is *only* a placeholder keeps the resolved type (`"{{input.amount}}"` → `250.0`); mixed strings are interpolated as text. Unknown expressions are returned literally with a warning, so a `{{...}}` in output means a typo. Current limits: field references take a single identifier (`{{input.customer_id}}`, not `{{input.customer.id}}`), `default(...)` takes a literal (not another placeholder), and a `None` argument value resolves to the literal placeholder — give such fields a `default(...)` or handle them in a factory.

## Writing good scenarios

- Mirror the real tool's response shape from the step-2 inventory, including field names the agent's prompt refers to.
- Give each scenario one purpose (happy path, empty results, upstream error, permission denied) and name the file after it.
- Prefer a data-driven case over factory code; move to a factory only for logic, raising, or values that depend on runtime context.
- Simulate failures both ways: an error-shaped success payload (`{"error": ...}`) tests how the agent reads tool output; a raising factory (PATTERNS.md) tests the `status="error"` path.
