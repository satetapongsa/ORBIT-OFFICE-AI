#!/usr/bin/env bash
# ORBIT OFFICE AI — end-to-end workflow tests against the running development stack.
#
#   bash scripts/e2e-test.sh
#
# Runs backend/tests/e2e inside the backend container, through the same entry point a browser
# uses (Next.js on http://frontend:3000 by default; ORBIT_E2E_BASE_URL to override, e.g. the
# Nginx proxy http://nginx). Needs the dev seed accounts (`python -m app.cli seed-dev`) and
# SEED_DEV_PASSWORD in .env. Creates data prefixed "E2E"; never run it against production.
set -euo pipefail

cd "$(dirname "$0")/.."

docker compose exec -T \
  -e ORBIT_E2E_BASE_URL="${ORBIT_E2E_BASE_URL:-http://frontend:3000}" \
  -e ORBIT_E2E_DOMAIN="${ORBIT_E2E_DOMAIN:-orbit.example.com}" \
  -e PYTHONDONTWRITEBYTECODE=1 \
  backend python -m pytest -p no:cacheprovider -q -m e2e tests/e2e "$@"
