#!/usr/bin/env bash
set -euo pipefail

# Lint GitHub Actions workflows locally with actionlint and yamllint
# Usage: scripts/lint-workflows.sh

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
WORKFLOWS_DIR="$ROOT_DIR/.github/workflows"
BIN_DIR="$ROOT_DIR/.tools/bin"
mkdir -p "$BIN_DIR"

# Install actionlint locally if missing (Darwin/Linux prebuilt)
if [ ! -x "$BIN_DIR/actionlint" ]; then
  echo "Downloading actionlint…"
  curl -sSfL https://raw.githubusercontent.com/rhysd/actionlint/main/scripts/download-actionlint.bash \
    | bash -s -- latest "$BIN_DIR" >/dev/null
fi

# Install yamllint in an isolated virtualenv via uv if available, else fallback to pip
run_yamllint() {
  if command -v uv >/dev/null 2>&1; then
    uv tool run --from yamllint yamllint "$@"
  elif command -v python3 >/dev/null 2>&1; then
    python3 -m pip install --user -q yamllint
    python3 -m yamllint "$@"
  else
    echo "error: neither uv nor python3 found to run yamllint" >&2
    exit 1
  fi
}

echo "Running actionlint…"
"$BIN_DIR/actionlint" -color

echo "Running yamllint…"
if [ -f "$ROOT_DIR/.yamllint.yml" ]; then
  run_yamllint -c "$ROOT_DIR/.yamllint.yml" "$WORKFLOWS_DIR"
else
  run_yamllint "$WORKFLOWS_DIR"
fi

echo "✓ Workflows linted successfully"
