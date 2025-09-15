"""PyInj - Type-safe dependency injection for modern Python.

⚠️ DEPRECATED: PyInj has been renamed to 'injx'. Please migrate to the new package.

Status: DEPRECATED - This package is no longer maintained.

Migration Instructions:
1. Uninstall pyinj: pip uninstall pyinj
2. Install injx: pip install injx
3. Update imports: Change 'from pyinj' to 'from injx'

For more information, visit: https://github.com/QriusGlobal/injx
"""

import warnings

# Show deprecation warning when the package is imported
warnings.warn(
    "\n"
    "="*70 + "\n"
    "DEPRECATION WARNING\n" 
    "="*70 + "\n"
    "PyInj has been renamed to 'injx' and this package is deprecated.\n"
    "\n"
    "Please migrate to the new package:\n"
    "  1. Uninstall: uv remove pyinj (or pip uninstall pyinj)\n"
    "  2. Install:   uv add injx (or pip install injx)\n"
    "  3. Update imports: Change 'from pyinj' to 'from injx'\n"
    "\n"
    "For more information, visit: https://github.com/QriusGlobal/injx\n"
    "="*70,
    DeprecationWarning,
    stacklevel=2
)

from pyinj.container import Container
from pyinj.contextual import ContextualContainer, RequestScope, SessionScope
from pyinj.defaults import get_default_container, set_default_container
from pyinj.exceptions import CircularDependencyError, PyInjError, ResolutionError
from pyinj.injection import Depends, Given, Inject, inject
from pyinj.metaclasses import Injectable
from pyinj.tokens import Scope, Token, TokenFactory

__version__ = "1.3.0"
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
