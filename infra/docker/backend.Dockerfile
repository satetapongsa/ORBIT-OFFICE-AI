# syntax=docker/dockerfile:1.7
# ORBIT OFFICE AI — backend image (API, Celery worker, migrations).
# Build context: repository root.

ARG PYTHON_VERSION=3.13

FROM python:${PYTHON_VERSION}-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app
WORKDIR /app
RUN groupadd --system orbit && useradd --system --gid orbit --home-dir /app --no-create-home orbit
# PDF reports (WeasyPrint): Pango/HarfBuzz for correct Thai shaping, plus Thai fonts.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-thai-tlwg \
    && rm -rf /var/lib/apt/lists/*
COPY backend/pyproject.toml ./pyproject.toml
# Install dependencies from pyproject.toml without installing the app package itself,
# so the source tree (copied or bind-mounted at /app) is the only copy of `app`.
RUN python -c "import tomllib; d = tomllib.load(open('pyproject.toml','rb'))['project']; open('/tmp/requirements.txt','w').write('\n'.join(d['dependencies']))" \
    && pip install -r /tmp/requirements.txt

# --- Development: dev tools, source bind-mounted by docker-compose -------------------
FROM base AS dev
RUN python -c "import tomllib; d = tomllib.load(open('pyproject.toml','rb'))['project']; open('/tmp/requirements-dev.txt','w').write('\n'.join(d['optional-dependencies']['dev']))" \
    && pip install -r /tmp/requirements-dev.txt
COPY backend/ ./
USER orbit
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# --- Production ----------------------------------------------------------------------
FROM base AS prod
COPY --chown=orbit:orbit backend/app ./app
COPY --chown=orbit:orbit backend/migrations ./migrations
COPY --chown=orbit:orbit backend/alembic.ini ./alembic.ini
USER orbit
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/live', timeout=4).status == 200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--proxy-headers", "--forwarded-allow-ips", "*"]
