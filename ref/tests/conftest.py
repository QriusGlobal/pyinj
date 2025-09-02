"""Pytest configuration and shared fixtures for ServiceM8 SDK tests."""
# pyright: reportMissingSuperCall=false

from collections.abc import AsyncGenerator, Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest
from pytest_mock import MockerFixture

# Import the main modules to ensure they can be imported
from servicem8py import APIKeyAuth, OAuth2Auth, ServiceM8Client
from servicem8py._internal.di_container import (
    CLOCK,
    HTTP_CLIENT_FACTORY,
    LOGGER,
    MESSAGING_BUILDER,
    RESOURCE_FACTORY_BUILDER,
    TOKEN_STORE,
    container,
)
from servicem8py.auth import TokenInfo
from servicem8py.interfaces import HttpClient
from servicem8py.resources import CompanyResource, JobResource, StaffResource


@pytest.fixture
def sample_uuid() -> str:
    """Generate a sample UUID for testing."""
    return str(uuid4())


@pytest.fixture
def sample_datetime() -> datetime:
    """Generate a sample datetime for testing."""
    return datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def api_key_auth() -> APIKeyAuth:
    """Create an API key authentication strategy for testing."""
    return APIKeyAuth("test-api-key")


@pytest.fixture
def oauth_auth() -> OAuth2Auth:
    """Create an OAuth2 authentication strategy for testing."""
    return OAuth2Auth("test-client-id", "test-client-secret")


@pytest.fixture
def valid_token_info() -> TokenInfo:
    """Create a valid TokenInfo object for testing."""
    from datetime import timedelta

    expires_at = datetime.now(UTC) + timedelta(hours=1)

    return TokenInfo(
        access_token="test-access-token",
        refresh_token="test-refresh-token",
        expires_at=expires_at,
        scope="read_customers read_jobs",
        token_type="Bearer",
    )


@pytest.fixture
def expired_token_info() -> TokenInfo:
    """Create an expired TokenInfo object for testing."""
    from datetime import timedelta

    expires_at = datetime.now(UTC) - timedelta(hours=1)

    return TokenInfo(
        access_token="expired-access-token",
        refresh_token="test-refresh-token",
        expires_at=expires_at,
        scope="read_customers",
        token_type="Bearer",
    )


@pytest.fixture
def mock_http_client() -> HttpClient:
    """Create a mock HTTP client for testing."""
    mock_client = AsyncMock()

    # Set up default responses with proper read data (including server-set fields)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {
            "uuid": "550e8400-e29b-41d4-a716-446655440000",
            "active": 1,
            "edit_date": "2024-01-01T12:00:00Z",
            "name": "Mock Test Company",
            "billing_address": "123 Mock Street, Mock City",
            "phone": "555-0123",
            "email": "contact@mockcompany.com",
            "abn": "12345678901",
        }
    ]
    mock_response.raise_for_status.return_value = None

    mock_client.request.return_value = mock_response

    return mock_client


@pytest.fixture
async def mock_servicem8_client(api_key_auth: APIKeyAuth, autospec_httpclient: HttpClient):
    """Create a ServiceM8Client using DI overrides for HTTP client."""
    async with ServiceM8Client(api_key_auth, http_client=autospec_httpclient) as client:
        yield client


# --- New DI-friendly fixtures ---


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self._t = start

    def time(self) -> float:
        return self._t

    def advance(self, dt: float) -> None:
        self._t += dt


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock(start=0.0)


@pytest.fixture
def autospec_httpclient(mocker: MockerFixture) -> HttpClient:
    hc = mocker.create_autospec(HttpClient, spec_set=True, instance=True)
    # ensure async signature
    hc.request = mocker.AsyncMock()  # type: ignore[attr-defined]
    return hc


def make_response(
    status: int = 200, json_data: Any | None = None, headers: dict[str, str] | None = None
) -> httpx.Response:
    if json_data is not None:
        return httpx.Response(status, json=json_data, headers=headers)
    return httpx.Response(status, headers=headers)


@pytest.fixture
def di_overrides() -> Iterator[Callable[..., Any]]:
    """Yield a helper to use DI overrides within a test scope."""

    def _ctx(**kwargs: Any):
        return use_overrides(**kwargs)

    yield _ctx


