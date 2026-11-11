# AURA OFFICE AI — PROJECT STATUS

**Current Phase:** Phase 2 — Authentication & Authorization — ✅ **COMPLETE** (verified 2026-11-11). Next: Phase 3.
**Last Updated:** 2026-11-11

## Completed

### Phase 0 — Project initialization & architecture
- Workspace inspected (was empty); git repository initialised (`main`).
- Documentation: `PROJECT_OVERVIEW`, `ARCHITECTURE`, `DATABASE_DESIGN`, `API_CONVENTIONS`,
  `SECURITY`, `DEVELOPMENT_PHASES`, `PROJECT_STATUS`, `DECISIONS` (ADR-001…022), `RUNBOOK`,
  root `README.md`, session instructions file.

### Phase 1 — Foundation
- **Backend** (`backend/`): FastAPI app factory; `pydantic-settings` config with production
  safety checks (rejects default JWT/storage secrets, wildcard CORS, `debug` in prod);
  structlog JSON/console logging with secret redaction; request-ID middleware + security headers;
  global error envelope (Thai user-facing messages, no stack traces); async + sync SQLAlchemy
  engines (psycopg 3); Redis client; S3/MinIO client with dev bucket auto-create (bounded so it
  never blocks startup); Celery app with `default`/`documents` queues and `system.ping` task;
  ORM base with naming convention, UUID PK, timestamp and soft-delete mixins.
- **Alembic**: configured from app settings; migration `0001` enables `vector` and `pg_trgm`.
- **Health API**: `GET /api/v1/health/live` (liveness), `GET /api/v1/health` (readiness: DB +
  pgvector, Redis, object storage in parallel with timeout; AI chat/embedding configuration
  reported as optional without contacting providers; 503 when a required component fails).
- **AI configuration interface**: `AI_CHAT_*` / `AI_EMBEDDING_*` settings, providers
  `disabled | openai_compatible | anthropic` with validation (no provider calls yet).
- **Frontend** (`frontend/`): Next.js 16 + shadcn/ui (Radix); Thai UI with IBM Plex Sans Thai;
  application shell (desktop sidebar, mobile drawer, header with live system-status indicator,
  skip link); navigation config with required permission + delivery phase per module
  (unbuilt modules are shown disabled with "เร็วๆ นี้", not as links); typed API client with
  error-envelope parsing and Zod response validation; TanStack Query setup; System Status page
  showing real readiness data with loading skeleton, error state with retry, toast feedback;
  reusable `PageHeader`, `ErrorState`, `EmptyState`; Thai 404 page.
- **Infrastructure**: `docker-compose.yml` (postgres/pgvector 17, redis 7.4, minio, migrate,
  backend, worker, frontend, optional nginx profile), backend & frontend multi-stage Dockerfiles
  (dev + non-root prod), Nginx reverse-proxy config, `.env.example`, `.gitignore`,
  `.dockerignore`, `.editorconfig`, `.gitattributes`.
- **Scripts**: `scripts/check.sh` (all static checks + tests), `scripts/smoke-test.sh` (running stack).
- **Verification fixes (2026-11-11)**: object storage image switched to digest-pinned
  `pgsty/minio` (upstream `minio/minio` no longer published, ADR-013); selector event-loop
  factory + startup warning for native Windows runs (async psycopg, ADR-014); host defaults use
  `127.0.0.1` instead of `localhost` (ADR-015); Nginx de-duplicates security headers;
  integration tests extended (Redis round trip, S3 put/get/delete, Celery ping).

### Phase 2 — Authentication & Authorization
- **Data model** (migration `0002`): `departments`, `users`, `roles`, `permissions`,
  `user_roles`, `role_permissions`, `user_sessions`, `password_reset_tokens`, `audit_logs`
  (append-only via DB trigger), and the document ACL foundation (`documents` core + `document_acl`).
- **Security core**: Argon2id hashing with rehash-on-login, password policy, HS256 access JWT
  (15 min, `sid` = session family), opaque hashed refresh tokens with rotation, reuse detection
  (family revocation) and a 10 s parallel-tab grace window, HttpOnly/SameSite cookies,
  double-submit CSRF, Bearer support for API clients, Redis login rate limiting (per e-mail/IP).
- **RBAC**: 38-permission catalogue in code (`app/core/permissions.py`), 5 system roles,
  `python -m app.cli sync-rbac` (run by the Compose `migrate` service), custom roles,
  `require_permissions(...)` guards, permissions re-read every request (instant revocation),
  escalation guards (grant only what you hold), locked ADMIN role, last-admin protection.
