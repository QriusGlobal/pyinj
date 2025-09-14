# Usage Guide

This guide covers practical usage patterns, framework integration, and real-world examples of PyInj in production applications.

## Framework Integration

### FastAPI Integration

PyInj integrates seamlessly with FastAPI through multiple approaches:

#### Option 1: FastAPI Dependencies (Traditional)

```
from typing import Annotated
from fastapi import FastAPI, Depends
from pyinj import Container, Token, Scope

app = FastAPI()
container = Container()

# Define services
class UserService:
    def __init__(self, db: Database, logger: Logger):
        self.db = db
        self.logger = logger

    def get_user(self, user_id: int) -> dict[str, str]:
        self.logger.info(f"Fetching user {user_id}")
        return self.db.query(f"SELECT * FROM users WHERE id = {user_id}")[0]

    def create_user(self, user_data: dict[str, str]) -> dict[str, str]:
        self.logger.info(f"Creating user: {user_data['name']}")
        # Create user logic here
        return {"id": "123", "name": user_data["name"]}

# Register services
USER_SERVICE = Token[UserService]("user_service", scope=Scope.SINGLETON)
container.register(USER_SERVICE, lambda: UserService(
    db=container.get(DATABASE),
    logger=container.get(LOGGER)
))

# FastAPI dependency
def get_user_service() -> UserService:
    return container.get(USER_SERVICE)

# Endpoints using FastAPI dependencies
@app.post("/users")
async def create_user(
    user_data: dict[str, str],
    user_service: Annotated[UserService, Depends(get_user_service)]
) -> dict[str, str]:
    return user_service.create_user(user_data)

@app.get("/users/{user_id}")
async def get_user(
    user_id: int,
    user_service: Annotated[UserService, Depends(get_user_service)]
) -> dict[str, str]:
    return user_service.get_user(user_id)
```

#### Option 2: PyInj @inject Decorator (Recommended)

```
from pyinj import inject, set_default_container

# Set global container
set_default_container(container)

@app.post("/users-v2")
@inject  # Much cleaner!
async def create_user_v2(
    user_data: dict[str, str],
    user_service: UserService  # Auto-injected
) -> dict[str, str]:
    return user_service.create_user(user_data)

@app.get("/users-v2/{user_id}")
@inject
async def get_user_v2(
    user_id: int,
    user_service: UserService  # Auto-injected
) -> dict[str, str]:
    return user_service.get_user(user_id)
```

#### Request-Scoped Dependencies

```
from pyinj import RequestScope

# Current user based on request context
CURRENT_USER = Token[User]("current_user", scope=Scope.REQUEST)

def get_current_user_from_request() -> User:
    # In real app, extract from JWT token, session, etc.
    return User(id=123, name="Alice")

container.register(CURRENT_USER, get_current_user_from_request)

# Middleware for request scope
@app.middleware("http")
async def request_scope_middleware(request, call_next):
    async with container.async_request_scope():
        response = await call_next(request)
    return response

@app.get("/profile")
@inject
async def get_profile(current_user: User) -> dict[str, str]:
    return {"id": str(current_user.id), "name": current_user.name}
```

### Django Integration

#### Global Container Setup

```
# settings.py
from pyinj import Container, Token, Scope, set_default_container

# Global DI container
DI_CONTAINER = Container()
set_default_container(DI_CONTAINER)

# Service registrations
USER_SERVICE = Token[UserService]("user_service", scope=Scope.SINGLETON)
EMAIL_SERVICE = Token[EmailService]("email_service", scope=Scope.SINGLETON)
LOGGER = Token[Logger]("logger", scope=Scope.SINGLETON)

DI_CONTAINER.register(USER_SERVICE, lambda: DjangoUserService())
DI_CONTAINER.register(EMAIL_SERVICE, lambda: DjangoEmailService())
DI_CONTAINER.register(LOGGER, lambda: DjangoLogger())
```

#### Django Views with Injection

```
# views.py
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from pyinj import inject

@csrf_exempt
@inject  # Uses default container
def create_user_view(
    request,
    user_service: UserService,  # Auto-injected
    email_service: EmailService,  # Auto-injected
    logger: Logger  # Auto-injected
) -> JsonResponse:
    if request.method == 'POST':
        user_data = json.loads(request.body)
        logger.info(f"Creating user: {user_data['name']}")

        user = user_service.create_user(user_data)
        email_service.send_welcome_email(user.email)

        return JsonResponse({"user_id": user.id, "status": "created"})

    return JsonResponse({"error": "Method not allowed"}, status=405)

@inject
def user_list_view(
    request,
    user_service: UserService,
    logger: Logger
) -> JsonResponse:
    logger.info("Fetching all users")
    users = user_service.get_all_users()
    return JsonResponse({"users": [{"id": u.id, "name": u.name} for u in users]})
```