@contextmanager
def use_overrides(**kwargs: Any):
    """Context-local dependency overrides for tests.

    Example:
        with use_overrides(http_client_factory=lambda: fake_http, clock=fake_clock):
            ...
    """
    mapping: dict[Any, Any] = {}
    if "http_client_factory" in kwargs:
        mapping[HTTP_CLIENT_FACTORY] = kwargs["http_client_factory"]
    if "clock" in kwargs:
        mapping[CLOCK] = kwargs["clock"]
    if "token_store" in kwargs:
        mapping[TOKEN_STORE] = kwargs["token_store"]
    if "logger" in kwargs:
        mapping[LOGGER] = kwargs["logger"]
    if "resource_factory_builder" in kwargs:
        mapping[RESOURCE_FACTORY_BUILDER] = kwargs["resource_factory_builder"]
    if "messaging_builder" in kwargs:
        mapping[MESSAGING_BUILDER] = kwargs["messaging_builder"]

    with container.use_overrides(mapping):
        yield


@pytest.fixture
def sample_job_data(sample_uuid: str) -> dict[str, Any]:
    """Generate sample job data for testing."""
    company_uuid = uuid4()

    return {
        "uuid": sample_uuid,
        "active": 1,
        "edit_date": "2024-01-01T12:00:00Z",
        "status": "Quote",
        "generated_job_id": 12345,
        "job_description": "Test job description",
        "job_address": "123 Test Street, Test City",
        "company_uuid": company_uuid,
        "total_invoice_amount": 1500.50,
        "job_priority": "High",
        "job_is_warranty": 0,
    }


@pytest.fixture
def sample_client_data(sample_uuid: str) -> dict[str, Any]:
    """Generate sample client data for testing."""
    return {
        "uuid": sample_uuid,
        "active": 1,
        "edit_date": "2024-01-01T12:00:00Z",
        "name": "Test Company Ltd",
        "billing_address": "456 Business Ave, Business City",
        "phone": "555-0123",
        "email": "contact@testcompany.com",
        "abn": "12345678901",
    }


@pytest.fixture
def sample_staff_data(sample_uuid: str) -> dict[str, Any]:
    """Generate sample staff data for testing."""
    return {
        "uuid": sample_uuid,
        "active": 1,
        "edit_date": "2024-01-01T12:00:00Z",
        "first": "John",
        "last": "Doe",
        "email": "john.doe@company.com",
        "mobile": "555-0199",
        "colour": "#FF0000",
    }


@pytest.fixture
def sample_job_allocation_data(sample_uuid: str) -> dict[str, Any]:
    """Generate sample job allocation data for testing."""
    job_uuid = uuid4()
    staff_uuid = uuid4()

    return {
        "uuid": sample_uuid,
        "active": 1,
        "edit_date": "2024-01-01T12:00:00Z",
        "job_uuid": job_uuid,
        "staff_uuid": staff_uuid,
        "allocation_date": "2024-01-15",
        "start_time": "09:00",
        "end_time": "17:00",
        "status": "Scheduled",
    }


@pytest.fixture
def mock_httpx_response() -> Any:
    """Create a mock httpx response object."""
    response = MagicMock()
    response.status_code = 200
    response.headers = {"Content-Type": "application/json"}
    response.json.return_value = {"result": "success"}
    response.text = '{"result": "success"}'
    response.raise_for_status.return_value = None
    return response


@pytest.fixture
def mock_httpx_client(mock_httpx_response: Any) -> Any:
    """Create a mock httpx AsyncClient."""
    client = AsyncMock()
    client.request.return_value = mock_httpx_response
    client.post.return_value = mock_httpx_response
    client.get.return_value = mock_httpx_response
    client.put.return_value = mock_httpx_response
    client.delete.return_value = mock_httpx_response
    return client


class MockServiceM8API:
    """Mock ServiceM8 API for testing."""

    def __init__(self):
        self.jobs = []
        self.clients = []
        self.staff = []
        self.call_count = 0

    def add_job(self, job_data: dict[str, Any]) -> None:
        """Add a job to the mock API."""
        self.jobs.append(job_data)

    def add_client(self, client_data: dict[str, Any]) -> None:
        """Add a client to the mock API."""
        self.clients.append(client_data)

    def add_staff(self, staff_data: dict[str, Any]) -> None:
        """Add staff to the mock API."""
        self.staff.append(staff_data)

    def get_jobs(self, query: Any | None = None) -> list[dict[str, Any]]:
        """Get jobs from mock API."""
        self.call_count += 1
        return self.jobs

    def get_clients(self, query: Any | None = None) -> list[dict[str, Any]]:
        """Get clients from mock API."""
        self.call_count += 1
        return self.clients

    def get_staff(self, query: Any | None = None) -> list[dict[str, Any]]:
        """Get staff from mock API."""
        self.call_count += 1
        return self.staff