- **APIs**: `/auth/*` (login, refresh, logout, me, change-password, password reset),
  `/users`, `/departments`, `/roles`, `/permissions`, `/audit-logs` — see `API_CONVENTIONS.md`.
- **Document ACL**: single SQL predicate `accessible_documents_condition` /
  `can_access_document` covering owner, COMPANY/DEPARTMENT visibility, user/department/role
  grants, VIEW/EDIT/MANAGE levels, `documents:manage` override, soft deletion.
- **Audit log**: 20 action types (auth, users, roles, departments), written in the same
  transaction; passwords/tokens never stored; `GET /audit-logs` with filters.
- **Dev seed**: `python -m app.cli seed-dev` (development only, idempotent): 5 departments and
  one account per role (`*@aura.example.com`, password `SEED_DEV_PASSWORD`).
- **Frontend**: login, forgot-password, reset-password pages; account page with change-password;
  `AuthGate` redirecting to `/login?next=…` (open-redirect safe); API client with CSRF header and
  single-flight refresh-and-retry; user menu with logout; sidebar filtered by permissions;
  Thai validation messages (React Hook Form + Zod).
- **Fixes found while verifying**: Next.js dev server needed `allowedDevOrigins: ["127.0.0.1"]`
  (app never hydrated otherwise); `instant = false` on the client-gated `(app)` layout;
  `.local` e-mail domains rejected by the validator → `example.com` (ADR-022); refresh with no
  session now answers 401 instead of a CSRF 403, and the client skips that call.

## In Progress
- Nothing. Phase 2 is complete.

## Remaining
- Phases 3–9 per `docs/DEVELOPMENT_PHASES.md`.
- User/role administration UI (APIs done) — planned with the Employee Center (Phase 5).
- E-mail delivery for password-reset links (needs a mail provider/SMTP decision).

## Technical Decisions
See `docs/DECISIONS.md`. Key ones: same-origin API via proxy (ADR-002); psycopg 3 for async and
sync (ADR-003); permission-based RBAC with roles as data (ADR-005); ACL evaluated at query time
for RAG (ADR-006); provider-independent AI with separate chat/embedding config (ADR-007);
S3-generic storage code (ADR-009) with digest-pinned `pgsty/minio` (ADR-013); selector event
loop on native Windows (ADR-014); `127.0.0.1` host defaults (ADR-015); session model with
rotating refresh-token families (ADR-016); CSRF double-submit (ADR-017); grant-only-what-you-hold
(ADR-018); ACL foundation in Phase 2 (ADR-019); isolated test database (ADR-020); client-side
session gate (ADR-021).

## Tests
### Phase 2 verification — 2026-11-11
Backend checks ran **inside the backend container** (Python 3.13) because Windows Application
Control now blocks the host venv's compiled wheels (see Known Issues).

| Check (command) | Result |
| --- | --- |
| `CHECK_BACKEND_IN_DOCKER=1 AURA_RUN_INTEGRATION=1 bash scripts/check.sh` | ✅ all passed |
| ruff check + format, mypy strict (66 files) | ✅ clean |
| `pytest` (container, incl. integration + DB tests) | ✅ **82 passed**, 1 skipped (Windows-only event-loop test) |
| — `tests/api/test_auth.py` | ✅ 16: cookies/flags, generic errors, inactive users, 401 on all protected endpoints, Bearer, tampered JWT, CSRF, refresh rotation, reuse detection, parallel-tab grace, logout revocation, rate limit 429, change password, reset flow |
| — `tests/api/test_authorization.py` | ✅ 22: role × endpoint matrix for all 5 roles, HR vs privileged roles, grant-only-what-you-hold, locked ADMIN, last-admin protection, instant role revocation, deactivation sign-out, custom roles, audit trail, DB append-only trigger, conflicts, pagination |
| — `tests/api/test_document_access.py` | ✅ 7: every ACL rule evaluated by PostgreSQL |
| `alembic upgrade head` / `alembic check` / offline SQL | ✅ `0002 (head)`, no drift; `downgrade 0001` + `upgrade` round trip |
| Frontend `vitest` | ✅ **22 passed** (CSRF header, refresh-and-retry, no refresh without session, open-redirect guard, login form validation/errors/redirect, permission-filtered nav) |
| Frontend lint, typecheck, Prettier, `next build` | ✅ (`/login`, `/forgot-password`, `/reset-password`, `/account` prerendered) |
| `docker compose up -d` + `migrate` (`alembic` + `sync-rbac`) | ✅ 38 permissions, 5 roles; second run: no changes |
| `docker compose exec backend python -m app.cli seed-dev` | ✅ 5 accounts; re-run creates 0; refused when `ENVIRONMENT` ≠ development |
| `bash scripts/smoke-test.sh` | ✅ passed |
| Browser (Docker frontend → backend) | ✅ `/account` → `/login?next=%2Faccount` → sign-in as employee → back to `/account`; logout → 204, next visit redirected to login; employee sidebar has no "ตั้งค่า", admin sidebar does |

