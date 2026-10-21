"""Measure the effect of the composite index on a realistic "recent orders" query.

The query is the kind of feed a back-office or a mobile client asks for:
"50 latest paid orders for the last 30 days". On a fresh install the table has
only a primary key, so PostgreSQL has to scan everything and sort the result.
After adding `(status, created_at DESC)` the planner can walk the index and stop
after 50 rows.

Usage:
    python -m scripts.benchmark --rows 200000

Requires a running PostgreSQL with the schema applied (`alembic upgrade head`).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import statistics
import time
import uuid
from datetime import UTC, datetime, timedelta

import asyncpg

DSN = os.getenv("BENCH_DSN", "postgresql://postgres:postgres@localhost:5433/orders")

QUERY = """
SELECT id, customer_id, total_kopecks, created_at
FROM orders
WHERE status = 'paid'
  AND created_at >= now() - interval '30 days'
ORDER BY created_at DESC
LIMIT 50
"""

INDEX_DDL = "CREATE INDEX ix_orders_status_created_at ON orders (status, created_at DESC)"
STATUSES = ["paid", "paid", "created", "shipped", "cancelled"]


async def ensure_reference_rows(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        INSERT INTO warehouses (id, name, city)
        VALUES (1, 'Benchmark warehouse', 'Moscow')
        ON CONFLICT (id) DO NOTHING
        """
    )


async def seed(conn: asyncpg.Connection, rows: int) -> None:
    existing = await conn.fetchval("SELECT count(*) FROM orders")
    if existing >= rows:
        print(f"orders table already holds {existing:,} rows — skipping seed")
        return

    print(f"seeding {rows:,} orders (this takes a minute)…")
    now = datetime.now(UTC)
    batch: list[tuple] = []
    for _ in range(rows):
        batch.append(
            (
                uuid.uuid4(),
                random.randint(1, 50_000),
                1,
                random.choice(STATUSES),
                random.randint(1_000, 500_000),
                now - timedelta(seconds=random.randint(0, 365 * 24 * 3600)),
            )
        )
        if len(batch) == 10_000:
            await _insert_batch(conn, batch)
            batch.clear()
    if batch:
        await _insert_batch(conn, batch)


async def _insert_batch(conn: asyncpg.Connection, batch: list[tuple]) -> None:
    await conn.executemany(
        """
        INSERT INTO orders (id, customer_id, warehouse_id, status, total_kopecks, created_at)
        VALUES ($1, $2, $3, $4::order_status, $5, $6)
        """,
        batch,
    )


async def measure(conn: asyncpg.Connection, runs: int) -> tuple[float, float]:
    for _ in range(3):  # warm-up: fill shared buffers and plan cache
        await conn.fetch(QUERY)

    samples: list[float] = []
    for _ in range(runs):
        started = time.perf_counter()
        await conn.fetch(QUERY)
        samples.append((time.perf_counter() - started) * 1000)

    samples.sort()
    p95_index = max(0, int(len(samples) * 0.95) - 1)
    return statistics.median(samples), samples[p95_index]


async def explain(conn: asyncpg.Connection) -> str:
    plan = await conn.fetch("EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) " + QUERY)
    return "\n".join(row[0] for row in plan)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=200_000, help="number of orders to seed")
    parser.add_argument("--runs", type=int, default=30, help="measured executions per phase")
    args = parser.parse_args()

    conn = await asyncpg.connect(DSN)
    try:
        await ensure_reference_rows(conn)
        await seed(conn, args.rows)
        await conn.execute("ANALYZE orders")

        print("\n=== without the composite index ===")
        await conn.execute("DROP INDEX IF EXISTS ix_orders_status_created_at")
        await conn.execute("ANALYZE orders")
        slow_p50, slow_p95 = await measure(conn, args.runs)
        print(f"p50 {slow_p50:.2f} ms · p95 {slow_p95:.2f} ms")
        print(await explain(conn))

        print("\n=== with (status, created_at DESC) ===")
        await conn.execute(INDEX_DDL)
        await conn.execute("ANALYZE orders")
        fast_p50, fast_p95 = await measure(conn, args.runs)
        print(f"p50 {fast_p50:.2f} ms · p95 {fast_p95:.2f} ms")
        print(await explain(conn))

        print("\n| Phase | p50, ms | p95, ms |")
        print("|---|---|---|")
        print(f"| No index | {slow_p50:.2f} | {slow_p95:.2f} |")
        print(f"| Composite index | {fast_p50:.2f} | {fast_p95:.2f} |")
        print(f"| Speed-up | x{slow_p50 / fast_p50:.1f} | x{slow_p95 / fast_p95:.1f} |")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
