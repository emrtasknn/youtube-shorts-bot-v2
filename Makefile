install:
	python -m pip install -e ".[dev]"
test:
	pytest -q
lint:
	ruff check .
format:
	ruff format .
format-check:
	ruff format --check .
typecheck:
	mypy app
db-up:
	docker compose up -d postgres
db-down:
	docker compose down
db-migrate:
	alembic upgrade head
db-current:
	alembic current
quality: lint format-check typecheck test
