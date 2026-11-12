# ORBIT OFFICE AI — Runbook

Commands assume the repository root unless stated otherwise. On Windows use Git
Bash (paths with `/`) or adapt to PowerShell.

> **Windows PowerShell 5.1:** `&&` is not supported — run chained commands one per
> line (or `A; if ($?) { B }`). Run the `.sh` scripts with `bash scripts/<name>.sh`
> (Git Bash). First confirm Docker works: `docker version` must print both a
> **Client** and a **Server** section.

## 1. Prerequisites

| Tool            | Version                 | Needed for                         |
| --------------- | ----------------------- | ---------------------------------- |
| Docker Desktop / Engine + Compose v2.24+ | current | full stack (`docker compose`) |
| Node.js         | ≥ 20.9 (22 LTS used in images) | frontend local dev          |
| Python          | ≥ 3.12                  | backend local dev                  |
| Ollama (optional) | current               | free local AI provider (Phase 6+)  |

## 2. First-time setup

```bash
cp .env.example .env            # local development defaults; edit as needed
```

### Option A — everything in Docker (recommended)

```bash
docker compose up --build
```

| URL                              | Service                          |
| -------------------------------- | -------------------------------- |
| http://127.0.0.1:3000            | Frontend (Next.js dev server)    |
| http://127.0.0.1:8000/api/docs   | Backend OpenAPI (Swagger UI)     |
| http://127.0.0.1:8000/api/v1/health | Readiness report              |
| http://127.0.0.1:9001            | MinIO console (`MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD`) |

The `migrate` service runs `alembic upgrade head` and `python -m app.cli sync-rbac`
(permission catalogue + system roles, idempotent) before `backend` and `worker` start.

Create the development accounts once (development only — refused in other environments):

```bash
docker compose exec backend python -m app.cli seed-dev
```

This creates five departments and one account per system role:
`admin@`, `manager@`, `hr@`, `it@` and `employee@orbit.example.com`, all with the password
`SEED_DEV_PASSWORD` from your `.env`. Sign in at http://127.0.0.1:3000/login.

With the reverse proxy:

```bash
docker compose --profile proxy up --build     # http://127.0.0.1:8080
```

### Option B — infrastructure in Docker, apps as local processes

```bash
docker compose up -d postgres redis minio

# backend
cd backend
python -m venv .venv
source .venv/Scripts/activate        # Windows Git Bash; Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
python -m app.cli sync-rbac
python -m app.cli seed-dev           # optional development accounts
uvicorn app.main:app --reload        # Linux/macOS — http://127.0.0.1:8000
# Windows (async psycopg needs a selector event loop, see ADR-014):
uvicorn app.main:app --reload --loop app.core.event_loop:selector_event_loop

# worker (second terminal, backend/ with venv active)
celery -A app.workers.celery_app worker --loglevel=INFO -Q default,documents --pool=solo   # --pool=solo on Windows

# frontend (third terminal)
cd frontend
npm install
npm run dev                          # http://127.0.0.1:3000, proxies /api → BACKEND_INTERNAL_URL
```

The backend reads `../.env` (repository root) and then `backend/.env`.

## 3. Verification

```bash
scripts/smoke-test.sh                # liveness, readiness (expects 200), frontend page, proxy
```

Celery round trip (backend venv active):

```bash
python -c "from app.workers.tasks import ping; print(ping.delay().get(timeout=10))"
```

## 4. Tests and checks

```bash
scripts/check.sh                                       # everything below, backend via local venv
CHECK_BACKEND_IN_DOCKER=1 ORBIT_RUN_INTEGRATION=1 scripts/check.sh   # backend inside the container
```

Database-backed tests (auth, RBAC, document ACL) use a separate database,
`orbit_office_test`, created and migrated automatically; they never touch development
data and are skipped (with a reason) only if PostgreSQL is unreachable.

Backend (in `backend/`, venv active):

```bash
pytest                               # unit tests; integration tests are skipped
ORBIT_RUN_INTEGRATION=1 pytest -m integration   # needs postgres/redis/minio + migrations
ruff check . && ruff format --check .
mypy app
alembic upgrade head --sql > /dev/null         # offline migration render check
```

Frontend (in `frontend/`):

```bash
npm run test
npm run lint
npm run typecheck
npm run format:check
npm run build
```

## 5. Database migrations

```bash
cd backend
alembic revision --autogenerate -m "add users and roles"   # review the generated file!
alembic upgrade head
alembic downgrade -1                 # development only — DROPS the tables of that revision
alembic history --verbose
```

Downgrades drop tables and their data. To test a migration round trip, point Alembic at the
**test** database, not the dev database the containers use:

```bash
docker compose exec backend sh -c 'DATABASE_URL="${DATABASE_URL%/*}/orbit_office_test" alembic downgrade -1'
docker compose exec backend sh -c 'DATABASE_URL="${DATABASE_URL%/*}/orbit_office_test" alembic upgrade head'
```

