# PyInj - Type-Safe Dependency Injection

[![Python Version](https://img.shields.io/badge/python-3.13+-blue.svg)](https://python.org)
[![Type Checked](https://img.shields.io/badge/type--checked-basedpyright-blue.svg)](https://github.com/DetachHead/basedpyright)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docs](https://img.shields.io/badge/docs-mkdocs--material-informational)](https://qriusglobal.github.io/pyinj/)

> Status: Stable — Actively maintained. Breaking changes follow semantic versioning.

## Stability

- Beta quality: APIs are stabilizing and may change.
- Expect breaking changes between pre-releases (a/b/rc).
- Pin exact versions if needed in production, e.g. `pyinj==1.0.1b1`.
- Review release notes before upgrading.

A **type-safe** dependency injection container for Python 3.13+ that provides:

- 🚀 **Thread-safe and async-safe** resolution (ContextVar-based; no cross-talk)  
- ⚡ **O(1) performance** for type lookups
- 🔍 **Circular dependency detection**
- 🧹 **Automatic resource cleanup**
- 🛡️ **Protocol-based type safety**
- 🏭 **Metaclass auto-registration**
- 📦 **Zero external dependencies**

## Documentation

Full docs: https://qriusglobal.github.io/pyinj/

## Quick Start

```bash
# Install with UV (recommended)
uv add pyinj

# Or with pip
pip install pyinj
```

```python
from pyinj import Container, Token, Scope

# Create container
container = Container()

# Define token
DB_TOKEN = Token[Database]("database")

# Register provider
container.register(DB_TOKEN, create_database, Scope.SINGLETON)

# Resolve dependency
db = container.get(DB_TOKEN)

# Cleanup
await container.dispose()
```

## Why PyInj?

**Traditional DI libraries are over-engineered:**
- 20,000+ lines of code for simple dependency injection
- Heavy frameworks with steep learning curves  
- Poor async support and race conditions
- Memory leaks and thread safety issues

**PyInj is different:**
- ~200 lines of pure Python - easy to understand and debug
- Designed specifically for Python 3.13+ with no-GIL support
- Production-focused design patterns; currently stabilizing in beta
- Can be vendored directly or installed as a package

## Core Features

### 1. Type-Safe Dependencies

```python
from typing import Protocol, runtime_checkable
from pyinj import Container, Token

@runtime_checkable
class Logger(Protocol):
    def info(self, message: str) -> None: ...

class ConsoleLogger:
    def info(self, message: str) -> None:
        print(f"INFO: {message}")

container = Container()
logger_token = Token[Logger]("logger", protocol=Logger)
container.register(logger_token, ConsoleLogger, Scope.SINGLETON)

# Type-safe resolution
logger = container.get(logger_token)  # Type: Logger
logger.info("Hello, World!")
```

### 2. Automatic Dependency Injection

```python
from pyinj import Injectable

class EmailService(metaclass=Injectable):
    __injectable__ = True
    __token_name__ = "email_service" 
    __scope__ = Scope.SINGLETON
    
    def __init__(self, logger: Logger):
        self.logger = logger
    
    def send_email(self, to: str, subject: str) -> None:
        self.logger.info(f"Sending email to {to}")

# Automatically registered and dependencies resolved!
email_service = container.get(Injectable.get_registry()[EmailService])
```

### 3. Async-Safe with Proper Cleanup

```python
class DatabaseConnection:
    async def connect(self) -> None:
        print("Connecting to database...")
    
    async def aclose(self) -> None:
        print("Closing database connection...")

container.register(
    Token[DatabaseConnection]("db"), 
    DatabaseConnection, 
    Scope.SINGLETON
)

# Async resolution
db = await container.aget(Token[DatabaseConnection]("db"))
await db.connect()

# Automatic cleanup
await container.dispose()  # Safely closes all resources

### Circuit-Breaker Cleanup (New)

To prevent subtle leaks, PyInj enforces async cleanup for async-only resources.
Attempting to use synchronous cleanup with such a resource raises a
semantically-typed exception:

```python
from pyinj import Container, Token, Scope
from pyinj.exceptions import AsyncCleanupRequiredError
from httpx import AsyncClient

container = Container()
client_token = Token[AsyncClient]("client", scope=Scope.SINGLETON)

from contextlib import asynccontextmanager

@asynccontextmanager
async def client_cm():
    client = AsyncClient()
    try:
        yield client
    finally:
        await client.aclose()

container.register_context(client_token, lambda: client_cm(), is_async=True)
_ = await container.aget(client_token)

# This will raise AsyncCleanupRequiredError
try:
    with container:
        pass
except AsyncCleanupRequiredError:
    ...

# Use async cleanup instead
await container.aclose()
```

Container-level cleanup manages resources registered via `register_context_sync/async` (or `register_context(..., is_async=...)`) and
closes them in LIFO order. Request/session scopes also clean up resources stored
in the scope when the scope exits.

Typed registration helpers:

```python
from contextlib import contextmanager, asynccontextmanager
from collections.abc import Generator, AsyncGenerator

# Sync context manager
@contextmanager
def db_cm() -> Generator[DatabaseConnection, None, None]:
    db = DatabaseConnection()
    try:
        yield db
    finally:
        db.close()

container.register_context_sync(Token("db", DatabaseConnection, scope=Scope.SINGLETON), lambda: db_cm())

# Async context manager
@asynccontextmanager
async def client_cm() -> AsyncGenerator[AsyncClient, None]:
    client = AsyncClient()
    try:
        yield client
    finally:
        await client.aclose()

container.register_context_async(Token("client", AsyncClient, scope=Scope.SINGLETON), lambda: client_cm())
```

Fail-fast behavior: if a provider raises during setup/enter (`__enter__`/`__aenter__`), the exception propagates to the resolver so the failure is explicit and debuggable.
```

### 4. Testing Made Easy

```python
# Production setup
container.register(logger_token, ConsoleLogger)

# Test override
test_logger = Mock(spec=Logger)
container.override(logger_token, test_logger)

# Test your code
service = container.get(service_token)
service.do_something()

# Verify interactions
test_logger.info.assert_called_with("Expected message")

# Cleanup
container.clear_overrides()
```

## Advanced Usage

### Protocol-Based Resolution

```python
# Resolve by protocol instead of token
from pyinj import inject

@inject
def business_logic(logger: Logger, db: Database) -> str:
    logger.info("Processing business logic")
    return db.query("SELECT * FROM users")

# Dependencies automatically injected based on type hints
result = business_logic()

### Plain Type Injection

Annotate parameters with concrete types and use `@inject` to resolve them.
Builtins like `str`/`int` are ignored to avoid surprises.

```python
@inject
def process(logger: Logger, db: Database) -> None:
    logger.info("processing"); db.connect()
```
```

### Multiple Scopes

```python
from pyinj import Scope

# Singleton - one instance per container
container.register(config_token, load_config, Scope.SINGLETON)

# Transient - new instance every time  
container.register(request_token, create_request, Scope.TRANSIENT)

# Request/Session - scoped to request/session context
container.register(user_token, get_current_user, Scope.REQUEST)
```

### Async Patterns

```python
# Async providers
async def create_async_service() -> AsyncService:
    service = AsyncService()
    await service.initialize()
    return service

container.register(service_token, create_async_service, Scope.SINGLETON)

# Concurrent resolution with race condition protection
results = await asyncio.gather(*[
    container.aget(service_token) for _ in range(100)
])

# All results are the same instance (singleton)
assert all(r is results[0] for r in results)
```

## Performance

PyInj is optimized for production workloads:

- **O(1) type lookups** - Constant time resolution regardless of container size
- **Cached injection metadata** - Function signatures parsed once at decoration time  
- **Lock-free fast paths** - Singletons use double-checked locking pattern
- **Memory efficient** - Minimal overhead per registered dependency

```python
# Benchmark: 1000 services registered
# Resolution time: ~0.0001ms (O(1) guaranteed)
# Memory overhead: ~500 bytes per service
```

## Framework Integration

### FastAPI

```python
from fastapi import FastAPI, Depends
from pyinj import Container

app = FastAPI()
container = Container()

def get_service(container: Container = Depends(lambda: container)) -> MyService:
    return container.get(service_token)

@app.post("/users")
async def create_user(service: MyService = Depends(get_service)):
    return await service.create_user()
```

### Django/Flask

```python
# Django settings.py
from pyinj import Container

# Global container
DI_CONTAINER = Container()

# In views
def my_view(request):
    service = DI_CONTAINER.get(service_token)
    return service.handle_request(request)
```

### CLI Applications

```python
import click
from pyinj import Container

@click.command()
@click.pass_context
def cli(ctx):
    ctx.obj = Container()
    # Register services...

@cli.command()
@click.pass_context  
def process(ctx):
    container = ctx.obj
    service = container.get(service_token)
    service.process()
```

## Error Handling

PyInj provides clear, actionable error messages:

```python
# Circular dependency detection
Container Error: Cannot resolve token 'service_a':
  Resolution chain: service_a -> service_b -> service_a
  Cause: Circular dependency detected

# Missing provider
Container Error: Cannot resolve token 'missing_service':
  Resolution chain: root
  Cause: No provider registered for token 'missing_service'

# Type validation failure  
Container Error: Provider for token 'logger' returned <Mock>, expected <Logger>
```

## Migration Guide

### From dependency-injector

```python
# Before (dependency-injector)
from dependency_injector import containers, providers

class Container(containers.DeclarativeContainer):
    config = providers.Configuration()
    logger = providers.Singleton(Logger)

# After (PyInj)
from pyinj import Container, Token, Scope

container = Container()
logger_token = Token[Logger]("logger")
container.register(logger_token, Logger, Scope.SINGLETON)
```

### From injector

```python
# Before (injector)  
from injector import Injector, inject, singleton

injector = Injector()
injector.binder.bind(Logger, to=ConsoleLogger, scope=singleton)

@inject
def my_function(logger: Logger) -> None: ...

# After (PyInj)
container = Container()
container.register(Token[Logger]("logger"), ConsoleLogger, Scope.SINGLETON)

@container.inject
def my_function(logger: Logger) -> None: ...
```

## Development

```bash
# Clone repository
git clone <repo-url>
cd pyinj

# Install dependencies  
uv sync

# Run tests
uv run pytest -q

# Type checking
uvx basedpyright src

# Format code
uvx ruff format .

# Run all quality checks
uvx ruff check . && uvx basedpyright src && uv run pytest -q
```

## Release Process

- Versioning: follow SemVer. Use pre-release tags (a, b, rc) while in beta; e.g. `1.0.1b1`.
- Classifiers: set an appropriate development status (e.g., "Development Status :: 4 - Beta").
- Build locally with uv:
  - `rm -rf dist`
  - `uv build`
- Publish to PyPI with uv:
  - `uv publish --token "$PYPI_API_TOKEN"`
- CI/CD:
  - GitHub Actions runs tests with uv on PRs/commits.
  - Releases are built/published via `.github/workflows/publish.yml` using uv.
- Yanking incorrect releases:
  - PyPI does not support API/CLI yanking; use the project release UI to “Yank this release”.
  - You cannot overwrite or reuse a version once uploaded.

### Current Release Notes (maintainer summary)

- Removed string-based tokens; only `Token` or `type` are supported.
- Extracted and delegated scope orchestration to `ScopeManager`.
- Finalized `InjectionAnalyzer` plan usage in decorators.
- Strengthened typing with `Resolvable` protocol for resolution functions.
- Tests updated to avoid strings and expect typed errors.
- Packaging: moved `py.typed` into `src/pyinj/` and ensured inclusion in wheels/sdists.
- Version and metadata updated; CI and PyPI publish workflows added using uv.

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make changes with tests
4. Ensure all quality checks pass
5. Submit a pull request

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Why "PyInj"?

**Py** - Python-first design for modern Python 3.13+  
**Inj** - Injection (Dependency Injection)

PyInj follows the philosophy that **good software is simple software**. We provide exactly what you need for dependency injection - nothing more, nothing less.

---

**Ready to simplify your Python dependency injection?**

```bash
uv add pyinj
```
