"""Type definitions and aliases for pyinj."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

__all__ = ["AsyncProvider", "Provider", "ProviderFactory", "SyncProvider"]

# Type aliases for clarity (PEP 695 type statements)
type SyncProvider = Callable[[], Any]
type AsyncProvider = Callable[[], Awaitable[Any]]
type Provider = SyncProvider | AsyncProvider
type ProviderFactory = Callable[..., Any]
