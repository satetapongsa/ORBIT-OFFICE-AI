#!/usr/bin/env bash
# ORBIT OFFICE AI — back up the database and every stored file.
#
#   bash scripts/backup.sh            # development stack (docker-compose.yml)
#   bash scripts/backup.sh --prod     # production stack (docker-compose.prod.yml + .env.production)
#
# Writes backups/<UTC timestamp>/ with database.dump (pg_dump custom format), files.tar
# (all objects, `python -m app.cli storage-export`) and SHA256SUMS. Old backups are removed
# after BACKUP_KEEP_DAYS (default 14). Copy the folder off the server (see docs/DEPLOYMENT.md).
set -euo pipefail

cd "$(dirname "$0")/.."

compose=(docker compose)
if [[ "${1:-}" == "--prod" ]]; then
  compose=(docker compose -f docker-compose.prod.yml --env-file .env.production)
fi

root="${BACKUP_DIR:-backups}"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="$root/$stamp"
mkdir -p "$target"
chmod 700 "$root" "$target" 2>/dev/null || true

echo "==> database -> $target/database.dump"
"${compose[@]}" exec -T postgres sh -c \
  'pg_dump --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --format=custom --no-owner' \
  > "$target/database.dump"

echo "==> stored files -> $target/files.tar"
"${compose[@]}" exec -T backend python -m app.cli storage-export > "$target/files.tar"

(cd "$target" && sha256sum database.dump files.tar > SHA256SUMS)
echo "==> checksums"
cat "$target/SHA256SUMS"

keep="${BACKUP_KEEP_DAYS:-14}"
find "$root" -mindepth 1 -maxdepth 1 -type d -mtime "+$keep" -print -exec rm -rf {} + || true

echo "Backup complete: $target"
