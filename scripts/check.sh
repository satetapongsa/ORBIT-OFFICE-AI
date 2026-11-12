#!/usr/bin/env bash
# Run all static checks and tests for backend and frontend.
#
# Usage (from the repository root):
#   scripts/check.sh                       backend checks with the local venv
#   CHECK_BACKEND_IN_DOCKER=1 scripts/check.sh
#                                          backend checks inside the running `backend` container
#
# Database-backed tests (auth/RBAC/ACL) need PostgreSQL from `docker compose up -d`;
# they are skipped with a reason when it is unreachable.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

backend_in_docker() {
  (cd "$ROOT" && docker compose exec -T -e PYTHONDONTWRITEBYTECODE=1 \
    -e ORBIT_RUN_INTEGRATION="${ORBIT_RUN_INTEGRATION:-}" backend "$@")
}

if [[ "${CHECK_BACKEND_IN_DOCKER:-}" == "1" ]]; then
  run_py() { backend_in_docker python "$@"; }
  echo "==> backend checks run inside the docker compose 'backend' container"
else
  if [[ -x "$ROOT/backend/.venv/bin/python" ]]; then
    PY="$ROOT/backend/.venv/bin/python"
  elif [[ -x "$ROOT/backend/.venv/Scripts/python.exe" ]]; then
    PY="$ROOT/backend/.venv/Scripts/python.exe"
  else
    PY="python"
  fi
  run_py() { (cd "$ROOT/backend" && "$PY" "$@"); }
fi

echo "==> backend: ruff"
run_py -m ruff check .
run_py -m ruff format --check .
echo "==> backend: mypy"
run_py -m mypy app
echo "==> backend: pytest"
run_py -m pytest -q -p no:cacheprovider
echo "==> backend: alembic offline SQL"
run_py -m alembic upgrade head --sql > /dev/null

echo "==> frontend: lint"
(cd "$ROOT/frontend" && npm run --silent lint)
echo "==> frontend: typecheck"
(cd "$ROOT/frontend" && npm run --silent typecheck)
echo "==> frontend: tests"
(cd "$ROOT/frontend" && npm run --silent test)
echo "==> frontend: format check"
(cd "$ROOT/frontend" && npm run --silent format:check)

echo "All checks passed."
