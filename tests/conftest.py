from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.db import get_session
from app.main import create_app
from app.models import Base, Product, Stock, Warehouse

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5433/orders_test",
)


@pytest_asyncio.fixture
async def engine() -> AsyncIterator:
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
    except OSError as exc:  # pragma: no cover - depends on local setup
        pytest.skip(f"PostgreSQL is not available at {TEST_DATABASE_URL}: {exc}")
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.execute(Base.metadata.tables["order_items"].delete())
        await conn.execute(Base.metadata.tables["orders"].delete())
        await conn.execute(Base.metadata.tables["stock"].delete())
        await conn.execute(Base.metadata.tables["products"].delete())
        await conn.execute(Base.metadata.tables["warehouses"].delete())

    return factory


@pytest_asyncio.fixture
async def client(session_factory) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def _override() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = _override

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


@pytest_asyncio.fixture
async def seeded(session_factory):
    """One warehouse, two products, 10 units of product 1 in stock."""
    async with session_factory() as session:
        warehouse = Warehouse(name="Moscow North", city="Moscow")
        session.add(warehouse)
        await session.flush()

        product_a = Product(sku="SKU-A", name="Coffee beans 1kg", price_kopecks=1000)
        product_b = Product(sku="SKU-B", name="Paper filters", price_kopecks=250)
        session.add_all([product_a, product_b])
        await session.flush()

        session.add_all(
            [
                Stock(warehouse_id=warehouse.id, product_id=product_a.id, quantity=10),
                Stock(warehouse_id=warehouse.id, product_id=product_b.id, quantity=5),
            ]
        )
        await session.commit()

        return {
            "warehouse_id": warehouse.id,
            "product_a": product_a.id,
            "product_b": product_b.id,
        }
