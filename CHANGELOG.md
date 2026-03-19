# Changelog

All notable changes to this project will be documented in this file.

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
