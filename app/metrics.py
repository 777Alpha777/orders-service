import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter(
    "orders_http_requests_total",
    "Total number of HTTP requests",
    ["method", "path", "status"],
)

REQUEST_LATENCY = Histogram(
    "orders_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

ORDER_STATUS_TOTAL = Counter(
    "orders_created_total",
    "Orders created, by final status",
    ["status"],
)


def setup_metrics(app: FastAPI) -> None:
    @app.middleware("http")
    async def _track(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        started = time.perf_counter()
        response = await call_next(request)

        route = request.scope.get("route")
        # Use the route template, not the raw URL, otherwise every order id
        # creates a new time series and the cardinality explodes.
        path = getattr(route, "path", request.url.path)

        REQUEST_LATENCY.labels(request.method, path).observe(time.perf_counter() - started)
        REQUEST_COUNT.labels(request.method, path, str(response.status_code)).inc()
        return response
