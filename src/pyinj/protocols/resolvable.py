from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

if True:  # typing-only import without runtime cycle
    try:
        from ..tokens import Token  # type: ignore
    except Exception:  # pragma: no cover
        from typing import Any as Token  # type: ignore

T = TypeVar("T")


@runtime_checkable
class Resolvable(Protocol[T]):
    """Protocol for containers that can resolve dependencies sync/async."""

    def get(self, token: Token[T] | type[T]) -> T:  # pragma: no cover - protocol
        ...

    async def aget(self, token: Token[T] | type[T]) -> T:  # pragma: no cover - protocol
        ...
