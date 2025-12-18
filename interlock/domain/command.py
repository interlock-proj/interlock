"""Command base class for the write side of CQRS.

Commands represent intentions to change state and are dispatched to aggregates.
"""

from typing import Generic, TypeVar

from pydantic import BaseModel, Field
from ulid import ULID

TResponse = TypeVar("TResponse")


class Command(BaseModel, Generic[TResponse]):
    """Base class for all commands in the system.

    Commands represent intentions to change state and are dispatched to
    command handlers. All commands must include an aggregate_id to identify
    which aggregate instance to operate on.

    Commands are generic over their response type, allowing handlers to
    return typed results. Use `Command[None]` for commands that don't
    return a value.

    Type Parameters:
        TResponse: The type returned by command handlers for this command

    Attributes:
        aggregate_id: ULID of the aggregate that should handle this command.
        correlation_id: Optional correlation ID for distributed tracing.
        causation_id: Optional ID of what caused this command.
        command_id: Unique identifier for this command instance.

    Examples:
        Command that returns the new aggregate ID:

        >>> class CreateAccount(Command[ULID]):
        ...     owner: str
        >>>
        >>> class BankAccount(Aggregate):
        ...     @handles_command
        ...     def handle_create(self, cmd: CreateAccount) -> ULID:
        ...         self.emit(AccountCreated(owner=cmd.owner))
        ...         return self.id

        Command that returns nothing:

        >>> class DepositMoney(Command[None]):
        ...     amount: Decimal
        >>>
        >>> class BankAccount(Aggregate):
        ...     @handles_command
        ...     def handle_deposit(self, cmd: DepositMoney) -> None:
        ...         self.emit(MoneyDeposited(amount=cmd.amount))
    """

    aggregate_id: ULID
    correlation_id: ULID | None = None
    causation_id: ULID | None = None
    command_id: ULID = Field(default_factory=ULID)
