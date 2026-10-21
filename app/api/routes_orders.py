from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query, Response, status

from app.api.deps import SessionDep
from app.models import OrderStatus
from app.schemas import OrderCreate, OrderOut, Page
from app.services import orders as orders_service

router = APIRouter(prefix="/orders", tags=["orders"])

IdempotencyKey = Annotated[
    str | None,
    Header(
        alias="Idempotency-Key",
        max_length=64,
        description="Client-generated key; a repeated key returns the original order.",
    ),
]


@router.post(
    "",
    response_model=OrderOut,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"description": "Idempotent replay of an existing order"}},
)
async def create_order(
    payload: OrderCreate,
    response: Response,
    session: SessionDep,
    idempotency_key: IdempotencyKey = None,
) -> OrderOut:
    order, created = await orders_service.create_order(session, payload, idempotency_key)
    if not created:
        response.status_code = status.HTTP_200_OK
    return OrderOut.model_validate(order)


@router.get("/{order_id}", response_model=OrderOut)
async def get_order(order_id: uuid.UUID, session: SessionDep) -> OrderOut:
    order = await orders_service.get_order(session, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return OrderOut.model_validate(order)


@router.get("", response_model=Page[OrderOut])
async def list_orders(
    session: SessionDep,
    status_filter: Annotated[OrderStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[OrderOut]:
    rows, total = await orders_service.list_orders(session, status_filter, limit, offset)
    return Page[OrderOut](
        items=[OrderOut.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
