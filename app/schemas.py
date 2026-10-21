from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import OrderStatus


class OrderItemIn(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=1000)


class OrderCreate(BaseModel):
    customer_id: int = Field(gt=0)
    warehouse_id: int = Field(gt=0)
    items: list[OrderItemIn] = Field(min_length=1, max_length=100)


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: int
    quantity: int
    price_kopecks: int


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: int
    warehouse_id: int
    status: OrderStatus
    total_kopecks: int
    created_at: datetime
    items: list[OrderItemOut]


class StockOut(BaseModel):
    warehouse_id: int
    product_id: int
    quantity: int
    reserved: int
    available: int


from typing import Generic, TypeVar

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int
