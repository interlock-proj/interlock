"""Test aggregates."""

# Import bank_account last to avoid issues
from .bank_account import BankAccount  # noqa: E402
from .nested.order import Order

__all__ = ["BankAccount", "Order"]
