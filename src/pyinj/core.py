"""Core container implementation for pyinj dependency injection."""

from __future__ import annotations

import asyncio
import inspect
import threading
from collections import defaultdict
from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar
from contextvars import Token as CtxToken
from functools import wraps
from typing import (
    Any,
    Protocol,
    TypeVar,
    cast,
    get_args,
    get_origin,
    get_type_hints,
)

from pyinj.exceptions import CircularDependencyError, ResolutionError
from pyinj.metaclasses import Injectable
from pyinj.protocols import SupportsAsyncClose, SupportsClose
from pyinj.tokens import Scope, Token
from pyinj.types import Provider

__all__ = ["Container"]

T = TypeVar("T")
P = TypeVar("P", bound=Protocol)


class Container:
    """Thread-safe, async-safe, type-safe dependency injection container.

    This container provides:
    - Thread-safe singleton creation
    - Async-safe resolution with proper locking
    - O(1) type lookups for performance
    - Circular dependency detection
    - Automatic resource cleanup
    - Protocol-based resolution
    - Metaclass auto-registration support
    """

    def __init__(self) -> None:
        """Initialize the container with empty state."""
        # Core provider registry
        self._providers: dict[Token[Any], tuple[Provider, Scope]] = {}
        self._singletons: dict[Token[Any], Any] = {}

        # Thread safety
        self._singleton_locks: dict[Token[Any], threading.RLock] = {}
        self._async_singleton_locks: dict[Token[Any], asyncio.Lock] = {}
        self._registry_lock = threading.RLock()

        # Thread-local resolution tracking
        self._local = threading.local()

        # Resource management
        self._resources: list[Any] = []
        self._resources_lock = threading.Lock()

        # Performance: O(1) type lookups
        self._type_map: dict[type, Token] = {}
        self._protocol_map: dict[type[Protocol], list[Token]] = defaultdict(list)

        # Cached injection data for @inject decorator
        self._injection_cache: dict[Callable, list[tuple[str, type, Any]]] = {}

        # Auto-register metaclass-marked classes
        self._auto_register()

        # ContextVar for per-context overrides (DI_SPEC requirement)
        self._overrides: ContextVar[dict[Token[Any], Any] | None] = ContextVar(
            "pyinj_overrides",
            default=None,
        )

    def _auto_register(self) -> None:
        """Register all classes marked with Injectable metaclass."""
        for cls, token in Injectable.get_registry().items():
            if hasattr(cls, "__scope__"):
                # Get constructor dependencies
                try:
                    hints = get_type_hints(cls.__init__)
                    deps = {
                        k: v for k, v in hints.items() if k not in ("self", "return")
                    }

                    if deps:
                        # Create auto-wiring factory
                        def make_factory(target_cls=cls, dependencies=deps):
                            def factory() -> Any:
                                kwargs = {}
                                for param_name, param_type in dependencies.items():
                                    kwargs[param_name] = self._resolve_type(param_type)
                                return target_cls(**kwargs)

                            return factory

                        self.register(token, make_factory(), cls.__scope__)
                    else:
                        # No dependencies, simple factory
                        self.register(token, cls, cls.__scope__)  # type: ignore[arg-type]
                except Exception:
                    # Skip auto-registration on error
                    pass

    def register(
        self,
        token: Token[T],
        provider: Provider,
        scope: Scope = Scope.TRANSIENT,
    ) -> None:
        """Register a provider for the given token.

        Args:
            token: Unique identifier for the dependency
            provider: Factory function that creates the dependency
            scope: Lifecycle scope for the dependency

        Raises:
            ValueError: If token is already registered with different scope
        """
        with self._registry_lock:
            # Store provider and scope
            self._providers[token] = (provider, scope)

            # Pre-create locks for singletons (CRITICAL: at registration time)
            if scope == Scope.SINGLETON:
                self._singleton_locks[token] = threading.RLock()
                self._async_singleton_locks[token] = asyncio.Lock()

            # Update O(1) lookup maps
            if token.expected_type:
                self._type_map[token.expected_type] = token
            if token.protocol:
                self._protocol_map[token.protocol].append(token)

    def get(self, token: Token[T]) -> T:
        """Resolve a dependency synchronously.

        Args:
            token: The token identifying the dependency

        Returns:
            The resolved dependency instance

        Raises:
            ResolutionError: If the dependency cannot be resolved
            CircularDependencyError: If a circular dependency is detected
        """
        # Initialize thread-local state
        if not hasattr(self._local, "resolving"):
            self._local.resolving: list[Token] = []

        # Check for circular dependency
        if token in self._local.resolving:
            raise CircularDependencyError(token, self._local.resolving.copy())

        # Add to resolution chain
        self._local.resolving.append(token)
        try:
            # Check for context overrides first
            current_overrides = self._overrides.get()
            if current_overrides and token in current_overrides:
                return cast(T, current_overrides[token])

            # Check if provider exists
            if token not in self._providers:
                raise ResolutionError(
                    token,
                    self._local.resolving.copy(),
                    f"No provider registered for token '{token.name}'",
                )

            provider, scope = self._providers[token]

            # Prevent async providers in sync context
            if asyncio.iscoroutinefunction(provider):
                raise ResolutionError(
                    token,
                    self._local.resolving.copy(),
                    "Cannot resolve async provider with get(). Use aget() instead.",
                )

            # Resolve based on scope
            if scope == Scope.SINGLETON:
                return self._get_singleton(token, provider)
            elif scope == Scope.TRANSIENT:
                instance = provider()  # type: ignore[misc]
                self._validate_and_track(token, instance)
                return cast(T, instance)
            else:
                # REQUEST/SESSION scopes would use ContextVar here
                instance = provider()  # type: ignore[misc]
                self._validate_and_track(token, instance)
                return cast(T, instance)

        finally:
            # Remove from resolution chain
            self._local.resolving.pop()

    def _get_singleton(self, token: Token[T], provider: Callable[[], Any]) -> T:
        """Create or retrieve singleton with thread-safe double-checked locking.

        Args:
            token: The singleton token
            provider: Factory function for creating the singleton

        Returns:
            The singleton instance
        """
        # First check without lock (fast path)
        if token not in self._singletons:
            # Acquire lock and check again (slow path)
            with self._singleton_locks[token]:
                if token not in self._singletons:
                    # Create the singleton
                    instance = provider()
                    self._validate_and_track(token, instance)
                    self._singletons[token] = instance

        return cast(T, self._singletons[token])

    async def aget(self, token: Token[T]) -> T:
        """Resolve a dependency asynchronously.

        Args:
            token: The token identifying the dependency

        Returns:
            The resolved dependency instance

        Raises:
            ResolutionError: If the dependency cannot be resolved
            CircularDependencyError: If a circular dependency is detected
        """
        # Initialize thread-local state
        if not hasattr(self._local, "resolving"):
            self._local.resolving: list[Token] = []

        # Check for circular dependency
        if token in self._local.resolving:
            raise CircularDependencyError(token, self._local.resolving.copy())

        # Add to resolution chain
        self._local.resolving.append(token)
        try:
            # Check for context overrides first
            current_overrides = self._overrides.get()
            if current_overrides and token in current_overrides:
                return cast(T, current_overrides[token])

            # Check if provider exists
            if token not in self._providers:
                raise ResolutionError(
                    token,
                    self._local.resolving.copy(),
                    f"No provider registered for token '{token.name}'",
                )

            provider, scope = self._providers[token]

            # Handle singleton scope with async-safe locking
            if scope == Scope.SINGLETON:
                if token not in self._singletons:
                    # CRITICAL: Use pre-created lock to prevent race condition
                    async with self._async_singleton_locks[token]:
                        # Double-check after acquiring lock
                        if token not in self._singletons:
                            if asyncio.iscoroutinefunction(provider):
                                instance = await provider()  # type: ignore[misc]
                            else:
                                instance = provider()  # type: ignore[misc]
                            self._validate_and_track(token, instance)
                            self._singletons[token] = instance
                return cast(T, self._singletons[token])
            else:
                # Non-singleton scopes
                if asyncio.iscoroutinefunction(provider):
                    instance = await provider()  # type: ignore[misc]
                else:
                    instance = provider()  # type: ignore[misc]
                self._validate_and_track(token, instance)
                return cast(T, instance)

        finally:
            # Remove from resolution chain
            self._local.resolving.pop()

    def _validate_and_track(self, token: Token[T], instance: T) -> None:
        """Validate instance type and register for cleanup.

        Args:
            token: The token this instance was created for
            instance: The created instance

        Raises:
            TypeError: If instance doesn't match token's type expectations
        """
        # Validate type expectations
        if not token.validate(instance):
            expected = token.expected_type or token.protocol
            raise TypeError(
                f"Provider for token '{token.name}' returned {type(instance)}, "
                f"expected {expected}"
            )

        # Track closeable resources
        if isinstance(instance, SupportsClose | SupportsAsyncClose):
            with self._resources_lock:
                self._resources.append(instance)

    def _resolve_type(self, param_type: type) -> Any:
        """Resolve a dependency by its type (O(1) lookup).

        Args:
            param_type: The type to resolve

        Returns:
            Resolved instance of the type

        Raises:
            ResolutionError: If type cannot be resolved
        """
        # Handle Token[T] type hints
        origin = get_origin(param_type)
        if origin is Token:
            # Extract the inner type from Token[SomeType]
            args = get_args(param_type)
            if args:
                inner_type = args[0]
                if inner_type in self._type_map:
                    return self.get(self._type_map[inner_type])

        # Handle concrete types - O(1) lookup
        if param_type in self._type_map:
            return self.get(self._type_map[param_type])

        # Handle protocol types
        if hasattr(param_type, "__protocol__"):
            return self.resolve_protocol(param_type)

        # Type not found
        raise ResolutionError(
            Token("unknown_type"),
            [],
            f"Cannot resolve type {param_type}. "
            f"Register a provider for this type first.",
        )

    def resolve_protocol(self, protocol: type[P]) -> P:
        """Resolve a dependency by protocol without speculative instantiation.

        Args:
            protocol: The protocol type to resolve

        Returns:
            Instance implementing the protocol

        Raises:
            ResolutionError: If no implementation found
        """
        # Check direct protocol mappings first
        if protocol in self._protocol_map:
            tokens = self._protocol_map[protocol]
            if tokens:
                return self.get(tokens[0])

        # Check if any registered providers return this protocol type
        for token, (provider, _) in self._providers.items():
            if token.protocol == protocol:
                return self.get(token)

            # Check return type annotation of provider
            if hasattr(provider, "__annotations__"):
                return_type = provider.__annotations__.get("return")
                if return_type and hasattr(return_type, "__protocol__"):
                    if return_type == protocol:
                        return self.get(token)

        raise ResolutionError(
            Token("protocol"),
            [],
            f"No implementation registered for protocol {protocol.__name__}",
        )

    def inject(self, func: Callable[..., T]) -> Callable[..., T]:
        """Decorator for automatic dependency injection.

        Analyzes function parameters and injects registered dependencies
        based on type hints.

        Args:
            func: Function to inject dependencies into

        Returns:
            Wrapped function with automatic injection
        """
        # Cache injection parameters (computed once at decoration time)
        if func not in self._injection_cache:
            sig = inspect.signature(func)
            hints = get_type_hints(func)

            params_to_inject = []
            for param_name, param in sig.parameters.items():
                if param.annotation != param.empty and param_name not in (
                    "self",
                    "cls",
                ):
                    param_type = hints.get(param_name)
                    if param_type:
                        params_to_inject.append((param_name, param_type, param.default))

            self._injection_cache[func] = params_to_inject

        # Get cached injection parameters
        params_to_inject = self._injection_cache[func]

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            # Only inject missing parameters
            sig = inspect.signature(func)
            bound_args = sig.bind_partial(*args, **kwargs)

            for param_name, param_type, default in params_to_inject:
                if param_name not in bound_args.arguments:
                    try:
                        kwargs[param_name] = self._resolve_type(param_type)
                    except ResolutionError:
                        # Only raise if parameter has no default value
                        if default == inspect.Parameter.empty:
                            raise

            return func(*args, **kwargs)

        return wrapper

    async def dispose(self) -> None:
        """Dispose of all tracked resources safely.

        This method properly closes all registered resources without
        causing asyncio event loop conflicts.
        """
        # Close resources in reverse order (LIFO)
        for resource in reversed(self._resources):
            try:
                if isinstance(resource, SupportsAsyncClose):
                    await resource.aclose()
                elif isinstance(resource, SupportsClose):
                    resource.close()
            except Exception:
                # Suppress cleanup errors to allow other resources to close
                pass

        # Clear all state
        with self._resources_lock:
            self._resources.clear()
        self._singletons.clear()

    async def aclose(self) -> None:
        """Async close alias to satisfy DI_SPEC SupportsAsyncClose.

        Closes tracked resources and clears all caches.
        """
        await self.dispose()

    def override(self, token: Token[T], value: T) -> None:
        """Override a dependency with a specific value (useful for testing).

        Args:
            token: The token to override
            value: The replacement value
        """
        self._singletons[token] = value

    @contextmanager
    def use_overrides(self, mapping: dict[Token[Any], Any]) -> Any:
        """Temporarily override tokens within this context.

        Uses ContextVar to ensure isolation between concurrent contexts
        and supports proper nesting, as per DI_SPEC.
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
        """Clear all overrides and singleton cache."""
        # Clear ContextVar overrides for this context
        if self._overrides.get() is not None:
            self._overrides.set(None)
        # Also clear singleton cache overrides
        self._singletons.clear()

    def clear_cache(self) -> None:
        """Clear the injection cache (useful for testing)."""
        self._injection_cache.clear()

    def is_registered(self, token: Token[Any]) -> bool:
        """Check if a token is registered.

        Args:
            token: The token to check

        Returns:
            True if the token is registered
        """
        return token in self._providers

    def get_scope(self, token: Token[Any]) -> Scope | None:
        """Get the scope of a registered token.

        Args:
            token: The token to check

        Returns:
            The scope of the token, or None if not registered
        """
        if token in self._providers:
            return self._providers[token][1]
        return None
