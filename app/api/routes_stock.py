from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import SessionDep
from app.schemas import StockOut
from app.services import stock as stock_service

router = APIRouter(prefix="/stock", tags=["stock"])


@router.get("/{product_id}", response_model=list[StockOut])
async def get_stock(
    product_id: int,
    session: SessionDep,
    warehouse_id: Annotated[int | None, Query(gt=0)] = None,
) -> list[StockOut]:
    return await stock_service.get_product_stock(session, product_id, warehouse_id)
