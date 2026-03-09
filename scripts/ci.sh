#!/usr/bin/env bash
# ci.sh — reproduce the GitHub Actions CI pipeline locally.
# Runs the lint job followed by the test job and reports a combined result.
# Requires the project's dependencies to already be installed.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Prefer .venv binaries if present
if [ -d "$REPO_ROOT/.venv/bin" ]; then
    export PATH="$REPO_ROOT/.venv/bin:$PATH"
fi

PASS=0
FAIL=0

run_step() {
    local label="$1"
    shift
    echo "=== $label"
    if "$@"; then
        PASS=$((PASS + 1))
    else
        echo "    STEP FAILED: $label"
        FAIL=$((FAIL + 1))
    fi
    echo
}

echo "================================================"
echo " Job: lint"
echo "================================================"
echo

run_step "black --check"  black --check src/ tests/
run_step "ruff check"     ruff check src/ tests/
run_step "mypy"           mypy src/

echo "================================================"
echo " Job: test"
echo "================================================"
echo

run_step "pytest" pytest -v --tb=short

echo "================================================"
echo " Summary: $PASS steps passed, $FAIL steps failed"
echo "================================================"

[ "$FAIL" -eq 0 ]
