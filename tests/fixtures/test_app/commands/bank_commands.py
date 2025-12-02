"""Bank account commands."""

from decimal import Decimal

from interlock.domain import Command


class DepositMoney(Command):
    """Deposit money into account."""

    amount: Decimal


class WithdrawMoney(Command):
    """Withdraw money from account."""

    amount: Decimal
