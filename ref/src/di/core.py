#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import threading
from collections import defaultdict
from contextlib import asynccontextmanager, suppress
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Generic, Mapping, Protocol, TypeVar

T = TypeVar("T")


class SupportsAclose(Protocol):
    async def aclose(self) -> None: ...


@dataclass(frozen=True, slots=True)
class Token(Generic[T]):
    name: str

    def __repr__(self) -> str:  # pragma: no cover
        return f"Token[{self.name}]"


Provider = Callable[[], T]
AsyncProvider = Callable[[], Awaitable[T]]


class Container:
    """Generic, async-native DI container with ContextVar overrides.

    - Token-typed providers (sync/async)
    - Per-token single-flight for async init
    - Thread-safe sync provider init (DCL)
    - Context-local overrides
    """

    _instance: Container | None = None
    _lock = threading.Lock()

    def __new__(cls) -> Container:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._providers: dict[Token[Any], Provider[Any]] = {}
        self._aproviders: dict[Token[Any], AsyncProvider[Any]] = {}
        self._singletons: dict[Token[Any], Any] = {}

        # Concurrency controls
        self._sync_locks: dict[Token[Any], threading.Lock] = defaultdict(threading.Lock)
        self._async_locks: dict[Token[Any], asyncio.Lock] = defaultdict(asyncio.Lock)
        self._inflight: dict[Token[Any], asyncio.Task[Any]] = {}

        self._overrides: ContextVar[Mapping[Token[Any], Any]] = ContextVar(
            "_di_overrides", default={}
        )
        self._initialized = True

    # Registration
    def register(self, token: Token[T], provider: Provider[T]) -> None:
        self._providers[token] = provider  # type: ignore[assignment]

    def register_async(self, token: Token[T], provider: AsyncProvider[T]) -> None:
        self._aproviders[token] = provider  # type: ignore[assignment]

    # Overrides
    def use_overrides(self, mapping: Mapping[Token[Any], Any]):
        class _CM:
            def __init__(self, outer: Container, new: Mapping[Token[Any], Any]):
                self._outer = outer
                self._new = dict(new)
                self._token = None

            def __enter__(self):
                current = dict(self._outer._overrides.get())
                merged = {**current, **self._new}
                self._token = self._outer._overrides.set(merged)
                return self

            def __exit__(self, *_exc):
                assert self._token is not None
                self._outer._overrides.reset(self._token)

        return _CM(self, mapping)

    def clear_overrides(self) -> None:
        self._overrides.set({})

    # Resolution
    def get(self, token: Token[T]) -> T:
        # Overrides first
        ov = self._overrides.get()
        if token in ov:
            return ov[token]  # type: ignore[return-value]

        # Singleton cache
        if token in self._singletons:
            return self._singletons[token]  # type: ignore[return-value]

        provider = self._providers.get(token)
        if provider is None:
            raise KeyError(f"No provider registered for token '{token.name}'")

        # Guard sync init
        lock = self._sync_locks[token]
        with lock:
            if token in self._singletons:
                return self._singletons[token]  # type: ignore[return-value]
            val = provider()
            self._singletons[token] = val
            return val  # type: ignore[return-value]

    async def aget(self, token: Token[T]) -> T:
        ov = self._overrides.get()
        if token in ov:
            return ov[token]  # type: ignore[return-value]
        if token in self._singletons:
            return self._singletons[token]  # type: ignore[return-value]

        aprov = self._aproviders.get(token)
        if aprov is None:
            return await asyncio.to_thread(self.get, token)

        task = self._inflight.get(token)
        if task is not None:
            return await asyncio.shield(task)  # type: ignore[return-value]

        alock = self._async_locks[token]
        async with alock:
            if token in self._singletons:
                return self._singletons[token]  # type: ignore[return-value]
            task = self._inflight.get(token)
            if task is None:
                task = asyncio.create_task(aprov())
                self._inflight[token] = task

        try:
            result = await asyncio.shield(task)
        except Exception:
            async with alock:
                self._inflight.pop(token, None)
            raise
        else:
            async with alock:
                self._singletons[token] = result
                self._inflight.pop(token, None)
            return result  # type: ignore[return-value]

    async def aclose(self) -> None:
        for obj in list(self._singletons.values()):
            if isinstance(obj, SupportsAclose):  # type: ignore[misc]
                with suppress(Exception):
                    await obj.aclose()
        self._singletons.clear()


