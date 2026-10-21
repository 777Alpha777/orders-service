.PHONY: install migrate seed run test lint bench bench-data up down

install:
	pip install -e ".[dev]"

migrate:
	alembic upgrade head

seed:
	python -m scripts.seed

run:
	uvicorn app.main:app --reload --port 8000

test:
	pytest -q

lint:
	ruff check .
	ruff format --check .

bench:
	python -m scripts.benchmark

up:
	docker compose up --build -d

down:
	docker compose down -v
