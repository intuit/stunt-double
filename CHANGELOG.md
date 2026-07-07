# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Per-release notes for tagged versions are auto-generated and published on the
[GitHub Releases page](https://github.com/intuit/StuntDouble/releases). This
file records notable unreleased changes and the initial release.

## [Unreleased]

### Fixed

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
