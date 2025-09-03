"""Protocol definitions for resource management and type checking."""

from __future__ import annotations

from typing import Any, Protocol, TypeVar, runtime_checkable

if True:  # for type checkers without creating import cycles
    try:
        from .tokens import Token  # type: ignore
    except Exception:  # pragma: no cover - import-time typing only
        Token = Any  # type: ignore

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


T_co = TypeVar("T_co", covariant=True)


@runtime_checkable
class Resolvable(Protocol[T_co]):
    """Protocol for containers that can resolve dependencies sync/async."""

    def get(
        self, token: Token[T_co] | type[T_co]
    ) -> T_co:  # pragma: no cover - protocol
        ...

    async def aget(
        self, token: Token[T_co] | type[T_co]
    ) -> T_co:  # pragma: no cover - protocol
        ...
