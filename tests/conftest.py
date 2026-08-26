"""Shared pytest fixtures."""

import pytest


@pytest.fixture
def anyio_backend() -> str:
    """Restrict anyio's pytest plugin to the asyncio backend (trio is not a project dependency)."""
    return "asyncio"
