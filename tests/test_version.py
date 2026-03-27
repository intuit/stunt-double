# ABOUTME: Tests that the package version is consistent between pyproject.toml and __init__.py.
# ABOUTME: Ensures __version__ is dynamically derived from package metadata.

import importlib.metadata

import stuntdouble


def test_version_matches_package_metadata():
    """__version__ should match the version declared in pyproject.toml."""
    expected = importlib.metadata.version("stuntdouble")
    assert stuntdouble.__version__ == expected


def test_version_is_not_hardcoded_placeholder():
    """__version__ should not be the old hardcoded placeholder."""
    assert stuntdouble.__version__ != "0.1.0"