Rules: never edit an applied migration; never use `create_all()`; review every
autogenerated migration (pgvector types, CHECK constraints, server defaults).

## 5a. Enabling the AI assistant (Phase 6)

The assistant stays "not configured" until a chat provider is set in `.env`, then the backend
is recreated (`docker compose up -d backend`).

- **Local (free):** install Ollama on the host, `ollama pull qwen3:8b`, then
  `AI_CHAT_PROVIDER=openai_compatible`, `AI_CHAT_MODEL=qwen3:8b`,
  `AI_CHAT_BASE_URL=http://host.docker.internal:11434/v1` (from containers). Choose a model
  that supports tool calling.
- **Anthropic:** `AI_CHAT_PROVIDER=anthropic`, `AI_CHAT_MODEL=claude-opus-5-5`,
  `AI_CHAT_API_KEY=<your key>` (never commit it). `AI_CHAT_TEMPERATURE` is ignored for Claude.

Check with `GET /api/v1/ai/status` (or the "ผู้ช่วย AI" page header shows the model).

**Semantic document search (Phase 7, optional):** `ollama pull bge-m3`, then
`AI_EMBEDDING_PROVIDER=openai_compatible`, `AI_EMBEDDING_MODEL=bge-m3`,
`AI_EMBEDDING_BASE_URL=http://host.docker.internal:11434/v1` (1024 dimensions — other sizes are
refused). Recreate backend **and** worker, then index existing documents:

```bash
docker compose exec backend python -m app.cli reindex-documents --all
```

Without an embedding provider, content search and the assistant still work with keyword
(trigram) search.

## 5b. E-mail (Phase 8)

