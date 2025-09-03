"""Lightweight decorators and markers for function parameter injection.

These tools are inspired by FastAPI but remain framework-agnostic and
work with synchronous and asynchronous callables.
"""

from __future__ import annotations

import asyncio
import builtins
from collections.abc import Callable
from functools import lru_cache, wraps
from inspect import Parameter, iscoroutinefunction, signature
from typing import get_type_hints
from typing import Any, TypeVar, cast, get_args, get_origin

from .protocols import Resolvable
from .tokens import Token

__all__ = [
    "Depends",
    "Given",
    "Inject",
    "InjectionAnalyzer",
    "analyze_dependencies",
    "inject",
    "resolve_dependencies",
]

T = TypeVar("T")
P = TypeVar("P")


class Inject:
    """
    Marker for injected dependencies (similar to FastAPI's ``Depends``).

    Usage:
        def handler(db: Inject[Database]):
            # db is auto-injected
            ...

        # Or with default provider
        def handler(db: Inject[Database] = Inject(create_db)):
            ...
    """

    def __init__(self, provider: Callable | None = None) -> None:
        """
        Initialize an injection marker optionally carrying a provider.

        Args:
            provider: Optional provider function
        """
        self.provider = provider
        self._type: type | None = None

    def __class_getitem__(cls, item: builtins.type[T]) -> builtins.type[Inject]:
        """
        Support Inject[Type] syntax.

        This allows type checkers to understand the type.
        """

        # Create a new class that remembers the type
        class TypedInject(cls):
            _inject_type = item

        return TypedInject

    @property
    def type(self) -> builtins.type | None:
        """Get the injected type if available."""
        if hasattr(self.__class__, "_inject_type"):
            return self.__class__._inject_type
        return self._type

    def __repr__(self) -> str:
        """Readable representation."""
        if self.type:
            return f"Inject[{self.type.__name__}]"
        return "Inject()"


class Given:
    """
    Scala-style given marker for implicit dependencies.

    Usage:
        def handler(db: Given[Database]):
            # db is resolved from given instances
            ...
    """

    def __class_getitem__(cls, item: type[T]) -> Inject:
        """Support Given[Type] syntax by delegating to Inject."""
        return Inject[item]


def Depends[T](provider: Callable[..., T]) -> T:  # noqa: N802
    """
    FastAPI-compatible ``Depends`` marker.

    Args:
        provider: Provider function for the dependency

    Returns:
        An :class:`Inject` marker usable as a default parameter value.
    """
    return Inject(provider)  # type: ignore


@lru_cache(maxsize=256)
def analyze_dependencies(func: Callable[..., Any]) -> dict[str, type | Token | Inject]:
    """
    Analyze function signature for injected dependencies.

    This is cached for performance as signature analysis is expensive.

    Args:
        func: Function to analyze

    Returns:
        Dictionary mapping parameter names to their injection specs
    """
    sig = signature(func)
    # Resolve annotations (handles from __future__ import annotations)
    try:
        resolved = get_type_hints(func, include_extras=True)
    except Exception:
        resolved = {}
    deps: dict[str, type | Token | Inject] = {}

    for name, param in sig.parameters.items():
        # Skip *args and **kwargs
        if param.kind in (Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD):
            continue

        annotation = resolved.get(name, param.annotation)

        # Skip if no annotation
        if annotation is Parameter.empty:
            continue

        # Check various injection patterns
        if _is_inject_type(annotation):
            # It's Inject[T] or Given[T]
            deps[name] = _extract_inject_spec(annotation, param.default)

        elif isinstance(param.default, Inject):
            # Default value is Inject()
            deps[name] = param.default
            if annotation != Parameter.empty:
                # Store the type from annotation
                param.default._type = annotation

        elif isinstance(annotation, Token):
            # Direct Token annotation
            deps[name] = annotation

        elif hasattr(annotation, "__metadata__"):
            # Annotated[Type, metadata] pattern
            for metadata in annotation.__metadata__:
                if isinstance(metadata, Inject | Token):
                    deps[name] = metadata
                    break

        elif _is_plain_injectable_type(annotation):
            # Fallback: plain type annotation (non-builtin class/protocol)
            deps[name] = annotation

        elif isinstance(param.annotation, str) and "Inject[" in param.annotation:
            # Last-resort: parse string annotations from future annotations
            inner = param.annotation.strip()
            try:
                inner_type_str = inner[inner.find("[") + 1 : inner.rfind("]")]
                inner_type = eval(inner_type_str, func.__globals__, {})  # noqa: S307 (trusted test context)
                marker = Inject()
                marker._type = inner_type
                deps[name] = marker
            except Exception:
                # Ignore if we cannot resolve
                pass

    return deps


