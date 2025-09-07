"""PyInj - Type-safe dependency injection for modern Python.

Status: Beta - APIs may change between pre-releases. Pin exact versions in production.

Highlights:
- Immutable tokens with pre-computed hashes (O(1) lookups)
- ContextVar-based scoping for async and thread safety
- `@inject` decorator (FastAPI-inspired) and lightweight markers
- Scala-style "given" instances for ergonomic overrides
- Zero runtime dependencies

Quick start:
    from pyinj import Container, Token, Scope

    container = Container()
    DB = Token[Database]("database")
    container.register(DB, create_database, scope=Scope.SINGLETON)

    db = container.get(DB)
    # ... use db ...
"""

from pyinj.container import Container
from pyinj.contextual import ContextualContainer, RequestScope, SessionScope
from pyinj.defaults import get_default_container, set_default_container
from pyinj.exceptions import CircularDependencyError, PyInjError, ResolutionError
from pyinj.injection import Depends, Given, Inject, inject
from pyinj.metaclasses import Injectable
from pyinj.tokens import Scope, Token, TokenFactory

__version__ = "1.2.0"
__author__ = "Qrius Global"

__all__ = [
    "Container",
    "ContextualContainer",
    "Depends",
    "Given",
    "Inject",
    "Injectable",
    "RequestScope",
    "Scope",
    "SessionScope",
    "Token",
    "TokenFactory",
    "PyInjError",
    "ResolutionError",
    "CircularDependencyError",
    "get_default_container",
    "inject",
    "set_default_container",
]