In Docker, backend and worker send mail to **Mailpit** (inbox at http://127.0.0.1:8025),
so nothing leaves the machine. Notification e-mails are sent by the worker after the change is
committed; each user chooses the types on "บัญชีของฉัน". For a real server set `SMTP_HOST`,
`SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_STARTTLS`/`SMTP_SSL` (for
containers: `SMTP_CONTAINER_HOST`, `SMTP_CONTAINER_PORT`, `SMTP_CONTAINER_STARTTLS`) and
recreate backend and worker. With `SMTP_HOST` empty, e-mail is skipped and reset links are
logged in development only.

PDF reports need the WeasyPrint system libraries and Thai fonts from the backend image; after
pulling Phase 8 rebuild it: `docker compose up -d --build backend worker`.

## 6. Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| Readiness `database: pgvector extension missing` | Run `alembic upgrade head` (migration `0001` enables `vector`, `pg_trgm`). |
| Readiness `database: unavailable` | PostgreSQL not running or wrong `DATABASE_URL`; `docker compose ps`, `docker compose logs postgres`. |
| Readiness `redis` / `object_storage` `timed out` | Service not running or port blocked; check `REDIS_URL`, `STORAGE_ENDPOINT_URL`. |
| Backend startup logs `storage_bucket_init_failed` | Object storage unreachable at startup; the API still starts, readiness shows the problem. |
| Frontend shows "ไม่สามารถเชื่อมต่อกับเซิร์ฟเวอร์ API ได้" | Backend not running or `BACKEND_INTERNAL_URL` wrong (restart `npm run dev` after changing it). |
| Containers cannot reach Ollama on the host | Use `http://host.docker.internal:11434/v1` in `.env` for `AI_*_BASE_URL`. |
| Celery on Windows hangs or errors | Use `--pool=solo` for local (non-Docker) workers. |
| `docker compose` complains about `env_file` `required` | Upgrade Docker Compose to ≥ 2.24. |
| MinIO image not found (`pull access denied`) | Upstream `minio/minio` images are no longer published; Compose uses the digest-pinned `pgsty/minio` build (ADR-013). Override with `MINIO_IMAGE`. |
| Native Windows backend: readiness `database: unavailable`, log `windows_proactor_event_loop` | Start uvicorn with `--loop app.core.event_loop:selector_event_loop` (ADR-014). |
| Host processes on Windows take seconds/minutes to connect | Use `127.0.0.1`, not `localhost`, in `.env` (ports are published on IPv4 only; ADR-015). |
| Login/app page stays on a grey skeleton; console shows `/_next/hmr` blocked | The dev server only trusts `localhost`; `allowedDevOrigins: ["127.0.0.1"]` is set in `next.config.ts` — restart the frontend after changing it. |
| Host venv: `DLL load failed ... An Application Control policy has blocked this file` | Windows Smart App Control / WDAC blocks unsigned compiled wheels. Do not disable it for this project; run backend commands in the container (`docker compose exec backend …`, `CHECK_BACKEND_IN_DOCKER=1 scripts/check.sh`). |
| `seed-dev refused: ENVIRONMENT must be 'development'` | Intended: development accounts are never created in other environments. |
| Login returns 429 | Login rate limit (10 attempts / 15 min per e-mail). Wait for `Retry-After`, or in development `docker compose exec redis redis-cli --scan --pattern 'orbit:ratelimit:*'` to inspect. |
| Next.js dev server does not pick up edits inside Docker on Windows | `WATCHPACK_POLLING=true` is set in Compose, but Turbopack in the container still missed host edits during Phase 3 — run `docker compose restart frontend`, or run `npm run dev` on the host for UI work. |
| Dev overlay: `Could not validate that a segment in your UI has instant navigation` | Pages under `app/(app)` must export `instant = false` (they render after the client-side session check, ADR-027). |
| `/` returns 307 | Intended: the home page redirects to `/dashboard`; system status is at `/system-status`. |
| Uploads > 10 MB fail with a plain "Internal Server Error" and the frontend log says `Request body exceeded 10MB` | `experimental.proxyClientMaxBodySize` in `next.config.ts` must be ≥ `UPLOAD_MAX_BYTES`; restart the frontend after changing it. |
| Documents stay "รอประมวลผล" (PENDING) | The worker is down or was not restarted after backend changes (it has no auto-reload): `docker compose restart worker`, then "ประมวลผลใหม่" on the document or `docker compose logs worker`. |
| Upload returns 503 "ไม่สามารถบันทึกไฟล์ได้" | Object storage unreachable — check `docker compose ps minio` and `STORAGE_*` settings. |
| Assistant page says "ยังไม่ได้ตั้งค่าผู้ให้บริการ AI" / API `503 ai_not_configured` | No valid chat provider (`AI_CHAT_PROVIDER`, `AI_CHAT_MODEL`, and base URL or API key) — see §5a; recreate the backend after editing `.env`. |
| Assistant answers appear all at once instead of streaming | A proxy is compressing or buffering the stream; the API sends `Cache-Control: no-transform` and `X-Accel-Buffering: no` — keep them when adding proxies. |
| Assistant says "ผู้ให้บริการ AI ไม่ตอบสนอง" | Provider unreachable or timed out (`AI_REQUEST_TIMEOUT_SECONDS`); from Docker use `host.docker.internal` for host services. `docker compose logs backend` shows the status code (never the body). |
| "ส่งข้อความถี่เกินไป" (429) | Per-user chat limit `AI_CHAT_RATE_LIMIT_MESSAGES` per `AI_CHAT_RATE_LIMIT_WINDOW_SECONDS`. |
| A proposed change shows "หมดเวลายืนยัน" | Actions expire after `AI_ACTION_TTL_MINUTES`; ask the assistant to prepare it again. |
| Content search finds nothing in an old document | It was uploaded before Phase 7 or the worker was down: `docker compose exec backend python -m app.cli reindex-documents`. The version's "ค้นหาในเนื้อหาได้ / รอสร้างดัชนีค้นหา" label shows the state. |
| Version shows "ค้นหาได้เฉพาะตามคำ" (index FAILED) | The embedding provider failed during indexing; fix it and run `reindex-documents`. |
| Backend refuses to start: `AI_EMBEDDING_DIMENSIONS must be 1024` | The vector column is fixed at 1024 (ADR-042); use a 1024-dimension model such as `bge-m3`. |
| A task gives "ไม่พบงาน" although it exists | Intended when you cannot see it (ADR-033): you are not the creator/assignee and do not manage that department. |
| Assigning a colleague fails with "มอบหมายได้เฉพาะพนักงานในแผนกของงาน" | Without `tasks:manage_all` assignees must be in the task's department; check the person's department in the Employee Center. |
| Employee profile shows no "ข้อมูลบุคคล" card | Intended without `employees:read_sensitive` (except on your own profile). |
| Dev data from Phase 5 tables disappeared after a migration test | `alembic downgrade` was run against the dev database; use the test database (§5). |

## 7. Resetting local data (destructive)

```bash
docker compose down -v               # deletes postgres, redis, minio volumes
```

## 7a. Backups, clean-up and end-to-end tests (development)

```bash
bash scripts/backup.sh                                  # backups/<stamp>/ (git-ignored)
bash scripts/restore.sh backups/<stamp> --database orbit_restore_check --bucket orbit-restore-check
docker compose exec backend python -m app.cli purge --dry-run
bash scripts/e2e-test.sh                                # needs seed-dev accounts
```

The `beat` service runs the daily clean-up; restart `worker` and `beat` after backend changes.
`e2e-test.sh` writes data titled "E2E …" into the development database.

## 8. Production

See `docs/DEPLOYMENT.md` (configuration, TLS, first administrator, updates, backups and
recovery, known risks).