#### Django Class-Based Views

```
from django.views import View
from django.http import JsonResponse
from pyinj import inject

class UserView(View):
    @inject
    def get(
        self,
        request,
        user_service: UserService,
        logger: Logger
    ) -> JsonResponse:
        logger.info("GET /users")
        users = user_service.get_all_users()
        return JsonResponse({"users": [u.to_dict() for u in users]})

    @inject  
    def post(
        self,
        request,
        user_service: UserService,
        email_service: EmailService,
        logger: Logger
    ) -> JsonResponse:
        user_data = json.loads(request.body)
        logger.info(f"POST /users - Creating: {user_data['name']}")

        user = user_service.create_user(user_data)
        email_service.send_welcome_email(user.email)

        return JsonResponse(user.to_dict(), status=201)
```

### Flask Integration

```
from flask import Flask, request, jsonify
from pyinj import Container, Token, Scope, inject

app = Flask(__name__)
container = Container()

# Service setup (same as above examples)
USER_SERVICE = Token[UserService]("user_service", scope=Scope.SINGLETON)
container.register(USER_SERVICE, FlaskUserService)

# Request-scoped current user
CURRENT_USER = Token[User]("current_user", scope=Scope.REQUEST)
container.register(CURRENT_USER, get_current_user_from_flask_session)

@app.before_request
def setup_request_scope():
    g.request_scope = container.request_scope()
    g.request_scope.__enter__()

@app.teardown_request
def teardown_request_scope(exception=None):
    if hasattr(g, 'request_scope'):
        g.request_scope.__exit__(None, None, None)

@app.route('/users', methods=['POST'])
@inject(container=container)
def create_user(
    user_service: UserService,
    logger: Logger
) -> dict[str, str]:
    user_data = request.json
    logger.info(f"Creating user: {user_data['name']}")
    user = user_service.create_user(user_data)
    return jsonify(user.to_dict())

@app.route('/profile')
@inject(container=container)
def get_profile(current_user: User) -> dict[str, str]:
    return jsonify(current_user.to_dict())
```

### Click CLI Applications

```
import click
from pyinj import Container, Token, Scope, inject

# Setup container
container = Container()
CONFIG = Token[Config]("config", scope=Scope.SINGLETON)
LOGGER = Token[Logger]("logger", scope=Scope.SINGLETON)
USER_SERVICE = Token[UserService]("user_service", scope=Scope.SINGLETON)

container.register(CONFIG, lambda: Config.from_file("config.yml"))
container.register(LOGGER, lambda: ClickLogger())
container.register(USER_SERVICE, lambda: UserService(
    config=container.get(CONFIG),
    logger=container.get(LOGGER)
))

@click.group()
@click.pass_context
def cli(ctx):
    """CLI application with dependency injection."""
    ctx.obj = container

@cli.command()
@click.argument('name')
@click.option('--email', help='User email address')
@click.pass_context
@inject(container=lambda ctx=None: ctx.obj if ctx else container)
def create_user(
    ctx,
    name: str,
    email: str | None,
    user_service: UserService,
    logger: Logger
) -> None:
    """Create a new user."""
    logger.info(f"Creating user: {name}")
    user_data = {"name": name}
    if email:
        user_data["email"] = email

    user = user_service.create_user(user_data)
    click.echo(f"Created user: {user.id}")

@cli.command()
@click.pass_context
@inject
def list_users(
    ctx,
    user_service: UserService,
    logger: Logger
) -> None:
    """List all users."""
    logger.info("Listing all users")
    users = user_service.get_all_users()

    for user in users:
        click.echo(f"{user.id}: {user.name}")

if __name__ == "__main__":
    cli()
```

## Real-World Usage Patterns

### Microservice Architecture