### Phase 2 acceptance criteria
| Criterion | Status |
| --- | --- |
| A user can log in and log out | ✅ API tests + browser |
| Unauthenticated users cannot access protected APIs | ✅ 401 on every protected endpoint (test) |
| Role permissions are enforced by the backend; unauthorized requests rejected | ✅ 403 matrix for all roles, escalation guards |
| Frontend navigation reflects permissions | ✅ unit test + browser (employee vs admin) |
| Authentication and authorization tests pass | ✅ 82 backend / 22 frontend |

### Phase 1 verification in Docker — 2026-11-11
Environment: Windows 11, Docker Desktop (engine 29.9.3, Compose v5.7.0, WSL2, 12 CPU, ~8 GB),
host Python 3.15.2 / Node 26.13; containers Python 3.13.18 / Node 22.

| # | Check (command) | Result |
| --- | --- | --- |
| 1 | `docker compose config --quiet` | ✅ valid; 8 services (nginx behind `proxy` profile) |
| 2 | `docker compose build` (dev) + `docker build --target prod` (both) | ✅ dev backend 546 MB, dev frontend 216 MB, prod backend 397 MB, prod frontend 308 MB |
| 3 | `docker compose down` → `docker compose up -d` (clean start) | ✅ all services up in 17 s in dependency order; `migrate` exits 0; postgres/redis/minio/backend healthy |
| 4 | PostgreSQL + pgvector (`psql`) | ✅ PostgreSQL 17.11; extensions `vector 0.8.7`, `pg_trgm 1.6` installed by migration |
| 5 | Redis (`redis-cli ping`, integration test) | ✅ Redis 7.4.12 `PONG`; set/get/delete round trip |
| 6 | MinIO / S3 (`mc ls`, integration test) | ✅ `pgsty/minio` RELEASE.2026-08-04 healthy; bucket `aura-documents` auto-created; S3 put/get/delete round trip via boto3 |
| 7 | Celery worker | ✅ ready on `default` + `documents`; `system.ping` round trip API→Redis→worker→result |
| 8 | Alembic | ✅ `upgrade head` → `0001 (head)`; `downgrade base` + `upgrade head` round trip |
| 9 | Integration tests | ✅ container `pytest`: 31 passed, 1 skipped (Windows-only test); host `AURA_RUN_INTEGRATION=1 pytest`: 32 passed |
| 10 | `bash scripts/smoke-test.sh` | ✅ liveness, readiness **200**, frontend page, frontend→backend proxy |
| 11 | Frontend + backend via Docker | ✅ backend container healthy; frontend container serves Thai UI with real readiness data; `/api` proxied to the `backend` service |
| — | Nginx (`--profile proxy`) on :8080 | ✅ page 200, `/api/v1/health` 200, `nginx -t` ok, one copy of each security header |
| — | Prod images run | ✅ non-root `aura`, healthcheck healthy, 4 uvicorn workers, standalone frontend proxy 200 |
| — | Native Windows backend (RUNBOOK option B) | ✅ with `--loop app.core.event_loop:selector_event_loop` readiness 200; without it the `windows_proactor_event_loop` warning is logged |
| — | `scripts/check.sh` | ✅ ruff, mypy (36 files), pytest 27 passed / 5 skipped (integration), alembic SQL, ESLint, tsc, Vitest 12 passed, Prettier |
| — | `npm run build` | ✅ compiled |

### Problems found during verification and fixed
1. `minio/minio` image no longer exists on Docker Hub (quay.io: 401) → digest-pinned `pgsty/minio` (ADR-013).
2. Native Windows backend could not reach PostgreSQL (`InterfaceError`, async psycopg on the Proactor loop) → selector loop factory + startup warning (ADR-014).
3. Host connections via `localhost` stalled on IPv6 (integration run 150 s) → `127.0.0.1` defaults (ADR-015); run now ~1.5 s.
4. Nginx duplicated `X-Frame-Options` / `X-Content-Type-Options` / `Referrer-Policy` → upstream copies hidden.
5. Verification commands in docs used `&&`, which Windows PowerShell 5.1 rejects → one command per line.