@pytest.fixture
def mock_servicem8_api():
    """Create a mock ServiceM8 API for testing."""
    return MockServiceM8API()


# Test data constants
TEST_API_KEY = "test-api-key-12345"
TEST_CLIENT_ID = "test-client-id"
TEST_CLIENT_SECRET = "test-client-secret"
TEST_REDIRECT_URI = "http://localhost:8080/callback"

# Common test UUIDs
TEST_JOB_UUID = "550e8400-e29b-41d4-a716-446655440000"
TEST_CLIENT_UUID = "550e8400-e29b-41d4-a716-446655440001"
TEST_STAFF_UUID = "550e8400-e29b-41d4-a716-446655440002"


def pytest_configure(config: Any) -> None:
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "integration: mark test as integration test")
    config.addinivalue_line("markers", "unit: mark test as unit test")
    config.addinivalue_line("markers", "auth: mark test as authentication related")
    config.addinivalue_line("markers", "query: mark test as query building related")
    config.addinivalue_line("markers", "resource: mark test as resource related")
    config.addinivalue_line("markers", "exception: mark test as exception related")


def pytest_collection_modifyitems(config: Any, items: list[Any]) -> None:
    """Automatically mark tests based on their location."""
    for item in items:
        # Mark tests in test_auth.py as auth tests
        if "test_auth" in item.nodeid:
            item.add_marker(pytest.mark.auth)

        # Mark tests in test_query.py as query tests
        if "test_query" in item.nodeid:
            item.add_marker(pytest.mark.query)

        # Mark tests in test_resource_factory.py as resource tests
        if "test_resource_factory" in item.nodeid:
            item.add_marker(pytest.mark.resource)

        # Mark tests in test_exceptions.py as exception tests
        if "test_exceptions" in item.nodeid:
            item.add_marker(pytest.mark.exception)

        # Mark all tests as unit tests by default
        if not any(marker.name in ["integration"] for marker in item.iter_markers()):
            item.add_marker(pytest.mark.unit)


# Modern fixtures for dependency injection patterns
from collections.abc import Generator

import pytest_asyncio


# Force pytest-anyio to use asyncio backend only, so Trio is not required
@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def fresh_http_client_factory_per_test():
    """Provide a per-test http client factory so each ServiceM8Client gets its own client
    bound to the active event loop, avoiding cross-loop reuse issues.
    """
    from servicem8py._internal.http_client import HttpxClientAdapter

    def factory():
        return HttpxClientAdapter()

    with use_overrides(http_client_factory=factory):
        yield


# Session-scoped configuration
@pytest.fixture(scope="session")
def test_config() -> dict[str, Any]:
    """Session-scoped test configuration with environment variables support."""
    import os

    return {
        "base_url": os.getenv("SERVICEM8_TEST_URL", "https://api.servicem8.com"),
        "api_key": os.getenv("SERVICEM8_TEST_API_KEY", "test-api-key-12345"),
        "oauth_client_id": os.getenv("SERVICEM8_TEST_CLIENT_ID", "test-client-id"),
        "oauth_client_secret": os.getenv("SERVICEM8_TEST_CLIENT_SECRET", "test-client-secret"),
        "timeout": float(os.getenv("SERVICEM8_TEST_TIMEOUT", "30.0")),
        "max_retries": int(os.getenv("SERVICEM8_TEST_MAX_RETRIES", "3")),
    }


# Authentication factories
@pytest.fixture
def api_key_auth_factory(test_config: dict[str, Any]) -> Callable[[str], APIKeyAuth]:
    """Factory for creating APIKeyAuth instances."""

    def _create_auth(api_key: str | None = None) -> APIKeyAuth:
        return APIKeyAuth(api_key=api_key or test_config["api_key"])

    return _create_auth


@pytest.fixture
def oauth_auth_factory(test_config: dict[str, Any]) -> Callable[..., OAuth2Auth]:
    """Factory for creating OAuth2Auth instances."""

    def _create_oauth_auth(
        client_id: str | None = None, client_secret: str | None = None, **kwargs: Any
    ) -> OAuth2Auth:
        return OAuth2Auth(
            client_id=client_id or test_config["oauth_client_id"],
            client_secret=client_secret or test_config["oauth_client_secret"],
            **kwargs,
        )

    return _create_oauth_auth


