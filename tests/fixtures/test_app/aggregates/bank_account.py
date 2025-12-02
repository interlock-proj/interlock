"""Bank account aggregate and commands for testing."""

from decimal import Decimal

from pydantic import BaseModel

from interlock.domain import Aggregate, Command
from interlock.routing import applies_event, handles_command


# Commands
class OpenAccount(Command):
    owner: str


class DepositMoney(Command):
    amount: Decimal


class WithdrawMoney(Command):
    amount: Decimal


# Events
class AccountOpened(BaseModel):
    owner: str


class MoneyDeposited(BaseModel):
    amount: Decimal


class MoneyWithdrawn(BaseModel):
    amount: Decimal


# Aggregate
class BankAccount(Aggregate):
    balance: Decimal = Decimal("0.00")
    owner: str = ""

    @handles_command
    def handle_open(self, cmd: OpenAccount) -> None:
        if self.owner:
            raise ValueError("Account already opened")
        self.emit(AccountOpened(owner=cmd.owner))

    @handles_command
    def handle_deposit(self, cmd: DepositMoney) -> None:
        if cmd.amount <= 0:
            raise ValueError("Amount must be positive")
        self.emit(MoneyDeposited(amount=cmd.amount))

    @handles_command
    def handle_withdraw(self, cmd: WithdrawMoney) -> None:
        if cmd.amount <= 0:
            raise ValueError("Amount must be positive")
        if cmd.amount > self.balance:
            raise ValueError("Insufficient funds")
        self.emit(MoneyWithdrawn(amount=cmd.amount))

    @applies_event
    def apply_opened(self, evt: AccountOpened) -> None:
        self.owner = evt.owner

    @applies_event
    def apply_deposited(self, event: MoneyDeposited) -> None:
        self.balance += event.amount

    @applies_event
    def apply_withdrawn(self, event: MoneyWithdrawn) -> None:
        self.balance -= event.amount