### Phase 1 acceptance criteria (actual)
| Criterion | Status |
| --- | --- |
| Development environment starts with Docker Compose | ✅ |
| Frontend can load | ✅ (`next dev`, Docker dev, prod standalone, behind Nginx) |
| Backend can start | ✅ (Docker dev + prod, native Windows) |
| Database connection works | ✅ |
| Redis connection works | ✅ |
| MinIO can start | ✅ |
| Health endpoints work | ✅ live 200, readiness 200 with all required components ok |
| Environment variables documented | ✅ `.env.example` |
| Basic test suite runs | ✅ backend 32 (host, with integration), frontend 12 |
| README contains setup instructions | ✅ |

**Phase 1 is accepted. Phase 2 may start.**

### Earlier runs (2026-11-10, before Docker was available)
Commands actually executed (Windows 11, Python 3.15.2, Node 26.13):

| Command | Result |
| --- | --- |
| `scripts/check.sh` | ✅ all passed |
| `backend: ruff check . && ruff format --check .` | ✅ passed |
| `backend: mypy app` (strict) | ✅ no issues (35 files) |
| `backend: pytest` | ✅ 24 passed, 2 skipped (integration tests need running services) |
| `backend: alembic upgrade head --sql` | ✅ renders migration 0001 |
| `frontend: npm run lint` | ✅ passed |
| `frontend: npm run typecheck` | ✅ passed |
| `frontend: npm run test` (Vitest) | ✅ 12 passed (3 files) |
| `frontend: npm run format:check` | ✅ passed |
| `frontend: npm run build` | ✅ compiled; `/` and `/_not-found` prerendered |
| `npm audit --omit=dev` | ✅ 0 vulnerabilities (dev-only: shadcn CLI transitive advisories) |
| Manual: backend `uvicorn` + frontend `next dev` locally | ✅ `/health/live` 200 with security headers; `/api/v1/health` via Next proxy → 503 report (no infra running, as expected); UI renders status in Thai on desktop and mobile; mobile drawer works |
| Compose YAML parse (PyYAML) | ✅ 8 services, container hostnames resolved |
| `docker compose up` | ⚠️ **not executed** — Docker not installed on this machine |
| `pytest -m integration` with `AURA_RUN_INTEGRATION=1` | ⚠️ **not executed** — needs PostgreSQL/Redis/MinIO |

## Known Issues
1. **Host Python venv blocked by Windows Application Control** (since the 2026-11-11 restart):
   `DLL load failed ... An Application Control policy has blocked this file` for compiled wheels
   (SQLAlchemy). Not bypassed. Backend commands run in the container
   (`CHECK_BACKEND_IN_DOCKER=1 scripts/check.sh`, `docker compose exec backend …`).
2. Password-reset e-mails are not delivered yet (no mail provider). In development the link is
   written to the backend log; elsewhere a warning is logged. Needs an SMTP/provider decision.
3. Login rate limiter fails open if Redis is unavailable (logged); review in Phase 9.
4. Object storage uses a third-party MinIO build (`pgsty/minio`, digest-pinned) — ADR-013.
5. Readiness endpoint is unauthenticated and lists component status; review in Phase 9.
6. User/role/department management has APIs but no admin UI yet ("ตั้งค่า" shows "เร็วๆ นี้"
   for admins); planned with Phase 5.
7. The session gate is client-side (pages render after `/auth/me`); every API call is still
   authorised by the backend. Server-side gating can be added with `proxy.ts` later (ADR-021).
8. Next.js dev server writes `frontend/AGENTS.md`; ignored by the global git excludes.
9. The `worker` container lists `8000/tcp` (inherited `EXPOSE`); cosmetic.

## Next Phase
**Phase 3 — Dashboard & Application UI**: dashboard with summary cards, charts, recent
activity and notification preview from real, permission-scoped APIs; role-aware menus;
loading/error/empty states; responsive navigation.

## Next Command
Start the stack (one command per line in PowerShell; the smoke test via Git Bash):

```powershell
docker compose up -d
bash scripts/smoke-test.sh
```

Then start the next session with:

```
Continue AURA OFFICE AI: read docs/PROJECT_STATUS.md and docs/DEVELOPMENT_PHASES.md, then execute PHASE 3 — DASHBOARD & APPLICATION UI as defined in docs/DEVELOPMENT_PHASES.md.
```

## Report format (end of every phase, in Thai)
1. Completed · 2. Files Created or Modified · 3. Database Changes · 4. API Changes · 5. Tests ·
6. How to Run · 7. Known Issues · 8. Project Status · 9. Next Phase · 10. Next Command
