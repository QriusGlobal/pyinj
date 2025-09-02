"""Pytest configuration and shared fixtures for pyinj tests."""

import pytest
import asyncio
from typing import Generator, AsyncGenerator

from pyinj.container import Container
from pyinj.tokens import Token, Scope


@pytest.fixture
def container() -> Container:
    """Create a fresh container for testing."""
    return Container()


@pytest.fixture
def registered_container() -> Container:
    """Create a container with some pre-registered dependencies."""
    container = Container()
    
    # Register some test dependencies
    container.register(Token("database", TestDatabase), lambda: TestDatabase())
    container.register(Token("cache", TestCache), lambda: TestCache())
    container.register_singleton(Token("config", TestConfig), lambda: TestConfig())
    
    return container


@pytest.fixture
async def async_container() -> AsyncGenerator[Container, None]:
    """Create a container for async testing."""
    container = Container()
    yield container
    # Cleanup if needed
    container.clear()


# Test classes for fixtures
class TestDatabase:
    """Test database for fixtures."""
    def __init__(self):
        self.connected = True
    
    def query(self, sql: str):
        return f"Result of: {sql}"


class TestCache:
    """Test cache for fixtures."""
    def __init__(self):
        self.data = {}
    
    def get(self, key: str):
        return self.data.get(key)
    
    def set(self, key: str, value):
        self.data[key] = value


class TestConfig:
    """Test configuration for fixtures."""
    def __init__(self):
        self.settings = {
            "debug": True,
            "host": "localhost",
            "port": 8080,
        }


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "unit: mark test as unit test"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )


# Async event loop fixture for pytest-asyncio
@pytest.fixture
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