@pytest.fixture
def token_info_factory() -> Callable[..., TokenInfo]:
    """Factory for creating TokenInfo instances."""
    from datetime import timedelta

    def _create_token_info(
        access_token: str = "test-access-token",
        expires_delta: timedelta = timedelta(hours=1),
        refresh_token: str | None = "test-refresh-token",
        **kwargs: Any,
    ) -> TokenInfo:
        expires_at = datetime.now(UTC) + expires_delta
        return TokenInfo(
            access_token=access_token,
            expires_at=expires_at,
            refresh_token=refresh_token,
            scope="read_customers read_jobs",
            token_type="Bearer",
            **kwargs,
        )

    return _create_token_info


# Client factories with proper dependency injection
@pytest_asyncio.fixture
async def client_factory(
    test_config: dict[str, Any], api_key_auth_factory: Callable[[str], APIKeyAuth]
) -> AsyncGenerator[Callable[..., ServiceM8Client]]:
    """Factory for creating ServiceM8 clients with different configurations."""
    created_clients: list[ServiceM8Client] = []

    def _create_client(
        api_key: str | None = None, auth_strategy: Any = None, **kwargs: Any
    ) -> ServiceM8Client:
        if auth_strategy is None:
            auth_strategy = api_key_auth_factory(api_key or "test-api-key")

        client = ServiceM8Client(
            auth_strategy=auth_strategy,
            timeout=test_config["timeout"],
            max_retries=test_config["max_retries"],
            **kwargs,
        )
        created_clients.append(client)
        return client

    yield _create_client

    # Cleanup all created clients
    for client in created_clients:
        try:
            await client.close()  # type: ignore[attr-defined]
        except Exception:
            pass  # Best effort cleanup


# Parametrized fixtures for different test scenarios
@pytest.fixture(
    params=[
        {"api_key": "test-key-1", "scenario": "basic"},
        {"api_key": "test-key-2", "scenario": "alternative"},
    ]
)
def auth_scenario(
    request: pytest.FixtureRequest, api_key_auth_factory: Callable[[str], APIKeyAuth]
) -> dict[str, Any]:
    """Parametrized authentication scenarios."""
    params = request.param
    auth = api_key_auth_factory(params["api_key"])
    return {"auth": auth, "scenario": params["scenario"], "api_key": params["api_key"]}


@pytest.fixture(
    params=[
        {"expires_delta": timedelta(hours=1), "should_be_valid": True},
        {"expires_delta": timedelta(minutes=3), "should_be_valid": False},  # Within 5-min buffer
        {"expires_delta": timedelta(hours=-1), "should_be_valid": False},  # Expired
    ]
)
def token_scenario(
    request: pytest.FixtureRequest, token_info_factory: Callable[..., TokenInfo]
) -> dict[str, Any]:
    """Parametrized token expiry scenarios."""
    params = request.param
    token = token_info_factory(expires_delta=params["expires_delta"])
    return {"token": token, "scenario": params, "should_be_valid": params["should_be_valid"]}


