# ORBIT OFFICE AI

**AI-Powered Office Management Platform** — an internal web application for
tasks, documents, IT helpdesk, employee information, analytics and an AI
assistant that answers only from company data the user is authorised to see.

> Status: **all phases (0–9) complete** — dashboard, documents with permission-aware search,
> tasks, employee center, IT helpdesk, notifications (in-app + e-mail), analytics and reports,
> AI assistant with tools and RAG, production deployment. See
> [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md).

## Stack

| Layer      | Technology |
| ---------- | ---------- |
| Frontend   | Next.js 16 (App Router) · React 19 · TypeScript · Tailwind CSS 4 · shadcn/ui (Radix) · TanStack Query · React Hook Form · Zod |
| Backend    | Python · FastAPI · Pydantic 2 · SQLAlchemy 2 · Alembic · psycopg 3 · Celery · structlog |
| Data       | PostgreSQL 17 + pgvector · Redis 7 · MinIO (S3-compatible) |
| AI         | Provider-independent layer: OpenAI-compatible (e.g. Ollama) or Anthropic, configured by environment |
| Infra      | Docker · Docker Compose · Nginx |

## Quick start

```bash
cp .env.example .env
docker compose up --build -d
docker compose exec backend python -m app.cli seed-dev   # development accounts
```

- App: http://127.0.0.1:3000 (opens the dashboard) — sign in as `admin@orbit.example.com` (or `manager@`, `hr@`,
  `it@`, `employee@`) with `SEED_DEV_PASSWORD` from `.env`
- API docs: http://127.0.0.1:8000/api/docs
- Readiness: http://127.0.0.1:8000/api/v1/health

Running without Docker, tests and troubleshooting: [`docs/RUNBOOK.md`](docs/RUNBOOK.md).
Production (HTTPS, first administrator, backups): [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

## Repository layout

```
frontend/      Next.js application
backend/       FastAPI application, Alembic migrations, Celery workers, tests
infra/         Dockerfiles and Nginx configuration
docs/          Architecture, database, API, security, phases, status, decisions, runbook
scripts/       check.sh (all checks), smoke-test.sh, e2e-test.sh (running stack),
               backup.sh / restore.sh
```

## Documentation

| Document | Purpose |
| --- | --- |
| [PROJECT_OVERVIEW](docs/PROJECT_OVERVIEW.md) | Vision, roles, modules |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | System design and layering |
| [DATABASE_DESIGN](docs/DATABASE_DESIGN.md) | Schema plan |
| [API_CONVENTIONS](docs/API_CONVENTIONS.md) | REST conventions, error envelope |
| [SECURITY](docs/SECURITY.md) | AuthN/AuthZ, ACL, AI security |
| [DEVELOPMENT_PHASES](docs/DEVELOPMENT_PHASES.md) | Phase 0–9 plan |
| [PROJECT_STATUS](docs/PROJECT_STATUS.md) | Current state |
| [DECISIONS](docs/DECISIONS.md) | Architecture decision records |
| [RUNBOOK](docs/RUNBOOK.md) | Setup, run, test, troubleshoot |
| [DEPLOYMENT](docs/DEPLOYMENT.md) | Production deployment, backups, known risks |

## Security

No real credentials belong in this repository. `.env` and `.env.production` are git-ignored;
`.env.example` and `.env.production.example` contain placeholders only. See
[`docs/SECURITY.md`](docs/SECURITY.md).