class InjectionAnalyzer:
    """Small analyzer facade to build dependency plans.

    This class enables decomposition and easier testing while
    remaining backward-compatible with analyze_dependencies.
    """

    @staticmethod
    def build_plan(func: Callable[..., Any]) -> dict[str, type | Token | Inject]:
        return analyze_dependencies(func)


def _is_inject_type(annotation: Any) -> bool:
    """Check if annotation is Inject[T] or Given[T] type."""
    # Check for our custom TypedInject classes
    if hasattr(annotation, "_inject_type"):
        return True

    # Check using get_origin for generic types
    origin = get_origin(annotation)
    if origin is not None:
        return origin is Inject or (
            hasattr(origin, "__name__") and origin.__name__ in ("Inject", "Given")
        )

    # Check if it's a direct Inject class
    return isinstance(annotation, type) and issubclass(annotation, Inject)


def _is_plain_injectable_type(annotation: Any) -> bool:
    """Heuristically decide whether a plain type hint should be injected.

    We inject only for non-builtin classes/protocols to avoid surprising
    behavior with primitives like ``int`` or ``str``.
    """
    try:
        return (
            isinstance(annotation, type)
            and getattr(annotation, "__module__", "builtins") != "builtins"
        )
    except Exception:
        return False


def _extract_inject_spec(
    annotation: Any, default: Any = Parameter.empty
) -> type | Token | Inject:
    """Extract injection specification from annotation."""
    # Get the type from Inject[T]
    if hasattr(annotation, "_inject_type"):
        type_ = annotation._inject_type
    else:
        args = get_args(annotation)
        type_ = args[0] if args else None

    # If there's a default Inject instance, use it
    if isinstance(default, Inject):
        if type_ and not default._type:
            default._type = type_
        return default

    # Return just the type
    return type_ or annotation


