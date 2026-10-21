from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Stock
from app.schemas import StockOut


async def get_product_stock(
    session: AsyncSession, product_id: int, warehouse_id: int | None = None
) -> list[StockOut]:
    conditions = [Stock.product_id == product_id]
    if warehouse_id is not None:
        conditions.append(Stock.warehouse_id == warehouse_id)

    rows = (
        await session.scalars(select(Stock).where(*conditions).order_by(Stock.warehouse_id))
    ).all()

    return [
        StockOut(
            warehouse_id=row.warehouse_id,
            product_id=row.product_id,
            quantity=row.quantity,
            reserved=row.reserved,
            available=row.quantity - row.reserved,
        )
        for row in rows
    ]
