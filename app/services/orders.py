from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.errors import InsufficientStock, ProductNotFound
from app.models import Order, OrderItem, OrderStatus, Product, Stock
from app.schemas import OrderCreate


async def create_order(
    session: AsyncSession,
    payload: OrderCreate,
    idempotency_key: str | None = None,
) -> tuple[Order, bool]:
    """Create an order and reserve stock for it.

    Returns ``(order, created)``. ``created`` is False when the call is a replay
    of an earlier request with the same Idempotency-Key, in which case the
    already stored order is returned unchanged.
    """
    if idempotency_key is not None:
        existing = await _find_by_idempotency_key(session, idempotency_key)
        if existing is not None:
            return existing, False

    # Aggregate quantities: the same product may appear in several lines.
    requested: dict[int, int] = {}
    for item in payload.items:
        requested[item.product_id] = requested.get(item.product_id, 0) + item.quantity

    product_ids = sorted(requested)
    products = {
        product.id: product
        for product in await session.scalars(select(Product).where(Product.id.in_(product_ids)))
    }
    for product_id in product_ids:
        if product_id not in products:
            raise ProductNotFound(product_id)

    # Lock stock rows in a deterministic key order: two concurrent orders that
    # touch the same products always acquire locks in the same sequence, so they
    # queue instead of deadlocking.
    stock_rows = (
        await session.scalars(
            select(Stock)
            .where(
                Stock.warehouse_id == payload.warehouse_id,
                Stock.product_id.in_(product_ids),
            )
            .order_by(Stock.product_id)
            .with_for_update()
        )
    ).all()
    stock_by_product = {row.product_id: row for row in stock_rows}

    total_kopecks = 0
    for product_id, quantity in requested.items():
        row = stock_by_product.get(product_id)
        available = (row.quantity - row.reserved) if row is not None else 0
        if available < quantity:
            raise InsufficientStock(product_id, quantity, available)
        total_kopecks += products[product_id].price_kopecks * quantity

    order = Order(
        customer_id=payload.customer_id,
        warehouse_id=payload.warehouse_id,
        total_kopecks=total_kopecks,
        idempotency_key=idempotency_key,
    )
    order.items = [
        OrderItem(
            product_id=item.product_id,
            quantity=item.quantity,
            price_kopecks=products[item.product_id].price_kopecks,
        )
        for item in payload.items
    ]
    session.add(order)

    for product_id, quantity in requested.items():
        stock_by_product[product_id].reserved += quantity

    try:
        await session.commit()
    except IntegrityError:
        # Lost the race on the idempotency key: the parallel request won.
        await session.rollback()
        if idempotency_key is not None:
            existing = await _find_by_idempotency_key(session, idempotency_key)
            if existing is not None:
                return existing, False
        raise

    await session.refresh(order, attribute_names=["items"])
    return order, True


async def get_order(session: AsyncSession, order_id: uuid.UUID) -> Order | None:
    return await session.scalar(
        select(Order).where(Order.id == order_id).options(selectinload(Order.items))
    )


async def list_orders(
    session: AsyncSession,
    status: OrderStatus | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[Sequence[Order], int]:
    conditions = [] if status is None else [Order.status == status]

    stmt = (
        select(Order)
        .where(*conditions)
        .options(selectinload(Order.items))
        .order_by(Order.created_at.desc(), Order.id)
        .limit(limit)
        .offset(offset)
    )
    total = await session.scalar(select(func.count()).select_from(Order).where(*conditions))

    rows = (await session.scalars(stmt)).all()
    return rows, int(total or 0)


async def _find_by_idempotency_key(session: AsyncSession, key: str) -> Order | None:
    return await session.scalar(
        select(Order).where(Order.idempotency_key == key).options(selectinload(Order.items))
    )