def resolve_dependencies(
    deps: dict[str, type | Token | Inject],
    container: Resolvable[Any],
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Resolve dependencies synchronously.

    Args:
        deps: Dependencies to resolve
        container: Container to resolve from
        overrides: Optional overrides for specific dependencies

    Returns:
        Dictionary of resolved dependencies
    """
    resolved: dict[str, Any] = {}
    overrides = overrides or {}

    for name, spec in deps.items():
        # Check for override first
        if name in overrides:
            resolved[name] = overrides[name]
            continue

        # Resolve based on spec type
        if isinstance(spec, Token):
            # Direct token
            resolved[name] = container.get(spec)

        elif isinstance(spec, Inject):
            # Inject with optional provider
            if spec.provider:
                # Call the provider
                resolved[name] = spec.provider()
            elif spec.type:
                # Create token from type
                token = Token(spec.type.__name__, spec.type)
                resolved[name] = container.get(token)

        elif isinstance(spec, type):
            # Direct type annotation
            token = Token(spec.__name__, spec)
            resolved[name] = container.get(token)

    return resolved


async def resolve_dependencies_async(
    deps: dict[str, type | Token | Inject],
    container: Resolvable[Any],
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Resolve dependencies asynchronously.

    Args:
        deps: Dependencies to resolve
        container: Container to resolve from
        overrides: Optional overrides for specific dependencies

    Returns:
        Dictionary of resolved dependencies
    """
    resolved: dict[str, Any] = {}
    overrides = overrides or {}
    tasks: dict[str, asyncio.Task[Any]] = {}

    for name, spec in deps.items():
        # Check for override first
        if name in overrides:
            resolved[name] = overrides[name]
            continue

        # Create resolution task based on spec type
        if isinstance(spec, Token):
            if hasattr(container, "aget"):
                tasks[name] = asyncio.create_task(container.aget(spec))
            else:
                # Fallback to sync in executor
                loop = asyncio.get_event_loop()
                tasks[name] = loop.run_in_executor(None, container.get, spec)

        elif isinstance(spec, Inject):
            if spec.provider:
                if iscoroutinefunction(spec.provider):
                    tasks[name] = asyncio.create_task(spec.provider())
                else:
                    loop = asyncio.get_event_loop()
                    tasks[name] = loop.run_in_executor(None, spec.provider)
            elif spec.type:
                token = Token(spec.type.__name__, spec.type)
                if hasattr(container, "aget"):
                    tasks[name] = asyncio.create_task(container.aget(token))
                else:
                    loop = asyncio.get_event_loop()
                    tasks[name] = loop.run_in_executor(None, container.get, token)

        elif isinstance(spec, type):
            token = Token(spec.__name__, spec)
            if hasattr(container, "aget"):
                tasks[name] = asyncio.create_task(container.aget(token))
            else:
                loop = asyncio.get_event_loop()
                tasks[name] = loop.run_in_executor(None, container.get, token)

    # Resolve all tasks in parallel
    if tasks:
        results: list[Any] = await asyncio.gather(*tasks.values())
        for name, result in zip(tasks.keys(), results, strict=False):
            resolved[name] = result

    return resolved


def inject(
    func: Callable[..., Any] | None = None,
    *,
    container: Any | None = None,
    cache: bool = True,
) -> Callable[..., Any]:
    """
    Decorator that injects dependencies into function parameters.

    This is the main entry point for dependency injection, inspired by
    FastAPI's dependency injection system.

    Args:
        func: Function to decorate (or None if using with parameters)
        container: Container to resolve dependencies from
        cache: Whether to cache dependency analysis

    Returns:
        Decorated function with automatic dependency injection

    Examples:
        @inject
        def service(db: Inject[Database]):
            return db.query()

        @inject(container=my_container)
        async def handler(cache: Inject[Cache]):
            return await cache.get("key")

        @inject
        async def endpoint(
            user_id: int,
            db: Inject[Database],
            cache: Given[Cache],
            settings: Settings = Inject()
        ):
            # Mixed regular and injected parameters
            pass
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        # Analyze dependencies (cached if cache=True)
        deps = InjectionAnalyzer.build_plan(fn) if cache else None

        if iscoroutinefunction(fn):

            @wraps(fn)
            async def async_wrapper(*args: object, **kwargs: object) -> Any:
                # Get dependencies if not cached
                nonlocal deps
                if deps is None:
                    deps = InjectionAnalyzer.build_plan(fn)

                if not deps:
                    # No dependencies, call original
                    return await fn(*args, **kwargs)

                # Get container
                nonlocal container
                if container is None:
                    # Try to get default container without import cycle
                    from .container import get_default_container

                    container = get_default_container()

                # Extract overrides from kwargs
                overrides: dict[str, Any] = {}
                for name in deps:
                    if name in kwargs:  # type: ignore[operator]
                        overrides[name] = cast(Any, kwargs.pop(name))  # type: ignore[call-arg]

                # Resolve dependencies
                resolved = await resolve_dependencies_async(deps, container, overrides)

                # Merge with kwargs
                kwargs.update(resolved)

                return await fn(*args, **kwargs)  # type: ignore[misc]

            return async_wrapper

        else:

            @wraps(fn)
            def sync_wrapper(*args: object, **kwargs: object) -> Any:
                # Get dependencies if not cached
                nonlocal deps
                if deps is None:
                    deps = InjectionAnalyzer.build_plan(fn)

                if not deps:
                    # No dependencies, call original
                    return fn(*args, **kwargs)

                # Get container
                nonlocal container
                if container is None:
                    from .container import get_default_container

                    container = get_default_container()

                # Extract overrides from kwargs
                overrides: dict[str, Any] = {}
                for name in deps:
                    if name in kwargs:  # type: ignore[operator]
                        overrides[name] = cast(Any, kwargs.pop(name))  # type: ignore[call-arg]

                # Resolve dependencies
                resolved = resolve_dependencies(deps, container, overrides)

                # Merge with kwargs
                kwargs.update(resolved)

                return fn(*args, **kwargs)  # type: ignore[misc]

            return sync_wrapper

    # Handle both @inject and @inject(...) syntax
    if func is None:
        # Called with parameters: @inject(container=...)
        return decorator
    else:
        # Called without parameters: @inject
        return decorator(func)
