# orders-service

[![CI](https://github.com/777Alpha777/orders-service/actions/workflows/ci.yml/badge.svg)](https://github.com/777Alpha777/orders-service/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688)

Order and stock service for retail: creating orders with **race-free stock
reservation**, idempotent checkout, paginated feeds and Prometheus metrics.

Built as a reference for the patterns I use in production — the interesting part
is not the CRUD, it is the concurrency behaviour and the index benchmark below.

## Why it is built this way

| Problem | Solution in this repo |
|---|---|
| Two customers buy the last item at the same moment | `SELECT … FOR UPDATE` on stock rows, locked in a deterministic key order |
| Mobile client retries a checkout and creates a duplicate order | `Idempotency-Key` header + unique constraint + replay of the stored order |
| Status feed becomes slow as the table grows | Composite index `(status, created_at DESC)`, measured with a reproducible benchmark |
| Accidental N+1 queries on order items | `lazy="raise"` on the relationship + explicit `selectinload` |
| Silent oversell under load | A test with two concurrent requests asserts exactly one `201` and one `409` |

## Architecture

```mermaid
flowchart LR
    C[Client] -->|HTTP| A[FastAPI]
    A --> R[API routers]
    R --> S[Services<br/>orders · stock]
    S --> ORM[SQLAlchemy 2.0<br/>async]
    ORM --> PG[(PostgreSQL 16)]
    A --> M[/metrics/]
    M --> P[Prometheus]
```

Layers: `api` (HTTP contracts and validation) → `services` (business rules and
transaction boundaries) → `models` (persistence). No business logic in routers,
no HTTP concepts in services.

## Stack

- **Python 3.12**, FastAPI, Pydantic v2
- **SQLAlchemy 2.0** async + asyncpg, Alembic migrations
- **PostgreSQL 16**
- pytest + httpx (ASGI transport), ruff, GitHub Actions
- prometheus-client

## Quick start

```bash
cp .env.example .env

docker compose up -d db      # PostgreSQL on localhost:5433
pip install -e ".[dev]"
alembic upgrade head
python -m scripts.seed       # 3 warehouses, 5 products, stock
uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs

## API

```bash
# create an order (stock is reserved atomically)
curl -X POST http://localhost:8000/api/v1/orders \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: checkout-42' \
  -d '{"customer_id": 1, "warehouse_id": 1,
       "items": [{"product_id": 1, "quantity": 2}]}'

# repeat the same call — returns the same order with 200 instead of 201

# available stock for a product
curl http://localhost:8000/api/v1/stock/1

# paginated feed
curl 'http://localhost:8000/api/v1/orders?status=created&limit=20&offset=0'
```

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/orders` | Create an order, reserve stock |
| `GET` | `/api/v1/orders/{id}` | Order with items |
| `GET` | `/api/v1/orders` | Paginated feed, filter by status |
| `GET` | `/api/v1/stock/{product_id}` | Stock per warehouse |
| `GET` | `/health` | Liveness probe |
| `GET` | `/metrics` | Prometheus exposition |

Errors are explicit: `409` with `requested` and `available` when stock is short,
`404` for unknown product or order.

## Benchmark: what the composite index actually buys

The query is a real back-office pattern — 50 latest paid orders for the last
30 days:

```sql
SELECT id, customer_id, total_kopecks, created_at
FROM orders
WHERE status = 'paid' AND created_at >= now() - interval '30 days'
ORDER BY created_at DESC
LIMIT 50;
```

`python -m scripts.benchmark --rows 200000` seeds the table, measures the query
with only a primary key, adds `(status, created_at DESC)`, and measures again.
Both phases print `EXPLAIN (ANALYZE, BUFFERS)` so the plan change is visible,
not just the timing.

<!-- BENCHMARK_RESULTS -->

## Tests

```bash
docker compose up -d db
createdb -p 5433 -U postgres orders_test   # or: docker compose exec db createdb -U postgres orders_test
TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/orders_test pytest -q
```

The suite covers the paths that actually break in production:

- successful reservation and stock accounting;
- `409` with a machine-readable payload on insufficient stock;
- idempotent replay returns the same order and does **not** reserve twice;
- two concurrent orders of 6 against 10 in stock → exactly one succeeds;
- pagination, filtering and `404` for unknown order.

## Layout

```
app/
  api/        HTTP layer: routers, dependencies
  services/   business logic, transaction boundaries
  models.py   SQLAlchemy models
  schemas.py  Pydantic contracts
  metrics.py  Prometheus middleware
alembic/      migrations
scripts/      seed and benchmark
tests/        pytest suite
```

## Roadmap

- [ ] Outbox pattern for `order.created` events
- [ ] Reserve stock with an expiry (cart TTL)
- [ ] Load test with Locust in CI
