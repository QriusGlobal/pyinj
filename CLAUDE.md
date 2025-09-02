Project maintenance and release notes

Overview
- This project provides a type-safe DI container for Python 3.13+.
- Tokens are strictly typed: only `Token` or `type` are allowed; string tokens are not supported.
- Scopes are orchestrated by `ScopeManager` (contextvars-backed, async-safe).
- Injection analysis is centralized via `InjectionAnalyzer` and cached `analyze_dependencies`.
- Resolution utilities accept any container implementing the `Resolvable[T]` protocol.

Repository conventions
- Source: `src/pyinj/`
- Tests: `tests/`
- Package typing marker: `src/pyinj/py.typed`
- Single distribution name: `pyinj`

Release process (uv-native)
1) Set version and classifiers (pyproject and package):
   - Edit `pyproject.toml` → `[project].version` (use SemVer; add `a/b/rc` for pre-releases).
   - Edit `src/pyinj/__init__.py` → `__version__` to match.
   - For in-development status, use classifier: `Development Status :: 4 - Beta`.

2) Build artifacts locally:
   - `rm -rf dist`
   - `uv build`

3) Publish to PyPI with token:
   - Ensure `PYPI_API_TOKEN` is available.
   - `uv publish --token "$PYPI_API_TOKEN"`

4) CI/CD with GitHub Actions:
   - `.github/workflows/ci.yml` uses `astral-sh/setup-uv@v4`, installs with `uv pip` and runs `uv run pytest`.
   - `.github/workflows/publish.yml` clears `dist/`, runs `uv build`, and publishes via `uv publish --token $PYPI_API_TOKEN`.
   - Alternative: switch to Trusted Publishing (OIDC) by enabling PyPI trusted publishers and setting `--trusted-publishing` in `uv publish` or using the workflow’s OIDC context.

PyPI policies to remember
- PyPI does not allow overwriting a version. Once uploaded, that version number can’t be reused.
- Yanking is the correct way to deprecate a bad release. Do this from the PyPI web UI (no official API/CLI for yank at this time).
- Project URLs in the sidebar come from `[project.urls]` in `pyproject.toml`.
- README rendering: use structured `readme = { file = "README.md", content-type = "text/markdown" }`.

Recent changes (this iteration)
- Removed string-token fallback; API is strictly `Token` or `type`.
- Extracted scope handling into `ScopeManager` and delegated from `ContextualContainer`.
- Completed `InjectionAnalyzer` pipeline usage in injection decorator.
- Strengthened typing with `Resolvable` protocol in `protocols.py` and used in resolve functions.
- Tests updated to avoid strings and to assert correct exception types.
- `py.typed` moved under `src/pyinj/` and included in wheels/sdists via Hatch config.
- Version updated and metadata expanded (URLs, classifiers).
- Added uv-based CI and publish workflows. Publish workflow now clears `dist/` before building.

Operational tips
- Prefer tokens from `TokenFactory` or `Token(name, type_)` for clarity.
- Avoid registering async providers for sync `get()`; prefer `aget()` or wrap appropriately.
- Use `use_overrides()` for scoped overrides in tests.
- For semver pre-releases, use `1.0.1b1` (beta) or `1.0.1rc1` (release-candidate). Finalize with `1.0.1`.

