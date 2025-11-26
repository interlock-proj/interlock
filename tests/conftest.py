"""Central test fixtures for all tests.

This module provides a base test application with common components that can be
reused and extended by specific tests. Tests can modify the application builder
to add test-specific components while reusing the common infrastructure.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal

import pytest
from pydantic import BaseModel
from ulid import ULID

from interlock.aggregates.aggregate import Aggregate
from interlock.application import ApplicationBuilder
from interlock.commands import Command, CommandHandler, CommandMiddleware
from interlock.events import InMemoryEventTransport
from interlock.events.processing import InMemorySagaStateStore
from interlock.events.store import EventStore, InMemoryEventStore
from interlock.routing import applies_event, handles_command


class IncrementCounter(Command):
    """Increment a counter by a specified amount."""

    amount: int = 1


class SetName(Command):
    """Set a name on an aggregate."""

    name: str


class DepositMoney(Command):
    """Deposit money into a bank account."""

    amount: Decimal


class WithdrawMoney(Command):
    """Withdraw money from a bank account."""

    amount: Decimal


class OpenAccount(Command):
    """Open a bank account."""

    owner: str


class CounterIncremented(BaseModel):
    """Counter was incremented."""

    amount: int


class NameChanged(BaseModel):
    """Name was changed."""

    name: str


class MoneyDeposited(BaseModel):
    """Money was deposited."""

    amount: Decimal


class MoneyWithdrawn(BaseModel):
    """Money was withdrawn."""

    amount: Decimal


class AccountOpened(BaseModel):
    """Account was opened."""

    owner: str


class Counter(Aggregate):
    """Simple counter aggregate for testing."""

    count: int = 0
    name: str = ""

    @handles_command
    def handle_increment(self, command: IncrementCounter):
        self.emit(CounterIncremented(amount=command.amount))

    @handles_command
    def handle_set_name(self, command: SetName):
        self.emit(NameChanged(name=command.name))

    @applies_event
    def apply_incremented(self, event: CounterIncremented):
        self.count += event.amount

    @applies_event
    def apply_name_changed(self, event: NameChanged):
        self.name = event.name


class BankAccount(Aggregate):
    """Bank account aggregate for testing."""

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


class ExecutionTracker(CommandMiddleware):
    """Middleware that tracks command execution for testing."""

    def __init__(self):
        self.executions = []

    async def handle(self, command: Command, next: CommandHandler):
        self.executions.append(("start", type(command).__name__))
        result = await next(command)
        self.executions.append(("end", type(command).__name__))
        return result


@pytest.fixture
def aggregate_id() -> ULID:
    """Generate a unique aggregate ID."""
    return ULID()


@pytest.fixture
def account_id() -> ULID:
    """Generate a unique account ID (alias for aggregate_id)."""
    return ULID()


@pytest.fixture
def correlation_id() -> ULID:
    """Generate a unique correlation ID."""
    return ULID()


@pytest.fixture
def counter(aggregate_id: ULID) -> Counter:
    """Create a Counter aggregate instance."""
    return Counter(id=aggregate_id)


@pytest.fixture
def bank_account(aggregate_id: ULID) -> BankAccount:
    """Create a BankAccount aggregate instance."""
    return BankAccount(id=aggregate_id)


@pytest.fixture
def counter_repository(counter: Counter):
    """Create a simple repository for Counter aggregates."""

    class CounterRepository:
        @asynccontextmanager
        async def acquire(self, aggregate_id: ULID) -> AsyncIterator[Counter]:
            yield counter

    return CounterRepository()


@pytest.fixture
def bank_account_repository(bank_account: BankAccount):
    """Create a simple repository for BankAccount aggregates."""

    class BankAccountRepository:
        @asynccontextmanager
        async def acquire(self, aggregate_id: ULID) -> AsyncIterator[BankAccount]:
            yield bank_account

    return BankAccountRepository()


@pytest.fixture
def event_store() -> InMemoryEventStore:
    """Create an in-memory event store."""
    return InMemoryEventStore()


@pytest.fixture
def event_transport() -> InMemoryEventTransport:
    """Create an in-memory event transport."""
    return InMemoryEventTransport()


@pytest.fixture
def saga_state_store() -> InMemorySagaStateStore:
    """Create an in-memory saga state store."""
    return InMemorySagaStateStore()


@pytest.fixture
def execution_tracker() -> ExecutionTracker:
    """Create an execution tracker middleware."""
    return ExecutionTracker()


@pytest.fixture
def upcaster_map():
    """Create an empty UpcasterMap for testing."""
    from interlock.events.upcasting.pipeline import UpcasterMap

    return UpcasterMap()


@pytest.fixture
def command_handler(counter_app):
    """Resolve DelegateToAggregate from counter app."""
    from interlock.commands.bus import DelegateToAggregate

    return counter_app.resolve(DelegateToAggregate)


@pytest.fixture
def middleware_filter(counter_app):
    """Resolve MiddlewareTypeFilter from counter app."""
    from interlock.commands.bus import MiddlewareTypeFilter

    return counter_app.resolve(MiddlewareTypeFilter)


@pytest.fixture
def base_app_builder(
    event_store: InMemoryEventStore, event_transport: InMemoryEventTransport
) -> ApplicationBuilder:
    """Create a base application builder with common dependencies.

    Tests can use this fixture and add their specific components:

    def test_something(base_app_builder, aggregate_id):
        app = (
            base_app_builder
            .add_aggregate(Counter)
            .add_command(IncrementCounter)
            .build()
        )
        await app.dispatch(IncrementCounter(aggregate_id=aggregate_id))
    """
    return (
        ApplicationBuilder()
        .register_dependency(EventStore, lambda: event_store)
        .register_dependency(InMemoryEventTransport, lambda: event_transport)
    )


@pytest.fixture
def counter_app(base_app_builder: ApplicationBuilder):
    """Create a pre-configured application with Counter aggregate.

    This is a convenience fixture for tests that need a simple counter app.
    """
    return (
        base_app_builder.register_aggregate(Counter)
        .build()
    )


@pytest.fixture
def bank_account_app(base_app_builder: ApplicationBuilder):
    """Create a pre-configured application with BankAccount aggregate.

    This is a convenience fixture for tests that need a bank account app.
    """
    return (
        base_app_builder.register_aggregate(BankAccount)
        .build()
    )


@pytest.fixture(autouse=True)
def clear_execution_context():
    """Automatically clear execution context after each test."""
    yield
    from interlock.context import clear_context

    clear_context()
