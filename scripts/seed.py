"""Fill the database with a small demo dataset (warehouses, products, stock).

Usage:
    python -m scripts.seed
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.db import SessionFactory, engine
from app.models import Product, Stock, Warehouse

WAREHOUSES = [
    ("Moscow North", "Moscow"),
    ("Moscow South", "Moscow"),
    ("Saint Petersburg", "Saint Petersburg"),
]

PRODUCTS = [
    ("SKU-COFFEE-1KG", "Coffee beans 1kg", 129_900),
    ("SKU-FILTER-100", "Paper filters, 100 pcs", 24_900),
    ("SKU-MILK-1L", "Milk 1L", 8_900),
    ("SKU-TEA-500", "Black tea 500g", 45_000),
    ("SKU-CUP-250", "Paper cup 250ml", 1_200),
]

STOCK_PER_WAREHOUSE = [500, 1_200, 300, 150, 10_000]


async def main() -> None:
    async with SessionFactory() as session:
        existing = await session.scalar(select(Warehouse.id).limit(1))
        if existing is not None:
            print("Data already present, nothing to do.")
            return

        warehouses = [Warehouse(name=name, city=city) for name, city in WAREHOUSES]
        products = [
            Product(sku=sku, name=name, price_kopecks=price) for sku, name, price in PRODUCTS
        ]
        session.add_all([*warehouses, *products])
        await session.flush()

        for warehouse in warehouses:
            for product, quantity in zip(products, STOCK_PER_WAREHOUSE, strict=True):
                session.add(
                    Stock(
                        warehouse_id=warehouse.id,
                        product_id=product.id,
                        quantity=quantity,
                    )
                )

        await session.commit()

    await engine.dispose()
    print(f"Seeded {len(WAREHOUSES)} warehouses, {len(PRODUCTS)} products.")


if __name__ == "__main__":
    asyncio.run(main())
