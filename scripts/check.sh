#!/usr/bin/env bash
# check.sh — run all static checks without modifying any files.
# Exits non-zero if any check fails.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Prefer .venv binaries if present
if [ -d "$REPO_ROOT/.venv/bin" ]; then
    export PATH="$REPO_ROOT/.venv/bin:$PATH"
fi

PASS=0
FAIL=0

run_check() {
    local label="$1"
    shift
    echo "--- $label"
    if "$@"; then
        echo "    OK"
        PASS=$((PASS + 1))
    else
        echo "    FAILED"
        FAIL=$((FAIL + 1))
    fi
    echo
}

run_check "black (format check)" black --check src/ tests/
run_check "ruff (lint)"          ruff check src/ tests/
run_check "mypy (type check)"    mypy src/

echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
