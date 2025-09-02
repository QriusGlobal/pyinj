"""Enhanced DI Container with all optimizations and features."""

from __future__ import annotations

import asyncio
import threading
from collections import defaultdict, deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from contextvars import Token as CtxToken
from functools import lru_cache
from itertools import groupby
from types import MappingProxyType
from typing import Any, TypeVar, cast

from .contextual import ContextualContainer
from .tokens import Scope, Token, TokenFactory
from .protocols import SupportsAsyncClose, SupportsClose
from .exceptions import CircularDependencyError, ResolutionError

__all__ = ["Container", "get_default_container", "set_default_container"]

T = TypeVar("T")
# Simpler provider alias to keep types concrete for static analysis
Provider = Callable[[], Any]

# Global default container
_default_container: Container | None = None


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
    """Ergonomic, type‑safe DI container with async support.

    Features:
    - O(1) lookups with a compact registry
    - Thread/async‑safe singleton initialization
    - Contextual scoping using ``contextvars`` (request/session)
    - Scala‑inspired "given" instances for testability
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
        self._given_providers: dict[type[Any], Provider] = {}

        # Override less-precise base attributes with typed variants
        self._providers: dict[Token[Any], Provider] = {}
        self._singletons: dict[Token[Any], Any] = {}
        self._async_locks: dict[Token[Any], asyncio.Lock] = {}

        # Performance metrics
        self._resolution_times: deque[float] = deque(maxlen=1000)
        self._cache_hits: int = 0
        self._cache_misses: int = 0

        # Thread safety
        self._lock: threading.RLock = threading.RLock()
        self._singleton_locks: dict[Token[Any], threading.Lock] = defaultdict(threading.Lock)

        # Track dependencies for graph
        self._dependencies: dict[Token[Any], set[Token[Any]]] = defaultdict(set)

        # Per-context overrides (DI_SPEC requirement)
        self._overrides: ContextVar[dict[Token[Any], Any] | None] = ContextVar(
            "pyinj_overrides",
            default=None,
        )

        # Thread-local resolution tracking for cycle detection
        self._local = threading.local()

    # ============= Internal Helpers (Phase 1) =============

    def _coerce_to_token(self, spec: Token[Any] | type[Any]) -> Token[Any]:
        if isinstance(spec, Token):
            return spec
        if isinstance(spec, type):
            for registered in self._providers:
                if registered.type_ == spec:
                    return registered
            return Token(spec.__name__, spec)
        # Disallow string-based tokens for type safety
        raise TypeError("Token specification must be a Token or type; strings are not supported")

    def _get_override(self, token: Token[Any]) -> Any | None:
        current = self._overrides.get()
        if current and token in current:
            return current[token]
        return None

    def _resolution_stack(self) -> list[Token[Any]]:
        stack = getattr(self._local, "resolving", None)
        if not isinstance(stack, list):
            new_stack: list[Token[Any]] = []
            setattr(self._local, "resolving", new_stack)
            return new_stack
        return cast(list[Token[Any]], stack)

    @contextmanager
    def _resolution_guard(self, token: Token[Any]):
        stack = self._resolution_stack()
        if token in stack:
            raise CircularDependencyError(token, list(stack))
        stack.append(token)
        try:
            yield
        finally:
            stack.pop()

    # ============= Registration Methods =============

    def register(
        self,
        token: Token[Any] | type[Any],
        provider: Provider,
        *,
        scope: Scope | None = None,
        tags: tuple[str, ...] = (),
    ) -> Container:
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
            token = token.with_scope(scope)

        # Validate provider
        if not callable(provider):
            raise TypeError(
                f"Provider must be callable, got {type(provider).__name__}\n"
                f"  Fix: Pass a function or lambda that returns an instance\n"
                f"  Example: container.register(token, lambda: {token.type_.__name__}())"
            )

        with self._lock:
            self._providers[token] = provider

        return self  # Enable chaining

    def register_singleton(self, token: Token[Any] | type[Any], provider: Provider) -> Container:
        """Register a singleton‑scoped dependency."""
        return self.register(token, provider, scope=Scope.SINGLETON)

    def register_request(self, token: Token[Any] | type[Any], provider: Provider) -> Container:
        """Register a request‑scoped dependency."""
        return self.register(token, provider, scope=Scope.REQUEST)

    def register_transient(self, token: Token[Any] | type[Any], provider: Provider) -> Container:
        """Register a transient‑scoped dependency."""
        return self.register(token, provider, scope=Scope.TRANSIENT)

    def register_value(self, token: Token[Any] | type[Any], value: Any) -> Container:
        """Register a pre‑created value as a singleton."""
        if isinstance(token, type):
            token = self.tokens.singleton(token.__name__, token)
        # token is now a Token[Any]

        # Store directly as singleton
        self._singletons[token] = value
        return self

    def override(self, token: Token[Any], value: Any) -> None:
        """Override a dependency with a specific value for this container.

        Prefer the ``use_overrides`` context manager for scoped overrides
        in concurrent test scenarios.
        """
        self._singletons[token] = value

    # ============= Given Instances (Scala-inspired) =============

    def given(self, type_: type[Any], provider: Provider | Any) -> Container:
        """Register a given instance for a type (Scala-style)."""
        if callable(provider):
            self._given_providers[type_] = provider
        else:
            # Wrap value in lambda
            self._given_providers[type_] = lambda p=provider: p

        return self

    def resolve_given(self, type_: type[T]) -> T | None:
        """Resolve a given instance by type."""
        provider = self._given_providers.get(type_)
        if provider:
            return provider()
        return None

    @contextmanager
    def using(self, **givens: Any) -> Iterator[Container]:
        """Scala-style using clause for temporary givens."""
        old_givens = self._given_providers.copy()

        # Add temporary givens
        for type_name, instance in givens.items():
            if isinstance(type_name, type):
                self.given(type_name, instance)

        try:
            yield self
        finally:
            self._given_providers = old_givens

    # ============= Resolution Methods =============

    def get(self, token: Token[Any] | type[Any]) -> Any:
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
            # Get provider
            provider = self._providers.get(token)
            if provider is None:
                raise ResolutionError(token, [], f"No provider registered for token '{token.name}'")

            # Create instance based on scope
            if token.scope == Scope.SINGLETON:
                with self._singleton_locks[token]:
                    if token in self._singletons:
                        return self._singletons[token]
                    instance = provider()
                    self._validate_and_track(token, instance)
                    self._singletons[token] = instance
                    return instance
            else:
                instance = provider()
                self._validate_and_track(token, instance)
                self.store_in_context(token, instance)
                return instance
        

    async def aget(self, token: Token[Any] | type[Any]) -> Any:
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
            # Get provider
            provider = self._providers.get(token)
            if provider is None:
                raise ResolutionError(token, [], f"No provider registered for token '{token.name}'")

            # Create instance based on scope
            if token.scope == Scope.SINGLETON:
                # Ensure async lock exists
                if token not in self._async_locks:
                    self._async_locks[token] = asyncio.Lock()

                async with self._async_locks[token]:
                    if token in self._singletons:
                        return self._singletons[token]

                    if asyncio.iscoroutinefunction(provider):
                        instance = await provider()
                    else:
                        instance = provider()
                    self._validate_and_track(token, instance)

                    self._singletons[token] = instance
                    return instance
            else:
                if asyncio.iscoroutinefunction(provider):
                    instance = await provider()
                else:
                    instance = provider()
                self._validate_and_track(token, instance)

                self.store_in_context(token, instance)
                return instance
        

    # ============= Batch Operations =============

    def batch_register(self, registrations: list[tuple[Token[Any], Provider]]) -> Container:
        """Register multiple dependencies at once."""
        for token, provider in registrations:
            self.register(token, provider)
        return self

    def batch_resolve(self, tokens: list[Token[Any]]) -> dict[Token[Any], Any]:
        """Resolve multiple dependencies efficiently (sync)."""
        sorted_tokens = sorted(tokens, key=lambda t: t.scope.value)
        results: dict[Token[Any], Any] = {}
        for _scope, group in groupby(sorted_tokens, key=lambda t: t.scope):
            group_list = list(group)
            for tk in group_list:
                results[tk] = self.get(tk)
        return results

    async def batch_resolve_async(self, tokens: list[Token[Any]]) -> dict[Token[Any], Any]:
        """Async batch resolution with parallel execution."""
        tasks = {token: self.aget(token) for token in tokens}
        results_list: list[Any] = await asyncio.gather(*tasks.values())
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

    def get_providers_view(self) -> MappingProxyType:
        """Return a read‑only view of registered providers."""
        return MappingProxyType(self._providers)

    def has(self, token: Token[Any] | type[Any]) -> bool:
        """Return True if the token/type is known to the container."""
        if isinstance(token, type):
            if token in self._given_providers:
                return True
            token = Token(token.__name__, token)
        return token in self._providers or token in self._singletons

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

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # pragma: no cover - trivial
        for resource in reversed(self._resources):
            try:
                if hasattr(resource, "close"):
                    resource.close()
            except Exception:
                pass

    async def __aenter__(self) -> Container:  # pragma: no cover - trivial
        return self

    async def __aexit__(
        self, exc_type, exc_val, exc_tb
    ) -> None:  # pragma: no cover - trivial
        tasks = []
        for resource in reversed(self._resources):
            if hasattr(resource, "aclose"):
                tasks.append(resource.aclose())
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def aclose(self) -> None:
        """Async close: close tracked resources and clear caches."""
        await self.__aexit__(None, None, None)
        self.clear()

    @contextmanager
    def use_overrides(self, mapping: dict[Token[Any], Any]) -> Any:
        """Temporarily override tokens for this concurrent context.

        Example:
            with container.use_overrides({LOGGER: fake_logger}):
                svc = container.get(SERVICE)
                ...
        """
        parent = self._overrides.get()
        merged: dict[Token[Any], Any] = dict(parent) if parent else {}
        merged.update(mapping)
        token: CtxToken = self._overrides.set(merged)
        try:
            yield
        finally:
            self._overrides.reset(token)

    def clear_overrides(self) -> None:
        """Clear all overrides for the current context."""
        if self._overrides.get() is not None:
            self._overrides.set(None)

    # ============= Validation & Resource Tracking =============

    def _validate_and_track(self, token: Token[Any], instance: Any) -> None:
        if not token.validate(instance):
            raise TypeError(
                f"Provider for token '{token.name}' returned {type(instance).__name__}, expected {token.type_.__name__}"
            )
        if isinstance(instance, (SupportsClose, SupportsAsyncClose)):
            # track for later cleanup
            self._resources.append(instance)
