#!/usr/bin/env bash
# ORBIT OFFICE AI — restore a backup made by scripts/backup.sh.
#
# Verification restore (safe; live data untouched): restore into another database and bucket
#   bash scripts/restore.sh backups/<stamp> --database orbit_restore_check --bucket orbit-restore-check
#
# Full restore (DESTRUCTIVE: replaces the live database and re-uploads every file)
#   bash scripts/restore.sh backups/<stamp> --yes [--prod]
set -euo pipefail

cd "$(dirname "$0")/.."

usage() {
  sed -n '2,9p' "$0"
  exit 2
}

[[ $# -ge 1 ]] || usage
source_dir="$1"
shift
database=""
bucket=""
confirmed=0
compose=(docker compose)
while [[ $# -gt 0 ]]; do
  case "$1" in
    --database) database="$2"; shift 2 ;;
    --bucket) bucket="$2"; shift 2 ;;
    --yes) confirmed=1; shift ;;
    --prod) compose=(docker compose -f docker-compose.prod.yml --env-file .env.production); shift ;;
    *) usage ;;
  esac
done

[[ -f "$source_dir/database.dump" && -f "$source_dir/files.tar" ]] || {
  echo "restore: $source_dir must contain database.dump and files.tar" >&2
  exit 2
}
echo "==> verifying checksums"
(cd "$source_dir" && sha256sum --check --quiet SHA256SUMS)

verification=0
if [[ -n "$database" || -n "$bucket" ]]; then
  [[ -n "$database" && -n "$bucket" ]] || { echo "restore: give both --database and --bucket" >&2; exit 2; }
  [[ "$database" =~ ^[a-z_][a-z0-9_]{0,62}$ ]] || { echo "restore: invalid database name" >&2; exit 2; }
  verification=1
elif [[ "$confirmed" -ne 1 ]]; then
  echo "restore: a full restore replaces ALL live data; re-run with --yes to confirm," >&2
  echo "         or use --database/--bucket for a verification restore." >&2
  exit 2
fi

psql_admin=("${compose[@]}" exec -T postgres sh -c)

if [[ "$verification" -eq 0 ]]; then
  echo "==> stopping application services"
  "${compose[@]}" stop backend worker beat frontend
  database_expr='$POSTGRES_DB'
else
  database_expr="$database"
fi

echo "==> recreating database $database_expr"
"${psql_admin[@]}" "psql --username=\"\$POSTGRES_USER\" --dbname=postgres -v ON_ERROR_STOP=1 \
  -c \"DROP DATABASE IF EXISTS \\\"$database_expr\\\" WITH (FORCE)\" \
  -c \"CREATE DATABASE \\\"$database_expr\\\" OWNER \\\"\$POSTGRES_USER\\\"\""

echo "==> restoring database"
"${psql_admin[@]}" "pg_restore --username=\"\$POSTGRES_USER\" --dbname=\"$database_expr\" --no-owner --exit-on-error" \
  < "$source_dir/database.dump"

echo "==> restoring stored files"
if [[ "$verification" -eq 1 ]]; then
  "${compose[@]}" exec -T -e STORAGE_BUCKET="$bucket" backend python -m app.cli storage-import \
    < "$source_dir/files.tar"
else
  "${compose[@]}" run --rm -T --no-deps backend python -m app.cli storage-import \
    < "$source_dir/files.tar"
  echo "==> starting application services"
  "${compose[@]}" up -d backend worker beat frontend
fi

echo "Restore complete from $source_dir"
