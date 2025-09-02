"""PyInj - Enhanced DI Container with Zero Dependencies.

A production-ready dependency injection container featuring:
- Immutable tokens with pre-computed hashes (O(1) lookups)
- ContextVar-based scoping for async safety
- FastAPI-style @inject decorator
- Scala-inspired given instances
- Zero external dependencies
"""

from pyinj.container import Container, get_default_container, set_default_container
from pyinj.contextual import ContextualContainer, RequestScope, SessionScope
from pyinj.injection import Depends, Given, Inject, inject
from pyinj.tokens import Scope, Token, TokenFactory

__version__ = "1.0.1b1"
__author__ = "Qrius Global"

__all__ = [
    "Container",
    "ContextualContainer",
    "Depends",
    "Given",
    "Inject",
    "RequestScope",
    "Scope",
    "SessionScope",
    "Token",
    "TokenFactory",
    "get_default_container",
    "inject",
    "set_default_container",
]
