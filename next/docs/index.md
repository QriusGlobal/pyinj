# PyInj

[ ](https://github.com/QriusGlobal/pyinj/edit/master/docs/index.md "Edit this page")

# PyInj - Type-Safe Dependency Injection¶

> **Status:** Stable — Actively maintained. Breaking changes follow semantic versioning.

A **type-safe** dependency injection container for Python 3.13+ that provides:

  * 🚀 **Thread-safe and async-safe** resolution (ContextVar-based; no cross-talk) 
  * ⚡ **O(1) performance** for type lookups with pre-computed hash tokens
  * 🔍 **Circular dependency detection** with detailed error chains
  * 🧹 **Automatic resource cleanup** (LIFO order with proper async support)
  * 🛡️ **Protocol-based type safety** with full static type checking
  * 🏭 **Metaclass auto-registration** for declarative DI patterns
  * 📦 **Zero external dependencies** \- pure Python implementation
  * 🎯 **PEP 561 compliant** with `py.typed` for mypy/basedpyright support

## Quick Install¶
    
    
    # Install with UV (recommended)
    uv add pyinj
    
    # Or with pip
    pip install pyinj
    

## Quick Start¶
    
    
    from typing import Protocol
    from pyinj import Container, Token, Scope, inject
    
    # Define interfaces
    class Logger(Protocol):
        def info(self, message: str) -> None: ...
    
    class Database(Protocol):
        def query(self, sql: str) -> list[dict[str, str]]: ...
    
    # Implementations
    class ConsoleLogger:
        def info(self, message: str) -> None:
            print(f"INFO: {message}")
    
    class PostgreSQLDatabase:
        def query(self, sql: str) -> list[dict[str, str]]:
            return [{"result": "data"}]
    
    # Create container and tokens
    container = Container()
    LOGGER = Token[Logger]("logger", scope=Scope.SINGLETON)
    DATABASE = Token[Database]("database", scope=Scope.SINGLETON)
    
    # Register providers
    container.register(LOGGER, ConsoleLogger)
    container.register(DATABASE, PostgreSQLDatabase)
    
    # Use with @inject decorator (recommended)
    @inject
    def process_users(logger: Logger, db: Database) -> None:
        """Dependencies injected automatically via type annotations."""
        logger.info("Processing users")
        users = db.query("SELECT * FROM users")
        logger.info(f"Found {len(users)} users")
    
    # Call without arguments - dependencies auto-resolved
    process_users()
    

## Why PyInj?¶

**Traditional DI libraries are over-engineered:** \- 20,000+ lines of code for simple dependency injection \- Heavy frameworks with steep learning curves  
\- Poor async support and race conditions \- Memory leaks and thread safety issues

**PyInj is different:** \- ~200 lines of pure Python - easy to understand and debug \- Designed specifically for Python 3.13+ with no-GIL support \- Production-focused design patterns; stable and ready for production \- Can be vendored directly or installed as a package

## Core Features¶

### Type-Safe Injection Patterns¶

PyInj provides clear guidance on injection patterns to prevent common mistakes:

#### ⭐ Recommended: Plain Type Annotations¶
    
    
    @inject  # Uses default container
    def business_logic(logger: Logger, db: Database, user_id: int) -> None:
        """
        ✅ RECOMMENDED PATTERN:
        - Clean type annotations 
        - Automatic dependency resolution
        - Mixed injected/regular parameters
        """
        logger.info(f"Processing user {user_id}")
        db.query("SELECT * FROM users WHERE id = ?", user_id)
    

#### ❌ Anti-Patterns to Avoid¶
    
    
    # ❌ WRONG - Don't do this!
    def bad_handler(logger: Inject[Logger] = None) -> None:
        # This breaks type safety and static analysis
        pass
    

### Full Static Type Checking¶

PyInj includes a `py.typed` marker file and works with all type checkers:
    
    
    # Works with all type checkers
    mypy your_code.py
    basedpyright your_code.py
    pyright your_code.py
    

### Contextual Scoping¶
    
    
    # Request scope - each request gets isolated dependencies
    with container.request_scope():
        user = container.get(USER_TOKEN)
        # user is scoped to this request
    
    # Session scope - longer-lived than request
    with container.session_scope():
        session = container.get(SESSION_TOKEN)
        # session persists across multiple requests
    

### Async-Safe Resource Management¶
    
    
    # Async context manager with automatic cleanup
    @asynccontextmanager
    async def database_connection():
        client = AsyncDatabaseClient()
        try:
            yield client
        finally:
            await client.aclose()
    
    container.register_context_async(DB_TOKEN, database_connection)
    
    # Automatic cleanup in LIFO order
    await container.aclose()
    

## Framework Integration¶

PyInj integrates seamlessly with popular Python frameworks:

  * **FastAPI** : Both FastAPI-style and PyInj-style injection
  * **Django** : Global container with automatic injection
  * **Flask** : Request-scoped dependencies
  * **Click** : CLI applications with DI

## Performance¶

PyInj is optimized for production workloads:

  * **O(1) type lookups** \- Constant time resolution regardless of container size
  * **Cached injection metadata** \- Function signatures parsed once at decoration time 
  * **Lock-free fast paths** \- Singletons use double-checked locking pattern
  * **Memory efficient** \- Minimal overhead per registered dependency

## Getting Started¶

Ready to build type-safe applications? Continue with:

  * **[Getting Started](getting-started/)** \- Basic patterns and setup
  * **[Type Safety](type-safety/)** \- Static type checking and PEP 561 compliance
  * **[Usage](usage/)** \- Framework integration and real-world examples
  * **[Advanced](advanced/)** \- Complex patterns and performance optimization
  * **[API Reference](api/)** \- Complete API documentation

* * *

**Ready to simplify your Python dependency injection?**
    
    
    uv add pyinj