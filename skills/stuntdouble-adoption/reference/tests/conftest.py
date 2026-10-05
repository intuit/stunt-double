"""Fixtures for the reference agent's mock tests."""

from __future__ import annotations

import pytest
from support import load_scenario

from stuntdouble import CallRecorder


@pytest.fixture
def recorder() -> CallRecorder:
    return CallRecorder()


@pytest.fixture
def happy_path() -> dict:
    return load_scenario("happy_path")


@pytest.fixture
def overdue_bills() -> dict:
    return load_scenario("overdue_bills")
