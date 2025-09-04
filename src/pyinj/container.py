"""Enhanced DI Container with all optimizations and features."""

from __future__ import annotations

import asyncio
import threading
from collections import defaultdict, deque
import inspect
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from contextvars import Token as CtxToken
from functools import lru_cache
from itertools import groupby
from types import MappingProxyType, TracebackType
from typing import Any, Mapping, TypeVar, cast

from .contextual import ContextualContainer
from .exceptions import CircularDependencyError, ResolutionError
from .protocols import SupportsAsyncClose, SupportsClose
from .tokens import Scope, Token, TokenFactory
from .types import ProviderAsync, ProviderLike, ProviderSync

__all__ = ["Container", "get_default_container", "set_default_container"]

T = TypeVar("T")
U = TypeVar("U")

# Global default container
_default_container: Container | None = None

# Task-local resolution stack to avoid false circular detection across asyncio tasks
_resolution_stack: ContextVar[tuple[Token[Any], ...]] = ContextVar(
    "pyinj_resolution_stack", default=()
)


def get_default_container() -> Container:
    """Get the global default container."""
    global _default_container
    if _default_container is None:
        _default_container = Container()
    return _default_container


def set_default_container(container: Container) -> None:
    """Set the global default container."""
    global _default_container
    _default_container = container


