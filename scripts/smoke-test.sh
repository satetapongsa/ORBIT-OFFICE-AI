#!/usr/bin/env bash
# Smoke-test a running stack (docker compose up, or local processes).
# Usage: scripts/smoke-test.sh [base_url]   default: http://127.0.0.1:3000
set -euo pipefail
BASE="${1:-http://127.0.0.1:3000}"
API="${API_URL:-http://127.0.0.1:8000}"

fail() { echo "FAIL: $*" >&2; exit 1; }

echo "==> backend liveness ($API)"
curl -fsS "$API/api/v1/health/live" | grep -q '"status":"ok"' || fail "liveness"

echo "==> backend readiness"
code=$(curl -s -o /tmp/aura-ready.json -w '%{http_code}' "$API/api/v1/health")
cat /tmp/aura-ready.json; echo
[[ "$code" == "200" ]] || fail "readiness returned HTTP $code"

echo "==> frontend page ($BASE)"
curl -fsS "$BASE/" | grep -q "AURA OFFICE AI" || fail "frontend page"

echo "==> frontend → backend proxy"
curl -fsS "$BASE/api/v1/health/live" | grep -q '"status":"ok"' || fail "proxy"

echo "Smoke test passed."
