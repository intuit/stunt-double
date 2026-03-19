# Context-Aware Mocks

Access runtime context (user identity, request headers, tenant info) in your mock factories. This is especially useful for **no-argument tools** that need to return user-specific data.

---

## Overview

Standard mock factories receive only `scenario_metadata`. Context-aware mock factories also receive the full `RunnableConfig`, allowing access to runtime context like authentication headers, user IDs, and tenant information.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Context-Aware Mock Flow                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Standard Mock Factory:                                                    │
│   ──────────────────────                                                    │
│   mock_fn(scenario_metadata) → callable                                    │
│                                                                             │
│   Context-Aware Mock Factory:                                               │
│   ───────────────────────────                                               │
│   mock_fn(scenario_metadata, config) → callable                            │
│                         │                                                   │
│                         ▼                                                   │
│              get_configurable_context(config)                               │
│                         │                                                   │
│                         ▼                                                   │
│              {"agent_context": {"user_id": "U123", ...}}                   │
│                                                                             │
│   Detection: Automatic via signature inspection                            │
│   Backward compatible: Existing 1-arg factories still work                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### When to Use

| Scenario | Recommendation |
|----------|----------------|
| No-argument tools that need user context | ✅ Use context-aware mocks |
| Mocks that vary based on request headers | ✅ Use context-aware mocks |
| Multi-tenant testing scenarios | ✅ Use context-aware mocks |
| Simple static mocks | Standard factory is sufficient |
| Mocks that only use `scenario_metadata` | Standard factory is sufficient |

---

## Quick Start

```python
from stuntdouble import (
    MockToolsRegistry,
    create_mockable_tool_wrapper,
    get_configurable_context,
    inject_scenario_metadata,
)
from langgraph.prebuilt import ToolNode

registry = MockToolsRegistry()

# Context-aware mock factory: accepts BOTH scenario_metadata AND config
def user_context_mock(scenario_metadata: dict, config: dict = None):
    """Mock factory that extracts user context from RunnableConfig."""
    ctx = get_configurable_context(config)

    # Your application-specific extraction logic
    agent_context = ctx.get("agent_context", {})
    auth_header = agent_context.get("auth_header", {})
    user_id = auth_header.get("user_id", "unknown")
    org_id = auth_header.get("org_id", "unknown")

    # Return the mock callable
    return lambda: {"user_id": user_id, "org_id": org_id}

registry.register("get_current_user", mock_fn=user_context_mock)

# Build graph
wrapper = create_mockable_tool_wrapper(registry)
tool_node = ToolNode(tools, awrap_tool_call=wrapper)
```

When invoked, the `RunnableConfig` is automatically passed to your factory:

```python
config = {
    "configurable": {
        "scenario_metadata": {"mocks": {}},
        "agent_context": {
            "auth_header": {
                "user_id": "USER-123",
                "org_id": "ORG-456"
            }
        }
    }
}

result = await graph.ainvoke(
    {"messages": [HumanMessage("Who am I?")]},
    config=config
)
# → get_current_user returns {"user_id": "USER-123", "org_id": "ORG-456"}
```

---

## How It Works

### Signature Inspection

StuntDouble detects context-aware factories automatically by inspecting the function signature:

```python
# Standard factory (1 parameter) — receives scenario_metadata only
def standard_mock(scenario_metadata: dict):
    return lambda **kw: {"data": "static"}

# Context-aware factory (2 parameters) — receives both
def context_mock(scenario_metadata: dict, config: dict = None):
    ctx = get_configurable_context(config)
    return lambda **kw: {"user": ctx.get("user_id")}
```

**No registration changes needed.** The same `registry.register()` call works for both:

```python
registry.register("tool_a", mock_fn=standard_mock)  # Works
registry.register("tool_b", mock_fn=context_mock)    # Also works
```

### The `get_configurable_context` Helper

`get_configurable_context(config)` safely extracts the `configurable` dict from a `RunnableConfig`:

```python
from stuntdouble import get_configurable_context

# Normal config
config = {"configurable": {"agent_context": {"user": "Alice"}}}
ctx = get_configurable_context(config)
# → {"agent_context": {"user": "Alice"}}

# None config (safe)
ctx = get_configurable_context(None)
# → {}

# Missing configurable key (safe)
ctx = get_configurable_context({})
# → {}
```

---

## Examples

### Example 1: User Identity Mock

A common pattern for tools that return the current user's profile:

```python
def current_user_mock(scenario_metadata: dict, config: dict = None):
    ctx = get_configurable_context(config)
    agent_context = ctx.get("agent_context", {})
    auth_header = agent_context.get("auth_header", {})

    user_id = auth_header.get("user_id", "test-user")
    org_id = auth_header.get("org_id", "test-org")

    return lambda: {
        "user_id": user_id,
        "realm_id": realm_id,
        "display_name": f"Test User ({user_id})"
    }

registry.register("get_current_user", mock_fn=current_user_mock)
```

