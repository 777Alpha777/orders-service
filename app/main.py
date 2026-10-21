from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api import routes_health, routes_orders, routes_stock
from app.db import engine
from app.errors import DomainError, InsufficientStock
from app.metrics import setup_metrics


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Orders Service",
        version="0.1.0",
        description="Orders and stock reservation with idempotent checkout.",
        lifespan=lifespan,
    )

    setup_metrics(app)

    app.include_router(routes_health.router)
    app.include_router(routes_orders.router, prefix="/api/v1")
    app.include_router(routes_stock.router, prefix="/api/v1")

    @app.exception_handler(DomainError)
    async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
        payload: dict[str, object] = {
            "type": type(exc).__name__,
            "message": str(exc),
        }
        if isinstance(exc, InsufficientStock):
            payload |= {
                "product_id": exc.product_id,
                "requested": exc.requested,
                "available": exc.available,
            }
        return JSONResponse(status_code=exc.status_code, content={"detail": payload})

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
