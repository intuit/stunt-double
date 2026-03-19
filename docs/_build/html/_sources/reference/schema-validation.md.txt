# Mock Input Validation Reference

Reference for validating `scenario_metadata["mocks"]` and mock/tool compatibility in StuntDouble.

---

## Overview

StuntDouble exposes three related validation helpers:

| Function | What it validates |
|----------|-------------------|
| `validate_mock_signature(tool, mock_fn, scenario_metadata, config)` | Whether a mock factory returns a callable compatible with the real tool signature |
| `validate_mock_parameters(tool, mock_cases)` | Whether data-driven mock `input` cases reference valid tool parameters |
| `validate_registry_mocks(tools, scenario_metadata)` | Validate all runtime mock cases in `scenario_metadata["mocks"]` against a list of tools |

These helpers validate mock configuration. They do **not** validate mock outputs.

---

## Signature Validation

`validate_mock_signature()` checks the callable returned by a mock factory against the real tool's parameter list.

It supports:
- Pydantic-based tool schemas
- JSON Schema dicts used by mirrored MCP tools
- Legacy mock factories that accept only `scenario_metadata`
- Context-aware mock factories that accept `scenario_metadata` and `config`

```python
from stuntdouble import validate_mock_signature

is_valid, error = validate_mock_signature(get_weather_tool, weather_mock_factory)
if not is_valid:
    print(error)
```

### What it catches

- Missing parameters in the mock callable
- Extra required parameters in the mock callable
- Cases where the real tool parameter is optional but the mock makes it required

### What happens at runtime

When `create_mockable_tool_wrapper(..., tools=..., validate_signatures=True)` is used, runtime signature mismatches raise `SignatureMismatchError`.

---

## Parameter Validation for Data-Driven Mocks

`validate_mock_parameters()` checks the `input` keys in data-driven mock cases against the real tool's accepted parameters.

```python
from stuntdouble import validate_mock_parameters

errors = validate_mock_parameters(
    get_weather_tool,
    [
        {"input": {"city": "NYC"}, "output": {"temp": 72}},
        {"input": {"wrong_param": "value"}, "output": {"temp": 70}},
    ],
)
```

Example error:

```text
Case 2: Unknown parameter 'wrong_param'. Valid parameters: city, units
```

Cases without an `input` key are treated as catch-all cases and are skipped by this validator.

---

## Validating Full Scenario Metadata

Use `validate_registry_mocks()` when you want to validate an entire runtime `scenario_metadata` payload before invoking your graph.

```python
from stuntdouble import validate_registry_mocks

errors = validate_registry_mocks(all_tools, scenario_metadata)
if errors:
    for tool_name, tool_errors in errors.items():
        print(tool_name, tool_errors)
```

Returned value:

- `dict[str, list[str]]`
- Empty dict means validation passed
- Unknown tool names are reported as errors

This is the best fit when your tests or evaluation harness load `scenario_metadata["mocks"]` dynamically.

---

## Data-Driven Mock Notes

This validation story is primarily for data-driven mocks registered via `register_data_driven()` or `DataDrivenMockFactory`.

Those mocks support:
- `input` matching operators like `$gt`, `$in`, and `$regex`
- catch-all cases with no `input`
- `fallback=...`
- `echo_input=True`
- placeholder resolution such as `{{now}}`, `{{input.customer_id}}`, and `{{config.user_id}}`

See [Mock Format Reference](mock-format.md) for the runtime mock format itself.

---

## What This Page Does Not Cover

- Output-schema validation
- Pydantic model generation for mock outputs
- Automatic coercion of invalid mock inputs
- Silent fallback on validation failure

If runtime signature validation fails in the wrapper, StuntDouble raises `SignatureMismatchError` instead of silently proceeding.

---

## See Also

- [Mock Signature Validation Guide](../guides/signature-validation.md)
- [Mock Data Format Reference](mock-format.md)

