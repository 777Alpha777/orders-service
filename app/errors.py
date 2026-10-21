class DomainError(Exception):
    """Base class for errors that map to a specific HTTP status."""

    status_code: int = 400


class ProductNotFound(DomainError):
    status_code = 404

    def __init__(self, product_id: int) -> None:
        self.product_id = product_id
        super().__init__(f"Product {product_id} not found")


class StockNotFound(DomainError):
    status_code = 404


class InsufficientStock(DomainError):
    status_code = 409

    def __init__(self, product_id: int, requested: int, available: int) -> None:
        self.product_id = product_id
        self.requested = requested
        self.available = available
        super().__init__(
            f"Not enough stock for product {product_id}: "
            f"requested {requested}, available {available}"
        )
