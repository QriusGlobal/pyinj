"""Protocol definitions for resource management and type checking."""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

if True:  # for type checkers without creating import cycles
    try:
        from .tokens import Token  # type: ignore
    except Exception:  # pragma: no cover - import-time typing only
        from typing import Any as Token  # type: ignore

__all__ = ["Resolvable", "SupportsAsyncClose", "SupportsClose"]


@runtime_checkable
class SupportsClose(Protocol):
    """Protocol for resources that can be synchronously closed."""

    def close(self) -> None:
        """Close the resource synchronously."""
        ...


@runtime_checkable
class SupportsAsyncClose(Protocol):
    """Protocol for resources that can be asynchronously closed."""

    async def aclose(self) -> None:
        """Close the resource asynchronously."""
        ...


T = TypeVar("T")


@runtime_checkable
class Resolvable(Protocol[T]):
    """Protocol for containers that can resolve dependencies sync/async."""

    def get(self, token: Token[T] | type[T]) -> T:  # pragma: no cover - protocol
        ...

    async def aget(self, token: Token[T] | type[T]) -> T:  # pragma: no cover - protocol
        ...