class Container(ContextualContainer):
    """Ergonomic, type-safe DI container with async support.

    Features:
    - O(1) lookups with a compact registry
    - Thread/async-safe singleton initialization
    - Contextual scoping using ``contextvars`` (request/session)
    - Scala-inspired "given" instances for testability
    - Method chaining for concise setup and batch operations

    Example:
        container = Container()
        LOGGER = Token[Logger]("logger")
        container.register_singleton(LOGGER, ConsoleLogger)

        @inject
        def handler(logger: Inject[Logger]):
            logger.info("hello")
    """

    def __init__(self) -> None:
        """Initialize enhanced container."""
        super().__init__()

        # Token factory for convenient creation
        self.tokens: TokenFactory = TokenFactory()

        # Given instances (Scala-inspired)
        self._given_providers: dict[type[object], ProviderSync[object]] = {}

        # Override less-precise base attributes with typed variants
        self._providers: dict[Token[object], ProviderLike[object]] = {}
        self._token_scopes: dict[Token[object], Scope] = {}
        self._singletons: dict[Token[object], object] = {}
        self._async_locks: dict[Token[object], asyncio.Lock] = {}

        # Performance metrics
        self._resolution_times: deque[float] = deque(maxlen=1000)
        self._cache_hits: int = 0
        self._cache_misses: int = 0

        # Thread safety
        self._lock: threading.RLock = threading.RLock()
        self._singleton_locks: dict[Token[object], threading.Lock] = defaultdict(
            threading.Lock
        )

        # Track dependencies for graph
        self._dependencies: dict[Token[object], set[Token[object]]] = defaultdict(set)

        # Per-context overrides (DI_SPEC requirement)
        self._overrides: ContextVar[dict[Token[object], object] | None] = ContextVar(
            "pyinj_overrides",
            default=None,
        )

        # Resolution stack is tracked via ContextVar (task-local)

    # ============= Internal Helpers (Phase 1) =============

    def _coerce_to_token(self, spec: Token[U] | type[U]) -> Token[U]:
        if isinstance(spec, Token):
            return spec
        if isinstance(spec, type):
            for registered in self._providers:
                if registered.type_ == spec:
                    return cast(Token[U], registered)
            return Token(spec.__name__, spec)
        # Disallow string-based tokens for type safety
        raise TypeError(
            "Token specification must be a Token or type; strings are not supported"
        )

    def _get_override(self, token: Token[U]) -> U | None:
        current = self._overrides.get()
        if current is not None:
            val = current.get(cast(Token[object], token))
            if val is not None:
                return cast(U, val)
        return None

    @contextmanager
    def _resolution_guard(self, token: Token[Any]):
        stack = _resolution_stack.get()
        if token in stack:
            raise CircularDependencyError(token, list(stack))
        reset_token = _resolution_stack.set(stack + (token,))
        try:
            yield
        finally:
            _resolution_stack.reset(reset_token)

    # ============= Registration Methods =============

    def register(
        self,
        token: Token[U] | type[U],
        provider: ProviderLike[U],
        scope: Scope | None = None,
        *,
        tags: tuple[str, ...] = (),
    ) -> "Container":
        """Register a provider for a token.

        Args:
            token: A ``Token[T]`` or a concrete ``type[T]``. If a type is
                provided, a token is created automatically.
            provider: Callable that returns the dependency instance.
            scope: Optional lifecycle override (defaults to token.scope or TRANSIENT).
            tags: Optional tags for discovery/metadata.

        Returns:
            Self, to allow method chaining.

        Example:
            container.register(Token[DB]("db"), create_db, scope=Scope.SINGLETON)
        """
        # Convert to Token if needed
        if isinstance(token, type):
            token = self.tokens.create(
                token.__name__, token, scope=scope or Scope.TRANSIENT, tags=tags
            )
        elif scope is not None:
            # Record desired scope without changing the token identity
            self._token_scopes[cast(Token[object], token)] = scope

        # Validate provider
        if not callable(provider):
            raise TypeError(
                f"Provider must be callable, got {type(provider).__name__}\n"
                f"  Fix: Pass a function or lambda that returns an instance\n"
                f"  Example: container.register(token, lambda: {token.type_.__name__}())"
            )

        with self._lock:
            self._providers[cast(Token[object], token)] = cast(
                ProviderLike[object], provider
            )

        return self  # Enable chaining

    def register_singleton(
        self, token: Token[U] | type[U], provider: ProviderLike[U]
    ) -> "Container":
        """Register a singleton-scoped dependency."""
        return self.register(token, provider, scope=Scope.SINGLETON)

    def register_request(
        self, token: Token[U] | type[U], provider: ProviderLike[U]
    ) -> "Container":
        """Register a request-scoped dependency."""
        return self.register(token, provider, scope=Scope.REQUEST)

    def register_transient(
        self, token: Token[U] | type[U], provider: ProviderLike[U]
    ) -> "Container":
        """Register a transient-scoped dependency."""
        return self.register(token, provider, scope=Scope.TRANSIENT)

    def register_value(self, token: Token[U] | type[U], value: U) -> "Container":
        """Register a pre-created value as a singleton."""
        if isinstance(token, type):
            token = self.tokens.singleton(token.__name__, token)
        # token is now a Token[Any]

        # Store directly as singleton
        self._singletons[cast(Token[object], token)] = value
        return self

    def override(self, token: Token[U], value: U) -> None:
        """Override a dependency with a specific value for this container.

        Prefer the ``use_overrides`` context manager for scoped overrides
        in concurrent test scenarios.
        """
        self._singletons[cast(Token[object], token)] = value

    # ============= Given Instances (Scala-inspired) =============

    def given(self, type_: type[U], provider: ProviderSync[U] | U) -> "Container":
        """Register a given instance for a type (Scala-style)."""
        if callable(provider):
            self._given_providers[type_] = cast(ProviderSync[object], provider)
        else:
            # Wrap value in lambda
            self._given_providers[type_] = lambda p=provider: p

        return self

    def resolve_given(self, type_: type[U]) -> U | None:
        """Resolve a given instance by type."""
        provider = self._given_providers.get(type_)
        if provider:
            return cast(ProviderSync[U], provider)()
        return None

    @contextmanager
    def using(
        self,
        mapping: Mapping[type[object], object] | None = None,
        **givens: object,
    ) -> Iterator[Container]:
        """Temporarily register "given" instances for the current block.

        Supports both an explicit mapping of types to instances and
        keyword arguments that match type names previously registered
        via ``given()``.
        """
        old_givens = self._given_providers.copy()

        # Apply explicit mapping first (precise and type-safe)
        if mapping:
            for t, instance in mapping.items():
                self.given(t, instance)

        # Support kwargs by matching on type name for already-known givens
        if givens:
            known_types = list(self._given_providers.keys())
            for name, instance in givens.items():
                for t in known_types:
                    if getattr(t, "__name__", "") == name:
                        self.given(t, instance)
                        break

        try:
            yield self
        finally:
            self._given_providers = old_givens

    # ============= Resolution Methods =============

    # --- Internal typed helpers to centralize invariance casts ---

    def _obj_token(self, token: Token[U]) -> Token[object]:
        return cast(Token[object], token)

    def _get_provider(self, token: Token[U]) -> ProviderLike[U]:
        obj_token = self._obj_token(token)
        provider = self._providers.get(obj_token)
        if provider is None:
            raise ResolutionError(
                token, [], f"No provider registered for token '{token.name}'"
            )
        return cast(ProviderLike[U], provider)

    def _get_scope(self, token: Token[U]) -> Scope:
        return self._token_scopes.get(self._obj_token(token), token.scope)

    def _get_singleton_cached(self, token: Token[U]) -> U | None:
        obj_token = self._obj_token(token)
        if obj_token in self._singletons:
            return cast(U, self._singletons[obj_token])
        return None

    def _set_singleton_cached(self, token: Token[U], value: U) -> None:
        self._singletons[self._obj_token(token)] = value

    def _ensure_async_lock(self, token: Token[U]) -> asyncio.Lock:
        obj_token = self._obj_token(token)
        lock = self._async_locks.get(obj_token)
        if lock is None:
            lock = asyncio.Lock()
            self._async_locks[obj_token] = lock
        return lock

    def get(self, token: Token[U] | type[U]) -> U:
        """Resolve a dependency synchronously.

        Args:
            token: The ``Token[T]`` or ``type[T]`` to resolve.

        Returns:
            The resolved instance.

        Raises:
            ResolutionError: If no provider is registered or resolution fails.
        """
        # Convert to token if needed and handle givens
        if isinstance(token, type):
            given = self.resolve_given(token)
            if given is not None:
                return given
        token = self._coerce_to_token(token)

        # Check per-context overrides first
        override = self._get_override(token)
        if override is not None:
            self._cache_hits += 1
            return override

        # Check context first
        instance = self.resolve_from_context(token)
        if instance is not None:
            self._cache_hits += 1
            return instance

        self._cache_misses += 1

        with self._resolution_guard(token):
            provider = self._get_provider(token)
            effective_scope = self._get_scope(token)
            if effective_scope == Scope.SINGLETON:
                with self._singleton_locks[self._obj_token(token)]:
                    cached = self._get_singleton_cached(token)
                    if cached is not None:
                        return cached
                    if asyncio.iscoroutinefunction(cast(Callable[..., Any], provider)):
                        raise ResolutionError(
                            token,
                            [],
                            "Provider is async; use aget() for async providers",
                        )
                    instance = cast(ProviderSync[U], provider)()
                    self._validate_and_track(token, instance)
                    self._set_singleton_cached(token, instance)
                    return instance
            else:
                if asyncio.iscoroutinefunction(cast(Callable[..., Any], provider)):
                    raise ResolutionError(
                        token,
                        [],
                        "Provider is async; use aget() for async providers",
                    )
                instance = cast(ProviderSync[U], provider)()
                self._validate_and_track(token, instance)
                self.store_in_context(token, instance)
                return instance

    async def aget(self, token: Token[U] | type[U]) -> U:
        """Resolve a dependency asynchronously.

        Equivalent to :meth:`get` but awaits async providers and uses
        async locks for singleton initialization.
        """
        # Convert to token if needed
        if isinstance(token, type):
            given = self.resolve_given(token)
            if given is not None:
                return given
        token = self._coerce_to_token(token)

        # Check per-context overrides first
        override = self._get_override(token)
        if override is not None:
            self._cache_hits += 1
            return override

        # Check context first
        instance = self.resolve_from_context(token)
        if instance is not None:
            self._cache_hits += 1
            return instance

        self._cache_misses += 1

        with self._resolution_guard(token):
            provider = self._get_provider(token)
            effective_scope = self._get_scope(token)
            if effective_scope == Scope.SINGLETON:
                lock = self._ensure_async_lock(token)
                async with lock:
                    cached = self._get_singleton_cached(token)
                    if cached is not None:
                        return cached

                    if asyncio.iscoroutinefunction(cast(Callable[..., Any], provider)):
                        instance = await cast(ProviderAsync[U], provider)()
                    else:
                        instance = cast(ProviderSync[U], provider)()
                    self._validate_and_track(token, instance)
                    self._set_singleton_cached(token, instance)
                    return instance
            else:
                if asyncio.iscoroutinefunction(cast(Callable[..., Any], provider)):
                    instance = await cast(ProviderAsync[U], provider)()
                else:
                    instance = cast(ProviderSync[U], provider)()
                self._validate_and_track(token, instance)

                self.store_in_context(token, instance)
                return instance

    # ============= Batch Operations =============

    def batch_register(
        self, registrations: list[tuple[Token[object], ProviderLike[object]]]
    ) -> Container:
        """Register multiple dependencies at once."""
        for token, provider in registrations:
            self.register(token, provider)
        return self

    def batch_resolve(self, tokens: list[Token[object]]) -> dict[Token[object], object]:
        """Resolve multiple dependencies efficiently (sync)."""
        sorted_tokens = sorted(tokens, key=lambda t: t.scope.value)
        results: dict[Token[object], object] = {}
        for _scope, group in groupby(sorted_tokens, key=lambda t: t.scope):
            group_list = list(group)
            for tk in group_list:
                results[tk] = self.get(tk)
        return results

    async def batch_resolve_async(
        self, tokens: list[Token[object]]
    ) -> dict[Token[object], object]:
        """Async batch resolution with parallel execution."""
        tasks = {token: self.aget(token) for token in tokens}
        results_list: list[object] = await asyncio.gather(*tasks.values())
        return dict(zip(tasks.keys(), results_list, strict=True))

    # (Provider graph analysis intentionally omitted; can be added behind a feature flag.)

    @lru_cache(maxsize=512)
    def _get_resolution_path(self, token: Token[Any]) -> tuple[Token[Any], ...]:
        """Get resolution path for a token (cached)."""
        return (token,)

    @property
    def cache_hit_rate(self) -> float:
        total = self._cache_hits + self._cache_misses
        return 0.0 if total == 0 else self._cache_hits / total

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_providers": len(self._providers),
            "singletons": len(self._singletons),
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "cache_hit_rate": self.cache_hit_rate,
            "avg_resolution_time": (
                sum(self._resolution_times) / len(self._resolution_times)
                if self._resolution_times
                else 0
            ),
        }

    # ============= Utilities =============

    def get_providers_view(
        self,
    ) -> MappingProxyType[Token[object], ProviderLike[object]]:
        """Return a read-only view of registered providers."""
        return MappingProxyType(self._providers)

    def resources_view(self) -> tuple[SupportsClose | SupportsAsyncClose, ...]:
        """Return a read-only snapshot of tracked resources for tests/inspection."""
        return tuple(self._resources)

    def has(self, token: Token[Any] | type[Any]) -> bool:
        """Return True if the token/type is known to the container."""
        if isinstance(token, type):
            if token in self._given_providers:
                return True
            token = Token(token.__name__, token)
        obj_token = cast(Token[object], token)
        return obj_token in self._providers or obj_token in self._singletons

    def clear(self) -> None:
        """Clear providers, caches, and statistics. Does not affect docs or code."""
        with self._lock:
            self._providers.clear()
            self._singletons.clear()
            self._transients.clear()
            self._given_providers.clear()
            self._dependencies.clear()
            self._cache_hits = 0
            self._cache_misses = 0
            self._resolution_times.clear()
        self.clear_all_contexts()

    def __repr__(self) -> str:
        return (
            "Container("
            f"providers={len(self._providers)}, "
            f"singletons={len(self._singletons)}, "
            f"cache_hit_rate={self.cache_hit_rate:.2%})"
        )

    # ============= Context Managers & Cleanup =============

    def __enter__(self) -> Container:  # pragma: no cover - trivial
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:  # pragma: no cover - trivial
        for resource in reversed(self._resources):
            try:
                # If resource exposes async cleanup, fail fast in sync context
                if hasattr(resource, "aclose") or hasattr(resource, "__aexit__"):
                    raise RuntimeError(
                        f"Resource {type(resource).__name__} requires async cleanup; "
                        f"use 'await container.aclose()' or an async scope"
                    )
                close = getattr(resource, "close", None)
                if close is not None and inspect.iscoroutinefunction(close):
                    raise RuntimeError(
                        f"Resource {type(resource).__name__}.close() is async; "
                        f"use 'await container.aclose()' or an async scope"
                    )
                if close is not None:
                    close()
            except RuntimeError:
                # propagate circuit breaker
                raise
            except Exception:
                # ignore best-effort cleanup errors
                pass

    async def __aenter__(self) -> Container:  # pragma: no cover - trivial
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:  # pragma: no cover - trivial
        tasks: list[asyncio.Future[None] | asyncio.Task[None]] = []
        loop = asyncio.get_running_loop()
        for resource in reversed(self._resources):
            aclose = getattr(resource, "aclose", None)
            if aclose and inspect.iscoroutinefunction(aclose):
                tasks.append(asyncio.create_task(aclose()))
                continue
            aexit = getattr(resource, "__aexit__", None)
            if aexit and inspect.iscoroutinefunction(aexit):
                tasks.append(asyncio.create_task(aexit(None, None, None)))
                continue
            close = getattr(resource, "close", None)
            if close:
                if inspect.iscoroutinefunction(close):
                    tasks.append(asyncio.create_task(close()))
                else:
                    tasks.append(loop.run_in_executor(None, close))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def aclose(self) -> None:
        """Async close: close tracked resources and clear caches."""
        await self.__aexit__(None, None, None)
        self.clear()

    async def dispose(self) -> None:
        """Alias for aclose to align with tests and docs."""
        await self.aclose()

    @contextmanager
    def use_overrides(self, mapping: dict[Token[Any], object]) -> Iterator[None]:
        """Temporarily override tokens for this concurrent context.

        Example:
            with container.use_overrides({LOGGER: fake_logger}):
                svc = container.get(SERVICE)
                ...
        """
        parent = self._overrides.get()
        merged: dict[Token[object], object] = dict(parent) if parent else {}
        merged.update(cast(dict[Token[object], object], mapping))
        token: CtxToken[dict[Token[object], object] | None] = self._overrides.set(
            merged
        )
        try:
            yield
        finally:
            self._overrides.reset(token)

    def clear_overrides(self) -> None:
        """Clear all overrides for the current context."""
        if self._overrides.get() is not None:
            self._overrides.set(None)

    # ============= Validation & Resource Tracking =============

    def _validate_and_track(self, token: Token[Any], instance: object) -> None:
        if not token.validate(instance):
            raise TypeError(
                f"Provider for token '{token.name}' returned {type(instance).__name__}, expected {token.type_.__name__}"
            )
        # Track cleanable resources broadly (protocols or common cleanup methods)
        if (
            isinstance(instance, (SupportsClose, SupportsAsyncClose))
            or hasattr(instance, "aclose")
            or hasattr(instance, "__aexit__")
            or hasattr(instance, "close")
        ):
            self._resources.append(instance)
