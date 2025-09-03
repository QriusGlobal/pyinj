# Concurrency

PyInj is designed for both threaded and async-concurrent programs.

- Thread-safe singletons: first creation is protected by locks.
- Async-safe singletons: first creation is protected by `asyncio.Lock`.
- Request/session scoping: implemented with `contextvars`, so context flows across awaits.
- Overrides: per-request overrides backed by `ContextVar` for isolation.

## Threaded programs

```python
from pyinj import Container, Token, Scope
import threading

container = Container()
CACHE = Token[dict[str, str]]("cache", scope=Scope.SINGLETON)
container.register(CACHE, lambda: {"a": "1"})

# Safe: every thread gets the same singleton
values: list[dict[str, str]] = []

def worker() -> None:
    values.append(container.get(CACHE))

threads = [threading.Thread(target=worker) for _ in range(10)]
[t.start() for t in threads]
[t.join() for t in threads]
assert all(v is values[0] for v in values)
```

## Async programs

```python
import asyncio
from typing import Awaitable
from pyinj import Container, Token, Scope

container = Container()

class Client:
    async def aclose(self) -> None: ...

CLIENT = Token[Client]("client", scope=Scope.SINGLETON)

async def make_client() -> Client:
    await asyncio.sleep(0)  # simulate I/O
    return Client()

container.register(CLIENT, make_client)

async def main() -> None:
    # Safe: async singleton is created once under an asyncio.Lock
    c1, c2 = await asyncio.gather(container.aget(CLIENT), container.aget(CLIENT))
    assert c1 is c2

asyncio.run(main())
```

## Request / session scope (web-style lifetimes)

```python
from typing import Any
from pyinj import Container, Token, Scope

container = Container()
SESSION = Token[dict[str, Any]]("session", scope=Scope.SESSION)
REQUEST = Token[dict[str, Any]]("request", scope=Scope.REQUEST)

container.register(SESSION, lambda: {"s": 1})
container.register(REQUEST, lambda: {"r": 1})

# Request scope isolates per-request caches while sharing singletons
with container.request_scope():
    assert container.get(REQUEST)["r"] == 1
    with container.request_scope():
        assert container.get(REQUEST)["r"] == 1  # new dict in inner scope
```

## Overrides per request

```python
from typing import Any

LOGGER = Token[object]("logger")
container.register(LOGGER, lambda: object())

with container.use_overrides({LOGGER: "fake"}):
    assert container.get(LOGGER) == "fake"
# Outside override, original provider is used
assert container.get(LOGGER) != "fake"
```

## Cleanup

Any object that implements `close()` or `aclose()` is tracked and cleaned up by `dispose()` / `aclose()`.

```python
await container.dispose()  # closes async resources and clears caches
```