# Resource test data factories
@pytest.fixture
def job_data_factory() -> Callable[..., dict[str, Any]]:
    """Factory for creating job test data."""
    import uuid

    def _create_job_data(
        job_address: str | None = None, job_description: str | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        unique_id = str(uuid.uuid4())[:8]
        return {
            "uuid": str(uuid.uuid4()),
            "job_address": job_address or f"123 Test St, Test City {unique_id}",
            "job_description": job_description or f"Test job description {unique_id}",
            "job_is_warranty": False,
            "status": "Pending",
            **kwargs,
        }

    return _create_job_data


@pytest.fixture
def company_data_factory() -> Callable[..., dict[str, Any]]:
    """Factory for creating company test data."""
    import uuid

    def _create_company_data(
        name: str | None = None, abn: str | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        unique_id = str(uuid.uuid4())[:8]
        return {
            "uuid": str(uuid.uuid4()),
            "name": name or f"Test Company {unique_id}",
            "abn": abn or f"1234567890{unique_id[:2]}",
            "address": f"456 Business Ave, Business City {unique_id}",
            "contact_first_name": "John",
            "contact_last_name": "Doe",
            **kwargs,
        }

    return _create_company_data


@pytest.fixture
def staff_data_factory() -> Callable[..., dict[str, Any]]:
    """Factory for creating staff test data."""
    import uuid

    def _create_staff_data(
        first_name: str | None = None, last_name: str | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        unique_id = str(uuid.uuid4())[:8]
        return {
            "uuid": str(uuid.uuid4()),
            "first_name": first_name or f"Staff{unique_id}",
            "last_name": last_name or f"Member{unique_id}",
            "email": f"staff{unique_id}@example.com",
            "is_active": True,
            **kwargs,
        }

    return _create_staff_data


# Integration test fixtures (only used when SERVICEM8_TEST_API_KEY is real)
@pytest.fixture
def integration_test_enabled() -> bool:
    """Check if integration tests should run."""
    import os

    api_key = os.getenv("SERVICEM8_TEST_API_KEY", "")
    return bool(api_key and api_key != "test-api-key-12345")


@pytest_asyncio.fixture
async def integration_client(
    client_factory: Callable[..., ServiceM8Client], integration_test_enabled: bool
) -> AsyncGenerator[ServiceM8Client | None]:
    """Integration test client (only when real API key is provided)."""
    if not integration_test_enabled:
        yield None
        return

    client = client_factory()
    async with client:
        yield client


# Resource cleanup helpers
@pytest.fixture
def cleanup_tracker() -> Generator[dict[str, list[str]]]:
    """Track resources created during tests for cleanup."""
    tracker: dict[str, list[str]] = {
        "jobs": [],
        "companies": [],
        "staff": [],
    }
    yield tracker
    # Cleanup happens in reverse order to handle dependencies


@pytest_asyncio.fixture
async def managed_company(
    integration_client: ServiceM8Client | None,
    company_data_factory: Callable[..., dict[str, Any]],
    cleanup_tracker: dict[str, list[str]],
) -> AsyncGenerator[dict[str, Any] | None]:
    """Managed company that gets cleaned up automatically."""
    if not integration_client:
        yield None
        return

    company_data = company_data_factory()
    # Note: Actual ServiceM8 API integration would be implemented here
    cleanup_tracker["companies"].append(company_data["uuid"])

    yield company_data

    # Cleanup
    try:
        # await integration_client.company.delete(company_data["uuid"])
        cleanup_tracker["companies"].remove(company_data["uuid"])
    except Exception:
        pass  # Best effort cleanup


@pytest_asyncio.fixture
async def managed_job(
    integration_client: ServiceM8Client | None,
    managed_company: dict[str, Any] | None,
    job_data_factory: Callable[..., dict[str, Any]],
    cleanup_tracker: dict[str, list[str]],
) -> AsyncGenerator[dict[str, Any] | None]:
    """Managed job that gets cleaned up automatically."""
    if not integration_client or not managed_company:
        yield None
        return

    job_data = job_data_factory()
    job_data["company_uuid"] = managed_company["uuid"]
    cleanup_tracker["jobs"].append(job_data["uuid"])

    yield job_data

    # Cleanup
    try:
        # await integration_client.job.delete(job_data["uuid"])
        cleanup_tracker["jobs"].remove(job_data["uuid"])
    except Exception:
        pass  # Best effort cleanup


# Parametrized test scenarios for comprehensive testing
@pytest.fixture(
    params=[
        {"resource_type": "job", "scenario": "basic"},
        {"resource_type": "company", "scenario": "basic"},
        {"resource_type": "staff", "scenario": "basic"},
    ]
)
def resource_type_scenario(request: pytest.FixtureRequest) -> dict[str, str]:
    """Parametrized resource type scenarios."""
    return request.param


@pytest.fixture(
    params=[
        {"status": "pending", "data": {"job_is_warranty": False}},
        {"status": "scheduled", "data": {"job_is_warranty": False}},
        {"status": "completed", "data": {"job_is_warranty": True}},
    ]
)
def job_status_scenario(request: pytest.FixtureRequest) -> dict[str, Any]:
    """Parametrized job status scenarios."""
    return request.param


# Resource fixtures for modern tests
@pytest_asyncio.fixture
async def company_resource(
    client_factory: Callable[..., ServiceM8Client], autospec_httpclient: HttpClient
) -> AsyncGenerator[CompanyResource]:
    """Fixture providing a configured company resource with mock HTTP client."""
    client = client_factory(http_client=autospec_httpclient)
    async with client:
        yield client.company


@pytest_asyncio.fixture
async def job_resource(
    client_factory: Callable[..., ServiceM8Client], autospec_httpclient: HttpClient
) -> AsyncGenerator[JobResource]:
    """Fixture providing a configured job resource with mock HTTP client."""
    client = client_factory(http_client=autospec_httpclient)
    async with client:
        yield client.job


@pytest_asyncio.fixture
async def staff_resource(
    client_factory: Callable[..., ServiceM8Client], autospec_httpclient: HttpClient
) -> AsyncGenerator[StaffResource]:
    """Fixture providing a configured staff resource with mock HTTP client."""
    client = client_factory(http_client=autospec_httpclient)
    async with client:
        yield client.staff
