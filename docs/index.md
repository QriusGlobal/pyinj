# PyInj

> Type-safe dependency injection for Python 3.13+
>
> Status: Beta — Active development; breaking changes may occur between pre-releases. Pin exact versions in production.

PyInj is a minimal, type-safe DI container focused on clarity and performance:

- Thread-safe and async-safe resolution
- O(1) lookups and cached injection metadata
- Circular dependency detection and safe cleanup
- Protocol-based type safety and auto-registration via metaclass
- Zero runtime dependencies

## Quick Install

```bash
# uv (recommended)
uv add pyinj

# or pip
pip install pyinj
```

## Quick Start

```python
from pyinj import Container, Token, Scope

container = Container()

DB_TOKEN = Token[Database]("database")
container.register(DB_TOKEN, create_database, Scope.SINGLETON)

db = container.get(DB_TOKEN)
await container.dispose()
```

Continue with Getting Started for basic patterns and Usage for type-safe injection, metaclass auto-registration, and async lifecycles.

