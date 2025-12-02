"""Test aggregates."""

from .nested.order import Order

# Import bank_account last to avoid issues
from .bank_account import BankAccount  # noqa: E402

__all__ = ["BankAccount", "Order"]
