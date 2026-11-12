# ORBIT OFFICE AI — Backend

FastAPI + SQLAlchemy 2 (psycopg 3) + Alembic + Celery. See the repository
`README.md` and `docs/RUNBOOK.md` for setup and commands.

```bash
python -m venv .venv && .venv/Scripts/activate   # Windows (use bin/activate elsewhere)
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload                    # http://localhost:8000/api/docs
pytest                                           # unit tests (integration: ORBIT_RUN_INTEGRATION=1)
ruff check . && ruff format --check . && mypy app
```