```
from pyinj import Container, Token, Scope, inject
import httpx
from typing import Protocol

# Service interfaces
class UserServiceClient(Protocol):
    async def get_user(self, user_id: int) -> dict[str, str]: ...
    async def create_user(self, user_data: dict[str, str]) -> dict[str, str]: ...

class NotificationServiceClient(Protocol):
    async def send_notification(self, user_id: int, message: str) -> bool: ...

class OrderService(Protocol):
    async def create_order(self, user_id: int, items: list[dict[str, str]]) -> dict[str, str]: ...

# Implementations
class HTTPUserServiceClient:
    def __init__(self, base_url: str):
        self.client = httpx.AsyncClient(base_url=base_url)

    async def get_user(self, user_id: int) -> dict[str, str]:
        response = await self.client.get(f"/users/{user_id}")
        return response.json()

    async def create_user(self, user_data: dict[str, str]) -> dict[str, str]:
        response = await self.client.post("/users", json=user_data)
        return response.json()

class HTTPNotificationServiceClient:
    def __init__(self, base_url: str):
        self.client = httpx.AsyncClient(base_url=base_url)

    async def send_notification(self, user_id: int, message: str) -> bool:
        response = await self.client.post("/notifications", json={
            "user_id": user_id,
            "message": message
        })
        return response.status_code == 200

class OrderServiceImpl:
    def __init__(self, user_client: UserServiceClient, notification_client: NotificationServiceClient):
        self.user_client = user_client
        self.notification_client = notification_client

    async def create_order(self, user_id: int, items: list[dict[str, str]]) -> dict[str, str]:
        # Verify user exists
        user = await self.user_client.get_user(user_id)

        # Create order (business logic here)
        order = {
            "id": "order_123",
            "user_id": user_id,
            "items": items,
            "total": sum(item["price"] for item in items)
        }

        # Send notification
        await self.notification_client.send_notification(
            user_id,
            f"Order {order['id']} created successfully!"
        )

        return order

# Container setup
container = Container()

# Register service clients
USER_CLIENT = Token[UserServiceClient]("user_client", scope=Scope.SINGLETON)
NOTIFICATION_CLIENT = Token[NotificationServiceClient]("notification_client", scope=Scope.SINGLETON)
ORDER_SERVICE = Token[OrderService]("order_service", scope=Scope.SINGLETON)

container.register(
    USER_CLIENT,
    lambda: HTTPUserServiceClient("https://user-service.internal")
)
container.register(
    NOTIFICATION_CLIENT,
    lambda: HTTPNotificationServiceClient("https://notification-service.internal")
)
container.register(
    ORDER_SERVICE,
    lambda: OrderServiceImpl(
        user_client=container.get(USER_CLIENT),
        notification_client=container.get(NOTIFICATION_CLIENT)
    )
)

# API endpoints
@inject
async def create_order_endpoint(
    user_id: int,
    items: list[dict[str, str]],
    order_service: OrderService
) -> dict[str, str]:
    return await order_service.create_order(user_id, items)
```

### Database Integration Patterns

```
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator
import asyncpg

class DatabasePool:
    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self.pool: asyncpg.Pool | None = None

    async def initialize(self) -> None:
        self.pool = await asyncpg.create_pool(self.connection_string)

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()

    async def execute(self, query: str, *args) -> str:
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetch(self, query: str, *args) -> list[dict[str, str]]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *args)
            return [dict(row) for row in rows]

# Repository pattern with DI
class UserRepository:
    def __init__(self, db: DatabasePool):
        self.db = db

    async def create_user(self, user_data: dict[str, str]) -> dict[str, str]:
        query = "INSERT INTO users (name, email) VALUES ($1, $2) RETURNING id, name, email"
        rows = await self.db.fetch(query, user_data["name"], user_data["email"])
        return rows[0]

    async def get_user(self, user_id: int) -> dict[str, str]:
        query = "SELECT id, name, email FROM users WHERE id = $1"
        rows = await self.db.fetch(query, user_id)
        return rows[0] if rows else None

# Resource management with context managers
@asynccontextmanager
async def database_pool_context() -> AsyncGenerator[DatabasePool, None]:
    pool = DatabasePool("postgresql://localhost/myapp")
    await pool.initialize()
    try:
        yield pool
    finally:
        await pool.close()

# Container setup
container = Container()
DB_POOL = Token[DatabasePool]("db_pool", scope=Scope.SINGLETON)
USER_REPO = Token[UserRepository]("user_repo", scope=Scope.SINGLETON)

container.register_context_async(DB_POOL, database_pool_context)
container.register(USER_REPO, lambda: UserRepository(
    db=container.get(DB_POOL)
))

# Service layer
@inject
async def user_service(
    user_repo: UserRepository,
    logger: Logger
) -> None:
    logger.info("User service started")
    users = await user_repo.get_user(123)
    logger.info(f"Found user: {users}")

# Application lifecycle
async def main() -> None:
    try:
        await user_service()
    finally:
        await container.aclose()  # Clean shutdown

asyncio.run(main())
```

### Testing Patterns with DI

