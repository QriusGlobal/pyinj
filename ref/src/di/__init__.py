#!/usr/bin/env python3
from __future__ import annotations

from .core import (
    AsyncProvider,
    Container,
    Depends,
    Provider,
    ScopedContainer,
    SupportsAclose,
    Token,
    depends,
    inject,
    scoped,
)

__all__ = [
    "AsyncProvider",
    "Container",
    "Depends",
    "Provider",
    "ScopedContainer",
    "SupportsAclose",
    "Token",
    "depends",
    "inject",
    "scoped",
]

__version__ = "0.1.0"
