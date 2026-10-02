name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  quality:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: shorts
          POSTGRES_USER: shorts
          POSTGRES_PASSWORD: shorts
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U shorts -d shorts"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10
    env:
      DATABASE_URL: postgresql+psycopg://shorts:shorts@localhost:5432/shorts
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: python -m pip install --upgrade pip
      - run: pip install -e ".[dev]"
      - run: ruff check .
      - run: ruff format --check .
      - run: mypy app
      - run: alembic upgrade head
      - run: pytest -q
      - run: docker build -t youtube-shorts-bot-v2 .
