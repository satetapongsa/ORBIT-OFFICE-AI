# AURA OFFICE AI — Architecture

## 1. System overview

```
                 ┌──────────────────────────── Browser ────────────────────────────┐
                 │  Next.js UI (Thai)  ── same-origin fetch to /api/v1/* (cookies) │
                 └───────────────────────────────┬─────────────────────────────────┘
                                                 │
                          dev: Next.js rewrites  │  prod: Nginx reverse proxy
                                                 ▼
┌───────────────┐   /api/*   ┌──────────────────────────────┐    ┌──────────────────┐
│ Next.js (3000)│──────────▶│  FastAPI backend (8000)      │──▶│ PostgreSQL 17     │
│ App Router    │            │  routes → services → repos   │    │ + pgvector        │
└───────────────┘            │  authN/authZ, ACL, audit     │    └──────────────────┘
                             │  AI provider layer, RAG      │──▶ Redis 7 (broker, cache, rate limit)
                             └──────────────┬───────────────┘──▶ MinIO / S3 (file objects)
                                            │ enqueue
                                            ▼
                             ┌──────────────────────────────┐
                             │ Celery worker(s)             │──▶ PostgreSQL, MinIO, AI provider
                             │ text extraction, chunking,   │
                             │ embeddings, notifications    │
                             └──────────────────────────────┘
                                            │
                                            ▼
                         Configurable AI provider (backend only):
                         Ollama / any OpenAI-compatible API / Anthropic
```

- The **browser only talks to its own origin**. In development, Next.js
  rewrites `/api/*` to the backend; in production, Nginx routes `/api/*` to the
  backend and everything else to the Next.js server. This keeps auth cookies
  first-party, makes `SameSite` cookies work, and avoids CORS for the main app.
- **AI providers are called only from the backend** (API process or worker).
  The frontend never sees provider URLs or keys.
- **Binary files live in object storage** (MinIO locally, any S3-compatible
  store in production). PostgreSQL stores metadata, ACLs, extracted chunks and
  embeddings.

## 2. Repository layout

```
aura-office-ai/
├── frontend/                 Next.js App Router + TypeScript + Tailwind + shadcn/ui
│   ├── app/                  routes and layouts only (thin)
│   ├── components/           shared UI: ui/ (shadcn primitives), layout/ (shell)
│   ├── features/<module>/    module-specific components, hooks, schemas
│   ├── hooks/                cross-module hooks
│   ├── services/             typed API client + per-resource API functions
│   ├── lib/                  utilities, navigation config, query client
│   ├── types/                shared TypeScript types
│   └── tests/                Vitest + Testing Library
├── backend/
│   ├── app/
│   │   ├── api/v1/           FastAPI routers (HTTP only: parse, authorise, delegate)
│   │   ├── api/deps.py       shared dependencies (db session, current user, permissions)
│   │   ├── core/             config, logging, db, errors, middleware, redis, storage
│   │   ├── models/           SQLAlchemy 2.x ORM models
│   │   ├── schemas/          Pydantic request/response models
│   │   ├── repositories/     data access (queries, ACL filters) — no HTTP concerns
│   │   ├── services/         business logic: ai/, rag/, documents/, tasks/, tickets/, reports/
│   │   ├── workers/          Celery app and tasks
│   │   └── main.py           application factory
│   ├── migrations/           Alembic
│   └── tests/                pytest (unit + integration)
├── infra/docker/             Dockerfiles
├── infra/nginx/              reverse-proxy configuration
├── docs/                     project documentation (this folder)
├── scripts/                  helper scripts (dev, checks)
└── docker-compose.yml        local development stack
```

## 3. Backend layering rules

| Layer          | Responsibility                                                    | Must NOT                         |
| -------------- | ----------------------------------------------------------------- | -------------------------------- |
| `api/v1`       | HTTP parsing, status codes, dependency wiring, permission guards  | contain business logic or SQL    |
| `schemas`      | Pydantic input validation and output shaping                      | import ORM sessions              |
| `services`     | Business rules, transactions, audit events, orchestration         | know about HTTP request objects  |
| `repositories` | SQLAlchemy queries, ACL predicates, pagination                    | make authorisation *decisions*   |
| `models`       | Table definitions, relationships, constraints                     | contain business logic           |
| `workers`      | Background jobs calling services with a sync session              | bypass services                  |
| `core`         | Cross-cutting infrastructure                                      | depend on feature modules        |

Request flow: `router → Depends(current_user, require_permission) → service → repository → DB`.

