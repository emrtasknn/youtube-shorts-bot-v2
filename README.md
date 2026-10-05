# youtube-shorts-bot-v2

Provider-agnostic modular monolith for automated YouTube Shorts production and publishing.

## M0 — Repository Bootstrap

Python 3.12, configuration, PostgreSQL, SQLAlchemy, Alembic, logging, tests, Ruff, MyPy, Docker and GitHub Actions CI.

```bash
python -m venv .venv
pip install -e ".[dev]"
docker compose up -d postgres
alembic upgrade head
pytest -q
pre-commit install
```