### Example 2: Tenant-Specific Data

Return different data based on the tenant/realm:

```python
def tenant_mock(scenario_metadata: dict, config: dict = None):
    ctx = get_configurable_context(config)
    tenant_id = ctx.get("agent_context", {}).get("tenant_id", "default")

    tenant_configs = {
        "tenant-a": {"plan": "enterprise", "max_users": 1000},
        "tenant-b": {"plan": "startup", "max_users": 10},
        "default": {"plan": "free", "max_users": 1},
    }

    data = tenant_configs.get(tenant_id, tenant_configs["default"])
    return lambda: data

registry.register("get_tenant_config", mock_fn=tenant_mock)
```

### Example 3: Request-Specific Mock

Use request headers to vary mock behavior:

```python
def locale_mock(scenario_metadata: dict, config: dict = None):
    ctx = get_configurable_context(config)
    locale = ctx.get("headers", {}).get("Accept-Language", "en-US")

    translations = {
        "en-US": {"greeting": "Hello", "currency": "USD"},
        "es-MX": {"greeting": "Hola", "currency": "MXN"},
        "fr-FR": {"greeting": "Bonjour", "currency": "EUR"},
    }

    data = translations.get(locale, translations["en-US"])
    return lambda: data

registry.register("get_locale_settings", mock_fn=locale_mock)
```

### Example 4: Combined with scenario_metadata

Use both scenario_metadata and config together:

```python
def combined_mock(scenario_metadata: dict, config: dict = None):
    """Use scenario_metadata for mock data and config for runtime context."""
    ctx = get_configurable_context(config)
    user_id = ctx.get("agent_context", {}).get("user_id", "unknown")

    # Get mock data from scenario_metadata
    mocks = scenario_metadata.get("mocks", {})
    customer_data = mocks.get("get_customer", [{}])[0].get("output", {})

    def mock_fn(customer_id: str) -> dict:
        return {
            **customer_data,
            "requested_by": user_id,  # From runtime config
            "customer_id": customer_id,  # From tool input
        }

    return mock_fn

registry.register("get_customer", mock_fn=combined_mock)
```

---

## Testing with Context-Aware Mocks

### pytest Example

```python
import pytest
from stuntdouble import (
    MockToolsRegistry,
    create_mockable_tool_wrapper,
    get_configurable_context,
    inject_scenario_metadata,
)

@pytest.fixture
def user_config():
    """Create config with user context."""
    config = inject_scenario_metadata({}, {"mocks": {}})
    config["configurable"]["agent_context"] = {
        "auth_header": {
            "user_id": "TEST-USER-001",
            "org_id": "TEST-ORG-001"
        }
    }
    return config

@pytest.fixture
def registry_with_context_mocks():
    registry = MockToolsRegistry()

    def user_mock(scenario_metadata: dict, config: dict = None):
        ctx = get_configurable_context(config)
        user_id = ctx.get("agent_context", {}).get("auth_header", {}).get("user_id", "unknown")
        return lambda: {"user_id": user_id}

    registry.register("get_current_user", mock_fn=user_mock)
    return registry

async def test_context_aware_mock(registry_with_context_mocks, user_config):
    wrapper = create_mockable_tool_wrapper(registry_with_context_mocks)
    # ... build graph and invoke with user_config ...
    # get_current_user will return {"user_id": "TEST-USER-001"}
```

### Multi-Tenant Test

```python
@pytest.mark.parametrize("tenant_id,expected_plan", [
    ("tenant-a", "enterprise"),
    ("tenant-b", "startup"),
    ("unknown", "free"),
])
async def test_tenant_specific_behavior(tenant_id, expected_plan):
    config = inject_scenario_metadata({}, {"mocks": {}})
    config["configurable"]["agent_context"] = {"tenant_id": tenant_id}

    result = await graph.ainvoke(
        {"messages": [HumanMessage("What's my plan?")]},
        config=config
    )
    # Assert based on expected_plan
```

---

## Key Points

- Mock factories can accept an **optional second parameter** `config` (the `RunnableConfig`)
- Use `get_configurable_context(config)` to safely extract the `configurable` dict
- **Backward compatible**: Existing factories with only `scenario_metadata` continue to work
- The `config` parameter is detected via signature inspection—no registration changes needed
- `get_configurable_context` returns an empty dict if config is `None` or missing `configurable`

---

## See Also

- [Quickstart Guide](quickstart.md) — Getting started with StuntDouble
- [LangGraph Approach](langgraph-integration.md) — Per-invocation mocking
- [Call Recording](call-recording.md) — Verify tool calls in tests
- [Mock Format Reference](../reference/mock-format.md) — Mock data format
