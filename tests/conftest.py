"""Pytest configuration and fixtures."""

import pytest

# Configure pytest-asyncio to use function-scoped event loops
pytest_plugins = ('pytest_asyncio',)

