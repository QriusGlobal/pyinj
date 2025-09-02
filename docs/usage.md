# Usage

## Type-Safe Dependencies

```python
from typing import Protocol, runtime_checkable
from pyinj import Container, Token, Scope

@runtime_checkable
class Logger(Protocol):
    def info(self, message: str) -> None: ...

class ConsoleLogger:
    def info(self, message: str) -> None:
        print(message)

container = Container()
logger_token = Token[Logger]("logger", protocol=Logger)
container.register(logger_token, ConsoleLogger, Scope.SINGLETON)

logger = container.get(logger_token)  # Type: Logger
```

## Auto-Registration (metaclass)

```python
from pyinj import Injectable

class EmailService(metaclass=Injectable):
    __injectable__ = True
    __token_name__ = "email_service"
    __scope__ = Scope.SINGLETON
    def __init__(self, logger: Logger):
        self.logger = logger
```

## Async Providers and Cleanup

```python
class DatabaseConnection:
    async def aclose(self) -> None: ...

DB = Token[DatabaseConnection]("db")
container.register(DB, DatabaseConnection, Scope.SINGLETON)

conn = await container.aget(DB)
await container.dispose()
```

