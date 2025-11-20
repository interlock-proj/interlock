"""Nested order aggregate for testing recursive discovery."""

from interlock.aggregates.aggregate import Aggregate


class Order(Aggregate):
    """Test nested aggregate."""

    customer_id: str = ""
