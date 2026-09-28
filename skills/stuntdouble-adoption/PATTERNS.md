# Mock factory patterns

Hand-written factories go in `mocking/mocks.py`. A factory takes `scenario_metadata` (and optionally `config`) and returns the callable that stands in for the tool. **The returned callable's parameters must match the real tool's** — see the inventory rule in SKILL.md step 2.

Reach for a factory only when a data-driven registration can't express the behaviour. Everything below is `from stuntdouble import ...`.

## Simple: return configured output or a default

```python
def get_customer_mock(scenario_metadata: dict[str, Any]) -> Callable[..., Any]:
    cases = scenario_metadata.get("mocks", {}).get("get_customer", [])
    configured = cases[0].get("output") if cases else None

    def mock_fn(customer_id: str) -> dict:
        return configured or {"id": customer_id, "name": "Mock Customer"}

    return mock_fn
```

## Conditional on `scenario_metadata`

Top-level keys in the scenario steer behaviour. Keep the keys documented next to the factory.

```python
def create_invoice_mock(scenario_metadata: dict[str, Any]) -> Callable[..., Any]:
    policy = scenario_metadata.get("invoice_policy", "accept")
    max_amount = scenario_metadata.get("max_amount", 10_000)

    def mock_fn(customer_id: str, amount: float, due_date: str | None = None) -> dict:
        if policy == "reject_large" and amount > max_amount:
            raise ValueError(f"Invoice amount {amount} exceeds limit {max_amount}")
        return {"invoice_id": "INV-1", "customer_id": customer_id, "amount": amount, "status": "draft"}

    return mock_fn
```

A raised exception becomes `ToolMessage(status="error", content="Mock error: ...")` by default; with `create_mockable_tool_wrapper(..., strict_mock_errors=True)` it propagates so a test can `pytest.raises` it.

## Input matching inside a factory

When a data-driven registration almost fits but you need code around it, reuse the matcher and resolver directly:

```python
from stuntdouble import InputMatcher, resolve_output

_matcher = InputMatcher()

def query_bills_mock(scenario_metadata: dict[str, Any]) -> Callable[..., Any]:
    cases = scenario_metadata.get("mocks", {}).get("query_bills", [])

    def mock_fn(date_range: str, status: str | None = None) -> dict:
        kwargs = {"date_range": date_range, "status": status}
        for case in cases:
            if _matcher.matches(case.get("input"), kwargs):
                return resolve_output(case["output"], input_data=kwargs)
        return {"bills": []}

    return mock_fn
```

## Placeholders

`resolve_output(template, input_data=...)` handles `{{uuid}}`, `{{now}}`, `{{now + 30d}}`, `{{input.field}}`, `{{sequence('INV')}}` — full table in SCENARIOS.md. Build the template inside `mock_fn` when a value depends on the arguments:

```python
def mock_fn(customer_id: str, amount: float, due_date: str | None = None) -> dict:
    template = {
        "invoice_id": "{{uuid}}",
        "customer_id": "{{input.customer_id}}",
        "due_date": due_date or "{{now + 30d}}",
        "created_at": "{{now}}",
    }
    return resolve_output(template, input_data={"customer_id": customer_id, "amount": amount})
```

## Context-aware: read the `RunnableConfig`

Add a second `config` parameter and the registry passes the invocation's config. Anything the service placed under `configurable` (user id, tenant, headers, `thread_id`) is reachable. Essential for no-argument tools like `get_current_user`.

```python
from stuntdouble import get_configurable_context

def get_current_user_mock(scenario_metadata: dict[str, Any], config: dict[str, Any] | None = None) -> Callable[..., Any]:
    user_id = get_configurable_context(config).get("user_id", "mock-user")

    def mock_fn() -> dict:
        return {"user_id": user_id, "roles": ["viewer"]}

    return mock_fn
```

Data-driven cases can do the same declaratively with `{{config.user_id}}`.

## Async factory / async mock

Both are supported; the wrapper awaits what it needs to.

```python
async def search_docs_mock(scenario_metadata: dict[str, Any]) -> Callable[..., Any]:
    index = await load_fixture_index(scenario_metadata.get("fixture", "default"))

    async def mock_fn(query: str, top_k: int = 5) -> list[dict]:
        return index.search(query)[:top_k]

    return mock_fn
```

## Echo (debugging)

Returns the arguments the LLM produced, useful while tuning prompts.

```python
def echo_mock(scenario_metadata: dict[str, Any]) -> Callable[..., Any]:
    def mock_fn(query: str, top_k: int = 5) -> dict:
        return {"_echo": True, "query": query, "top_k": top_k}

    return mock_fn
```

For a data-driven tool the same thing is `registry.register_data_driven("search", echo_input=True)`.

## Registering

```python
registry.register("get_customer", mock_fn=get_customer_mock, tool=get_customer)  # tool= validates the signature now
registry.register("search_docs", mock_fn=search_docs_mock, when=lambda md: "fixture" in md)  # gate on the scenario
```

`when=` decides whether the mock applies for a scenario at all; a `False` result means "no mock" (and, in strict mode, `MissingMockError`). Use it to let some tools fall through to real implementations only when `require_mock_when_scenario=False`.