class ScopedContainer:
    """Scoped container with isolated cache and override context.

    Falls back to parent providers if not locally registered.
    """

    def __init__(self, parent: Container) -> None:
        self._parent = parent
        self._providers: dict[Token[Any], Provider[Any]] = {}
        self._aproviders: dict[Token[Any], AsyncProvider[Any]] = {}
        self._singletons: dict[Token[Any], Any] = {}
        self._sync_locks: dict[Token[Any], threading.Lock] = defaultdict(threading.Lock)
        self._async_locks: dict[Token[Any], asyncio.Lock] = defaultdict(asyncio.Lock)
        self._inflight: dict[Token[Any], asyncio.Task[Any]] = {}
        self._overrides: ContextVar[Mapping[Token[Any], Any]] = ContextVar(
            "_di_overrides_scoped", default={}
        )

    def register(self, token: Token[T], provider: Provider[T]) -> None:
        self._providers[token] = provider  # type: ignore[assignment]

    def register_async(self, token: Token[T], provider: AsyncProvider[T]) -> None:
        self._aproviders[token] = provider  # type: ignore[assignment]

    def use_overrides(self, mapping: Mapping[Token[Any], Any]):
        class _CM:
            def __init__(self, outer: ScopedContainer, new: Mapping[Token[Any], Any]):
                self._outer = outer
                self._new = dict(new)
                self._tok = None

            def __enter__(self):
                cur = dict(self._outer._overrides.get())
                self._tok = self._outer._overrides.set({**cur, **self._new})
                return self

            def __exit__(self, *_exc):
                assert self._tok is not None
                self._outer._overrides.reset(self._tok)

        return _CM(self, mapping)

    def clear_overrides(self) -> None:
        self._overrides.set({})

    def _resolve(self, token: Token[T]) -> tuple[Provider[T] | None, AsyncProvider[T] | None]:
        p = self._providers.get(token)  # type: ignore[assignment]
        ap = self._aproviders.get(token)  # type: ignore[assignment]
        if p is None and ap is None:
            p = self._parent._providers.get(token)  # type: ignore[attr-defined]
            ap = self._parent._aproviders.get(token)  # type: ignore[attr-defined]
        return p, ap

    def get(self, token: Token[T]) -> T:
        lov = self._overrides.get()
        if token in lov:
            return lov[token]  # type: ignore[return-value]
        pov = self._parent._overrides.get()  # type: ignore[attr-defined]
        if token in pov:
            return pov[token]  # type: ignore[return-value]
        if token in self._singletons:
            return self._singletons[token]  # type: ignore[return-value]
        provider, _ = self._resolve(token)
        if provider is None:
            raise KeyError(f"No provider registered for token '{token.name}'")
        with self._sync_locks[token]:
            if token in self._singletons:
                return self._singletons[token]  # type: ignore[return-value]
            val = provider()
            self._singletons[token] = val
            return val  # type: ignore[return-value]

    async def aget(self, token: Token[T]) -> T:
        lov = self._overrides.get()
        if token in lov:
            return lov[token]  # type: ignore[return-value]
        pov = self._parent._overrides.get()  # type: ignore[attr-defined]
        if token in pov:
            return pov[token]  # type: ignore[return-value]
        if token in self._singletons:
            return self._singletons[token]  # type: ignore[return-value]
        provider, aprovider = self._resolve(token)
        if aprovider is None and provider is None:
            raise KeyError(f"No provider registered for token '{token.name}'")
        if aprovider is None:
            return await asyncio.to_thread(self.get, token)
        task = self._inflight.get(token)
        if task is not None:
            return await asyncio.shield(task)  # type: ignore[return-value]
        alock = self._async_locks[token]
        async with alock:
            if token in self._singletons:
                return self._singletons[token]  # type: ignore[return-value]
            task = self._inflight.get(token)
            if task is None:
                task = asyncio.create_task(aprovider())
                self._inflight[token] = task
        try:
            result = await asyncio.shield(task)
        except Exception:
            async with alock:
                self._inflight.pop(token, None)
            raise
        else:
            async with alock:
                self._singletons[token] = result
                self._inflight.pop(token, None)
            return result  # type: ignore[return-value]

    async def aclose(self) -> None:
        for obj in list(self._singletons.values()):
            if isinstance(obj, SupportsAclose):  # type: ignore[misc]
                with suppress(Exception):
                    await obj.aclose()
        self._singletons.clear()


# Current container context
_current_container: ContextVar[Any] = ContextVar("_current_container", default=None)


def _ensure_current_container() -> Container | ScopedContainer:
    cur = _current_container.get()
    if cur is None:
        root = Container()
        _current_container.set(root)
        return root
    return cur


@asynccontextmanager
async def scoped(parent: Container | None = None):
    base = parent or Container()
    child = ScopedContainer(base)
    tok = _current_container.set(child)
    try:
        yield child
    finally:
        _current_container.reset(tok)
        await child.aclose()


class Depends(Generic[T]):  # type: ignore[misc]
    __slots__ = ("token",)

    def __init__(self, token: Token[T]):
        self.token = token


def depends(token: Token[T]) -> Depends[T]:
    return Depends(token)


def inject(func: Callable[..., Any] | None = None):
    """Decorator to inject params whose default is depends(Token).

    Resolves against the current container context (root or scoped).
    """
    import inspect
    from functools import wraps

    def _decorate(f: Callable[..., Any]):
        sig = inspect.signature(f)
        is_async = inspect.iscoroutinefunction(f)
        params = sig.parameters

        def _prepare_bindings(*args, **kwargs):
            cont = _ensure_current_container()
            bound = sig.bind_partial(*args, **kwargs)
            for name, p in params.items():
                if name not in bound.arguments and isinstance(p.default, Depends):
                    dep: Depends[Any] = p.default
                    val = cont.get(dep.token)
                    bound.arguments[name] = val
            return bound

        if is_async:
            @wraps(f)
            async def _awrapper(*args, **kwargs):
                bound = _prepare_bindings(*args, **kwargs)
                return await f(*bound.args, **bound.kwargs)
            return _awrapper
        else:
            @wraps(f)
            def _wrapper(*args, **kwargs):
                bound = _prepare_bindings(*args, **kwargs)
                return f(*bound.args, **bound.kwargs)
            return _wrapper

    return _decorate(func) if func is not None else _decorate
