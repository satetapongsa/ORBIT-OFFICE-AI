#!/usr/bin/env bash
# Run all static checks and unit tests for backend and frontend.
# Usage: scripts/check.sh            (from the repository root)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -x "$ROOT/backend/.venv/bin/python" ]]; then
  PY="$ROOT/backend/.venv/bin/python"
elif [[ -x "$ROOT/backend/.venv/Scripts/python.exe" ]]; then
  PY="$ROOT/backend/.venv/Scripts/python.exe"
else
  PY="python"
fi

echo "==> backend: ruff"
(cd "$ROOT/backend" && "$PY" -m ruff check . && "$PY" -m ruff format --check .)
echo "==> backend: mypy"
(cd "$ROOT/backend" && "$PY" -m mypy app)
echo "==> backend: pytest"
(cd "$ROOT/backend" && "$PY" -m pytest -q)
echo "==> backend: alembic offline SQL"
(cd "$ROOT/backend" && "$PY" -m alembic upgrade head --sql > /dev/null)

echo "==> frontend: lint"
(cd "$ROOT/frontend" && npm run --silent lint)
echo "==> frontend: typecheck"
(cd "$ROOT/frontend" && npm run --silent typecheck)
echo "==> frontend: tests"
(cd "$ROOT/frontend" && npm run --silent test)
echo "==> frontend: format check"
(cd "$ROOT/frontend" && npm run --silent format:check)

echo "All checks passed."
