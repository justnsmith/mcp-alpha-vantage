#!/usr/bin/env bash
# fix.sh — auto-format and auto-fix lint issues.
# Modifies files in place; run check.sh afterwards to confirm everything passes.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Prefer .venv binaries if present
if [ -d "$REPO_ROOT/.venv/bin" ]; then
    export PATH="$REPO_ROOT/.venv/bin:$PATH"
fi

echo "--- black (format)"
black src/ tests/
echo

echo "--- ruff (lint fix)"
ruff check --fix src/ tests/
echo

echo "Done. Run scripts/check.sh to verify."