Authorisation is enforced by **both** route-level permission dependencies
(coarse: "may this user call this endpoint?") **and** service/repository-level
checks (fine: "may this user touch *this* record?"). See `SECURITY.md`.

### Database access

- One driver, **psycopg 3**, for everything:
  `postgresql+psycopg://` — async engine for FastAPI, sync engine for Alembic
  and Celery workers.
- One `AsyncSession` per request (`get_db` dependency). Services own the
  transaction boundary (`async with session.begin()` or explicit commit).
- Schema changes only through Alembic migrations. The application never calls
  `create_all()`.

### Errors

All errors are returned in one envelope (see `API_CONVENTIONS.md`). Domain code
raises `AppError` subclasses (`NotFoundError`, `PermissionDeniedError`,
`ConflictError`, `ValidationFailedError`, `ServiceUnavailableError`, …); a global
handler maps them to HTTP responses. Unexpected exceptions are logged with a
request ID and returned as a generic `internal_error` — never a stack trace.

### Logging

`structlog` with JSON output in non-development environments and pretty console
output in development. Every request gets an `X-Request-ID` (accepted from the
client if well-formed, otherwise generated) that is bound to all log lines and
returned in the response. Secrets, passwords and tokens are never logged.

### Background processing

Celery with Redis as broker and result backend. Queues:

| Queue       | Work                                                          |
| ----------- | ------------------------------------------------------------- |
| `default`   | notifications, housekeeping                                   |
| `documents` | text extraction, cleaning, chunking, embedding (Phase 4/7)    |

Tasks must be idempotent (safe to retry) and receive IDs, not ORM objects.

## 4. AI architecture

```
services/ai/
  config.py        provider settings & status (Phase 1)
  providers/       ChatProvider / EmbeddingProvider protocols + adapters (Phase 6)
    openai_compatible.py   Ollama, vLLM, LM Studio, OpenAI, Azure-compatible gateways
    anthropic.py           Claude models via the official Anthropic SDK
  tools/           whitelisted tool registry (Phase 6)
services/rag/      chunking, embedding, permission-filtered retrieval, prompting (Phase 7)
```

- **Provider-independent**: business code depends on `ChatProvider` /
  `EmbeddingProvider` protocols, never on a vendor SDK. Chat and embedding
  providers are configured **separately** (some chat vendors, e.g. Anthropic,
  have no embedding endpoint).
- Configuration via environment variables (`AI_*`, see `.env.example`). If no
  provider is configured, AI endpoints return a clear `ai_not_configured` error
  and the UI shows a configuration message — nothing is faked.
- **Tool calling** uses a fixed registry of backend functions. Each tool
  re-validates the authenticated user, enforces permissions, validates
  arguments with Pydantic, and — if it mutates data — creates an
  `ai_action_requests` row that the user must confirm before execution.
- **RAG retrieval** applies the user's document ACL inside the SQL query that
  selects chunks (see `SECURITY.md §5`). The LLM only ever sees chunks the user
  could open directly. Retrieved text is wrapped as untrusted data in the prompt.

## 5. Frontend architecture

- **App Router** with route groups: `(app)` for the authenticated shell;
  `(auth)` for login (Phase 2).
- **Data fetching**: TanStack Query for client-side server state; all requests
  go through `services/api-client.ts`, which handles the base path, JSON,
  credentials, CSRF header (Phase 2), error-envelope parsing and Zod
  validation of responses.
- **Forms**: React Hook Form + Zod resolvers; schemas mirror backend Pydantic
  models.
- **UI**: shadcn/ui (Radix primitives) + Tailwind + Lucide icons; toast
  notifications via `sonner`. One design system for all modules.
- **Navigation** is defined once (`lib/navigation.ts`) with the permission each
  item requires; the shell filters items by the current user's permissions
  (Phase 2). Hiding is cosmetic — the backend still rejects unauthorised calls.
- **Language**: Thai UI labels, kept in one place per feature. Fonts:
  IBM Plex Sans Thai (Thai + Latin).

## 6. Environments

| Environment   | How it runs                                                              |
| ------------- | ------------------------------------------------------------------------ |
| `development` | `docker compose up` (all services) or local processes + Compose infra    |
| `test`        | pytest/Vitest; integration tests need Postgres/Redis/MinIO from Compose  |
| `production`  | Containers behind Nginx with HTTPS; managed Postgres/Redis/S3 optional (Phase 9) |

Configuration is environment-variable based (`pydantic-settings` on the
backend, `process.env` on the frontend). `.env.example` documents every variable.
