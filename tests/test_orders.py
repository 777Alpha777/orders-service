from __future__ import annotations

import asyncio

from httpx import AsyncClient


def _payload(seeded: dict, quantity: int, product: str = "product_a") -> dict:
    return {
        "customer_id": 42,
        "warehouse_id": seeded["warehouse_id"],
        "items": [{"product_id": seeded[product], "quantity": quantity}],
    }


async def test_create_order_reserves_stock(client: AsyncClient, seeded: dict) -> None:
    response = await client.post("/api/v1/orders", json=_payload(seeded, 2))

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "created"
    assert body["total_kopecks"] == 2000
    assert len(body["items"]) == 1

    stock = (await client.get(f"/api/v1/stock/{seeded['product_a']}")).json()
    assert stock[0]["reserved"] == 2
    assert stock[0]["available"] == 8


async def test_insufficient_stock_returns_409(client: AsyncClient, seeded: dict) -> None:
    response = await client.post("/api/v1/orders", json=_payload(seeded, 99))

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["available"] == 10
    assert detail["requested"] == 99

    stock = (await client.get(f"/api/v1/stock/{seeded['product_a']}")).json()
    assert stock[0]["reserved"] == 0


async def test_idempotency_key_returns_the_same_order(client: AsyncClient, seeded: dict) -> None:
    headers = {"Idempotency-Key": "checkout-7f3a"}

    first = await client.post("/api/v1/orders", json=_payload(seeded, 2), headers=headers)
    second = await client.post("/api/v1/orders", json=_payload(seeded, 2), headers=headers)

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]

    # The replay must not reserve stock twice.
    stock = (await client.get(f"/api/v1/stock/{seeded['product_a']}")).json()
    assert stock[0]["reserved"] == 2


async def test_concurrent_orders_cannot_oversell(client: AsyncClient, seeded: dict) -> None:
    """10 units in stock, two simultaneous orders of 6: exactly one may succeed."""
    first, second = await asyncio.gather(
        client.post("/api/v1/orders", json=_payload(seeded, 6)),
        client.post("/api/v1/orders", json=_payload(seeded, 6)),
    )

    assert sorted([first.status_code, second.status_code]) == [201, 409]

    stock = (await client.get(f"/api/v1/stock/{seeded['product_a']}")).json()
    assert stock[0]["reserved"] == 6
    assert stock[0]["available"] == 4


async def test_list_orders_paginates_and_filters(client: AsyncClient, seeded: dict) -> None:
    for _ in range(3):
        await client.post("/api/v1/orders", json=_payload(seeded, 1))

    page = (await client.get("/api/v1/orders", params={"limit": 2, "offset": 0})).json()
    assert page["total"] == 3
    assert len(page["items"]) == 2

    filtered = (await client.get("/api/v1/orders", params={"status": "paid"})).json()
    assert filtered["total"] == 0


async def test_get_unknown_order_returns_404(client: AsyncClient) -> None:
    response = await client.get("/api/v1/orders/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