```
import pytest
from unittest.mock import AsyncMock, Mock
from pyinj import Container, Token, Scope

class TestUserService:
    def setup_method(self):
        """Setup for each test."""
        self.container = Container()

        # Define tokens
        self.db_token = Token[Database]("database", scope=Scope.SINGLETON)
        self.email_token = Token[EmailService]("email_service", scope=Scope.SINGLETON)
        self.user_service_token = Token[UserService]("user_service")

        # Register real implementations
        self.container.register(self.db_token, PostgreSQLDatabase)
        self.container.register(self.email_token, SMTPEmailService)
        self.container.register(
            self.user_service_token,
            lambda: UserService(
                db=self.container.get(self.db_token),
                email=self.container.get(self.email_token)
            )
        )

    def test_create_user_success(self):
        """Test user creation with mocked dependencies."""
        # Create mocks
        mock_db = Mock(spec=Database)
        mock_email = Mock(spec=EmailService)

        mock_db.create_user.return_value = {"id": 1, "name": "Alice", "email": "alice@example.com"}
        mock_email.send_welcome_email.return_value = True

        # Override dependencies
        self.container.override(self.db_token, mock_db)
        self.container.override(self.email_token, mock_email)

        # Test
        user_service = self.container.get(self.user_service_token)
        result = user_service.create_user("alice@example.com", "Alice")

        # Assertions
        assert result["id"] == 1
        assert result["name"] == "Alice"
        mock_db.create_user.assert_called_once_with("alice@example.com", "Alice")
        mock_email.send_welcome_email.assert_called_once_with("alice@example.com")

    def test_create_user_database_error(self):
        """Test error handling when database fails."""
        # Create mocks
        mock_db = Mock(spec=Database)
        mock_email = Mock(spec=EmailService)

        mock_db.create_user.side_effect = DatabaseError("Connection failed")

        # Override dependencies
        self.container.override(self.db_token, mock_db)
        self.container.override(self.email_token, mock_email)

        # Test
        user_service = self.container.get(self.user_service_token)

        with pytest.raises(DatabaseError):
            user_service.create_user("alice@example.com", "Alice")

        # Email should not be sent on database error
        mock_email.send_welcome_email.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_user_service(self):
        """Test async service with async mocks."""
        # Create async mocks
        mock_async_db = AsyncMock(spec=AsyncDatabase)
        mock_async_email = AsyncMock(spec=AsyncEmailService)

        mock_async_db.create_user.return_value = {"id": 1, "name": "Alice"}
        mock_async_email.send_welcome_email.return_value = True

        # Register async service
        async_service_token = Token[AsyncUserService]("async_user_service")
        self.container.register(
            async_service_token,
            lambda: AsyncUserService(
                db=mock_async_db,
                email=mock_async_email
            )
        )

        # Test
        service = self.container.get(async_service_token)
        result = await service.create_user("alice@example.com", "Alice")

        # Assertions
        assert result["id"] == 1
        mock_async_db.create_user.assert_called_once()
        mock_async_email.send_welcome_email.assert_called_once()

    def teardown_method(self):
        """Cleanup after each test."""
        self.container.clear_overrides()
```

### Configuration Management

```
from dataclasses import dataclass
from typing import Optional
import os
from pyinj import Container, Token, Scope, inject

@dataclass
class DatabaseConfig:
    host: str
    port: int
    database: str
    username: str
    password: str
    pool_size: int = 10

@dataclass
class RedisConfig:
    host: str
    port: int
    password: Optional[str] = None

@dataclass
class AppConfig:
    debug: bool
    secret_key: str
    database: DatabaseConfig
    redis: RedisConfig

def load_config() -> AppConfig:
    """Load configuration from environment variables."""
    return AppConfig(
        debug=os.getenv("DEBUG", "false").lower() == "true",
        secret_key=os.getenv("SECRET_KEY", "dev-secret"),
        database=DatabaseConfig(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            database=os.getenv("DB_NAME", "myapp"),
            username=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "password")
        ),
        redis=RedisConfig(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            password=os.getenv("REDIS_PASSWORD")
        )
    )

# Container setup
container = Container()
CONFIG = Token[AppConfig]("config", scope=Scope.SINGLETON)
container.register(CONFIG, load_config)

# Services using configuration
@inject
def database_service(config: AppConfig) -> DatabaseService:
    return DatabaseService(
        host=config.database.host,
        port=config.database.port,
        database=config.database.database,
        username=config.database.username,
        password=config.database.password,
        pool_size=config.database.pool_size
    )

@inject
def redis_service(config: AppConfig) -> RedisService:
    return RedisService(
        host=config.redis.host,
        port=config.redis.port,
        password=config.redis.password
    )

# Register services that depend on config
DATABASE_SERVICE = Token[DatabaseService]("database_service", scope=Scope.SINGLETON)
REDIS_SERVICE = Token[RedisService]("redis_service", scope=Scope.SINGLETON)

container.register(DATABASE_SERVICE, database_service)
container.register(REDIS_SERVICE, redis_service)
```

This covers the main usage patterns for PyInj in real-world applications. The key benefits are clean separation of concerns, easy testing with mocks, and type-safe dependency resolution.
