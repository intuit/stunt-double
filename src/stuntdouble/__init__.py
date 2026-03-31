# ABOUTME: Exposes the public StuntDouble import surface from one top-level package module.
# ABOUTME: Re-exports the main wrappers, registries, builders, validators, recorders, and helper functions.
"""StuntDouble - Tool mocking framework for AI agent testing."""

from importlib.metadata import version as _pkg_version

from stuntdouble.builder import MockBuilder
from stuntdouble.config import (
    extract_scenario_metadata_from_config,
    get_configurable_context,
    get_scenario_metadata,
    inject_scenario_metadata,
)
from stuntdouble.exceptions import (
    InputNotMatchedError,
    MissingMockError,
    MockAssertionError,
    SignatureMismatchError,
)
from stuntdouble.matching import InputMatcher
from stuntdouble.mock_registry import MockToolsRegistry
from stuntdouble.recorder import CallRecord, CallRecorder
from stuntdouble.resolving import ValueResolver, resolve_output
from stuntdouble.scenario_mocking import DataDrivenMockFactory, register_data_driven
from stuntdouble.types import MockFn, MockRegistration, ScenarioMetadata, WhenPredicate
from stuntdouble.validation import (
    validate_mock_parameters,
    validate_mock_signature,
    validate_registry_mocks,
)
from stuntdouble.wrapper import (
    create_mockable_tool_wrapper,
    default_registry,
    mockable_tool_wrapper,
)

__version__ = _pkg_version("stuntdouble")

__all__ = [
    "CallRecord",
    "CallRecorder",
    "DataDrivenMockFactory",
    "InputMatcher",
    "InputNotMatchedError",
    "MissingMockError",
    "MockAssertionError",
    "MockBuilder",
    "MockFn",
    "MockRegistration",
    "MockToolsRegistry",
    "ScenarioMetadata",
    "SignatureMismatchError",
    "ValueResolver",
    "WhenPredicate",
    "create_mockable_tool_wrapper",
    "default_registry",
    "extract_scenario_metadata_from_config",
    "get_configurable_context",
    "get_scenario_metadata",
    "inject_scenario_metadata",
    "mockable_tool_wrapper",
    "register_data_driven",
    "resolve_output",
    "validate_mock_parameters",
    "validate_mock_signature",
    "validate_registry_mocks",
]
