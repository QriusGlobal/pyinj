#!/usr/bin/env bash
set -euo pipefail

echo "Running Ruff format check…"
if command -v uv >/dev/null 2>&1; then
  uv tool run --from ruff ruff format --check .
  uv tool run --from ruff ruff check .
else
  ruff format --check .
  ruff check .
fi

echo "Running BasedPyright…"
if command -v uv >/dev/null 2>&1; then
  uv tool run --from basedpyright basedpyright src/ tests/
else
  basedpyright src/ tests/
fi

echo "Running workflow lint…"
"$(dirname "$0")/lint-workflows.sh"

echo "✓ All linters passed"

