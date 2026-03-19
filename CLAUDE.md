# StuntDouble

Tool mocking framework for AI agent testing, built for LangGraph.

## Build & Test

```bash
uv sync                          # Install deps
uv run pytest                    # Run unit tests
uv run pytest tests-e2e/         # Run e2e tests
uv run ruff check .              # Lint
uv run ruff format .             # Format
uv run mypy src/                 # Type check
```

## Package Structure

- `src/stuntdouble/` — single flat namespace, all public exports in `__init__.py`
- `src/stuntdouble/mirroring/` — MCP tool mirroring subsystem
- `tests/` — unit tests
- `tests-e2e/` — end-to-end tests
- `docs/` — Sphinx documentation

## Conventions

- Line length: 120 (ruff)
- Python: 3.11+
- Build: hatchling
- Package manager: uv
- All public API exported from `stuntdouble.__init__`
- No subpackage public APIs (import from `stuntdouble`, not `stuntdouble.X`)
