# Getting Started

## Installation

```bash
uv add pyinj
# or
pip install pyinj
```

## Basic Concepts

- Token: a typed identifier for a dependency.
- Provider: a function or class that creates the dependency.
- Scope: lifecycle (SINGLETON, TRANSIENT, REQUEST).

## Example

```python
from pyinj import Container, Token, Scope

container = Container()
LOGGER = Token[Logger]("logger")

container.register(LOGGER, ConsoleLogger, Scope.SINGLETON)

logger = container.get(LOGGER)
logger.info("Hello")
```

## Cleanup

Call `dispose()` to close resources (async-friendly):

```python
await container.dispose()
```

