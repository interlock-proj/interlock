"""Bank account aggregate for testing."""

from decimal import Decimal

from pydantic import BaseModel

from ouroboros.aggregates.aggregate import Aggregate
from ouroboros.routing import applies_event, handles_command
from tests.fixtures.test_app.commands.bank_commands import DepositMoney, WithdrawMoney


class MoneyDeposited(BaseModel):
    """Test event."""

    amount: Decimal


class MoneyWithdrawn(BaseModel):
    """Test event."""

    amount: Decimal


class BankAccount(Aggregate):
    """Test aggregate."""

    balance: Decimal = Decimal("0")

    @handles_command
    def handle_deposit(self, cmd: DepositMoney) -> None:
        """Handle deposit command."""
        self.emit(MoneyDeposited(amount=cmd.amount))

    @handles_command
    def handle_withdraw(self, cmd: WithdrawMoney) -> None:
        """Handle withdraw command."""
        self.emit(MoneyWithdrawn(amount=cmd.amount))

    @applies_event
    def apply_deposited(self, event: MoneyDeposited) -> None:
        """Apply deposit event."""
        self.balance += event.amount

    @applies_event
    def apply_withdrawn(self, event: MoneyWithdrawn) -> None:
        """Apply withdraw event."""
        self.balance -= event.amount
