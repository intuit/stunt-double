# Dependencies

This document explains StuntDouble's dependencies and why each is required.

---

## Core Dependencies

These are installed automatically with StuntDouble:

```toml
[project]
dependencies = [
    "langchain-core>=1.2.5,<2",
    "pydantic>=2.0.0,<3",
    "langgraph>=1.0.0,<2",
]
```

### langchain-core

**Version:** `>=1.2.5`

**Why it's needed:**

| Component | Usage |
|-----------|-------|
| `StructuredTool` | Converting mirrored tools to LangChain format |
| `RunnableConfig` | Per-invocation configuration passing |
| Type definitions | Tool protocols and interfaces |

**Used by:**
- `stuntdouble/wrapper.py` — `create_mockable_tool_wrapper`, `mockable_tool_wrapper`
- `stuntdouble/mirroring/` — LangChain tool conversion

### pydantic

**Version:** `>=2.0.0`

**Why it's needed:**

| Component | Usage |
|-----------|-------|
| `BaseModel` | Schema validation for tools |
| `create_model` | Dynamic schema generation from MCP tools |
| Field validation | Input/output type checking |
| JSON schema | Converting between formats |

**Used by:**
- `stuntdouble/wrapper.py` — Dynamic schema conversion
- `stuntdouble/types.py` — Type models (ScenarioMetadata, MockRegistration, etc.)
- `stuntdouble/validation.py` — Signature validation

### langgraph

**Version:** `>=1.0.0`

**Why it's needed:**

| Component | Usage |
|-----------|-------|
| `StateGraph` | Building mockable agent graphs |
| `ToolNode` | Native node with `awrap_tool_call` hook |
| `ToolCallRequest` | Tool call data extraction |
| Message types | State management compatibility |

**Used by:**
- `stuntdouble/wrapper.py` — `mockable_tool_wrapper`, `create_mockable_tool_wrapper`

---

## Development Dependencies

These are only needed for development and testing:

```toml
[dependency-groups]
dev = [
    "pytest>=9.0.0,<10",
    "pytest-cov>=7.0.0,<8",
    "pytest-xdist>=3.8.0,<4",
    "pytest-asyncio>=1.3.0,<2",
    "mypy>=1.19.0,<2",
    "ruff>=0.15.0,<1",
    "langchain-openai>=1.1.0,<2",
]
```

| Package | Purpose |
|---------|---------|
| `pytest` | Test framework |
| `pytest-cov` | Coverage reporting |
| `pytest-xdist` | Parallel test execution |
| `pytest-asyncio` | Async test support |
| `mypy` | Static type checking |
| `ruff` | Linting and formatting |
| `langchain-openai` | LLM client for mirroring tests |

---

## Optional Dependencies

These are NOT included but may be needed for specific features:

### For LLM-powered mock generation

```bash
pip install langchain-openai
# or
pip install foundationsai
```

**When needed:** Using `ToolMirror.with_llm()` for realistic mock data generation.

### For MCP mirroring support

```bash
pip install "stuntdouble[mcp]"
```

**When needed:** Using live MCP discovery and mirroring. The optional `mcp` extra currently provides the additional client dependency used by the StuntDouble MCP client.

---

## Version Compatibility

### Python Versions

StuntDouble supports:
- Python 3.12
- Python 3.13

### LangChain Ecosystem

StuntDouble is designed around the LangChain Core / LangGraph 1.x series:

| Package | Compatible Versions |
|---------|-------------------|
| `langchain-core` | 1.x |
| `langgraph` | 1.x |

**Note:** Optional integrations such as `langchain-openai` are not pinned in StuntDouble's package metadata. If you use them, align them with your project's existing LangChain stack.

If you encounter dependency conflicts, ensure your project's LangChain packages are aligned:

```bash
# Check versions
pip show langchain-core langgraph langchain-openai

# Upgrade to compatible versions
pip install --upgrade langchain-core>=1.2.5 langgraph>=1.0.0
```

---

## Dependency Graph

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        StuntDouble Dependencies                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│                          stuntdouble                                        │
│                               │                                             │
│         ┌─────────┬───────────┬─────────┐                                  │
│         │         │           │         │                                  │
│         ▼         ▼           ▼         ▼                                  │
│   langchain-core  pydantic  langgraph  (optional)                          │
│         │           │           │         │                                │
│         │           │           │         ▼                                │
│         │           │                     │     langchain-openai           │
│         │           │                     │           │                    │
│         └───────────┴─────────────────────┴───────────┘                    │
│                               │                                             │
│                               ▼                                             │
│                   Common transitive deps:                                   │
│                   • typing-extensions                                       │
│                   • httpx/httpcore                                          │
│                   • tenacity                                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Minimal Installation

For the absolute minimal installation (core mocking only):

```python
# These are the only truly required imports for basic mocking:
from stuntdouble.matching import InputMatcher
from stuntdouble.resolving import ValueResolver
```

The core matching and resolution logic has no external dependencies beyond the standard library. However, for practical use with LangChain/LangGraph agents, the full dependency set is recommended.

---

## Troubleshooting

### Dependency Conflicts

If you see errors like:
```
langchain-core 1.x requires ..., but you have ...
```

**Solution:**
```bash
# Pin versions explicitly
pip install langchain-core==1.2.5 langgraph==1.0.0
pip install stuntdouble
```

### Missing Optional Dependencies

If you see:
```
ImportError: langchain-openai is not installed
```

**Solution:**
```bash
pip install langchain-openai
```

