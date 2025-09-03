Project Stub Directory (BasedPyright)

Purpose
- Provide ad-hoc type stubs (.pyi) for third-party libraries that are missing or incomplete typings, per BasedPyright’s typed-libraries guidance.

Where stubs are used
- BasedPyright searches `stubPath` entries before workspace code and site-packages. We configured:
  - pyproject.toml → [tool.basedpyright].stubPath = "typings"

Conventions
- Structure stubs to mirror the import path. Examples:
  - typings/asyncpg/__init__.pyi
  - typings/aiosqlite/__init__.pyi
  - typings/vendorpkg/submodule.pyi
- Keep stubs minimal and precise for only what our code imports.
- Prefer upstream stub packages if available (e.g., types-...). Use local stubs only to unblock.

How to add a stub
1) Create the module path under `typings/`.
2) Add `.pyi` files with the minimal classes/functions/vars and accurate signatures.
3) Re-run `basedpyright` to verify the diagnostic disappears.

Example skeleton
  # typings/aiosqlite/__init__.pyi
  from typing import Protocol, Any

  class Connection(Protocol):
      async def close(self) -> None: ...

  async def connect(path: str, /) -> Connection: ...

Notes
- Our library is typed (py.typed present), so no internal stubs are necessary.
- Prefer improving our source hints over stubbing our own modules.
