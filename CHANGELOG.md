# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Per-release notes for tagged versions are auto-generated and published on the
[GitHub Releases page](https://github.com/intuit/StuntDouble/releases). This
file records notable unreleased changes and the initial release.

## [Unreleased]

## [2.1.3] - 2026-09-28

### Fixed

- **Multiple placeholders in one string** now interpolate independently, so
  values such as `{{input.a}}-{{input.b}}` resolve correctly instead of being
  treated as one unknown placeholder expression.
- **Operators inside nested patterns**: `InputMatcher` now recurses into nested dict
  patterns, so operators (`$regex`, `$gt`, `$in`, `$exists`, ...) work at any depth,
  e.g. `{"filter": {"amount": {"$gt": 100}}}`. Previously a nested operator dict was
  compared as a literal value and never matched. Nested matching is partial, like the
  top level: extra keys in the actual value are ignored.
- **Signature validation and `**kwargs` mocks**: mocks that take `**kwargs` (what
  `register_data_driven` and `MockBuilder.returns()/returns_fn()` build) no longer
  fail `validate_signatures=True` with "Missing parameters"; extra required
  parameters on such a mock are still reported.
- **`{{input.x}}` / `{{config.x}}` resolving to `None`**: a reference whose value
  is `None`, and `| default(null)` / `| default(none)`, now resolve to `None` instead
  of being left as the literal placeholder with an "Unknown placeholder" warning.
- **Mock factory errors** are no longer swallowed: `MockToolsRegistry.resolve()` raises
  the new `MockFactoryError` (chained from the original exception) instead of returning
  `None`, which made a broken mock surface as `MissingMockError: No mock registered`.
  The wrapper returns `ToolMessage(status="error")` for it, or re-raises with
  `strict_mock_errors=True`, and records the error on the `CallRecorder`. In
  lenient mode a broken factory therefore no longer falls back to the real tool.
- **Async mock factories and `MockFactoryError`**: awaiting an async mock factory in the
  tool wrapper now catches exceptions and wraps them in `MockFactoryError`, matching sync
  factories (#79).
- **Arity detection in mock factories**: `MockToolsRegistry.resolve()` and
  `validate_mock_signature` now evaluate `sig.bind()` before invoking the factory.
  Internal `TypeError` exceptions raised inside 2-argument factory functions are
  preserved rather than triggering a fallback to 1-argument invocation (#79).
- **`{{sequence('X')}}` in data-driven mocks**: counters now persist across calls of
  the same resolved data-driven mock callable (e.g. when calling the factory's result
  directly), instead of restarting at `001` on every call. Through the tool wrapper
  each call still resolves a fresh callable, so the ids restart there (see #56).
- **stdio transport hangs**: the MCP client now drains the subprocess `stderr`
  pipe on a background thread, so a server that logs verbosely can no longer
  deadlock the client by filling the OS pipe buffer.
- **stdio read timeout**: JSON-RPC responses are now read with a configurable
  `read_timeout` (default 30s) via `MCPServerConfig`, so an unresponsive server
  no longer blocks `list_tools`/`call_tool` indefinitely.
- **`MockBuilder.returns_fn()`** now honors `.when(**conditions)` input matching
  (raising `InputNotMatchedError` on a non-matching call) and `.echoes_input(...)`,
  matching `.returns()`. Previously both were silently ignored.
- **Documentation**: corrected the module-structure map and dependency "used by"
  paths (there is no `stuntdouble/langgraph/` or top-level `mcp/` package — the
  layout is flat with MCP under `mirroring/`), fixed overstated Python-version
  support (3.12–3.13), replaced a fabricated dev-dependency block, and fixed a
  `NameError` in a context-aware-mocks example.

### Changed

- Python 3.14 is now tested in CI (unit and e2e matrices) and listed in the
  package classifiers.
- CI now enforces `mypy` type checking and `ruff format --check` in addition to
  `ruff check`; the source tree is fully type-clean under mypy.
- Refreshed `uv.lock` to match the declared `requires-python = ">=3.12"` (it had
  drifted to `>=3.11` and lagged the project version). CI and release now run
  `uv sync --frozen` so the lockfile can no longer silently drift from
  `pyproject.toml`.
- Docs are now built from the `docs` dependency group (`uv sync --group docs`)
  instead of a separate `docs/requirements.txt`, which had drifted to older
  Sphinx/MyST major versions; the redundant `docs/requirements.txt` is removed.

## 0.1.0

Initial public release.

### Features

- Per-invocation tool mocking via `MockToolsRegistry`
- Fluent mock builder API (`registry.mock("tool").returns(...)`)
- Data-driven mock factory with JSON scenario files
- Input matching with operator-based predicates
- Dynamic value resolution with placeholders
- Call recording for test assertions
- Mock signature validation against real tool schemas
- MCP tool mirroring (auto-discover and mock MCP server tools)
- LangGraph ToolNode integration via `create_mockable_tool_wrapper`
