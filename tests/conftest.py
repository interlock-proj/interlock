"""Central test fixtures - imports from unified test_app."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import pytest

from interlock.application import ApplicationBuilder
from interlock.application.events import InMemoryEventStore, InMemoryEventTransport
from interlock.application.events.processing import InMemorySagaStateStore
from interlock.application.events.store import EventStore

# Import all test domain objects from unified test app
from tests.fixtures.test_app import (
    BankAccount,
    ExecutionTracker,
)


@pytest.fixture
def aggregate_id() -> UUID:
    """Generate a unique aggregate ID."""
    return uuid4()


@pytest.fixture
def account_id() -> UUID:
    """Generate a unique account ID."""
    return uuid4()


@pytest.fixture
def correlation_id() -> UUID:
    """Generate a unique correlation ID."""
    return uuid4()


@pytest.fixture
def bank_account(aggregate_id: UUID) -> BankAccount:
    """Create a BankAccount aggregate instance."""
    return BankAccount(id=aggregate_id)


@pytest.fixture
def bank_account_repository(bank_account: BankAccount):
    """Create a simple repository for BankAccount aggregates."""

    class BankAccountRepository:
        @asynccontextmanager
        async def acquire(self, aggregate_id: UUID) -> AsyncIterator[BankAccount]:
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
    from interlock.application.events.upcasting.pipeline import UpcasterMap

    return UpcasterMap()


@pytest.fixture
def base_app_builder(
    event_store: InMemoryEventStore, event_transport: InMemoryEventTransport
) -> ApplicationBuilder:
    """Create a base application builder with common dependencies."""
    return (
        ApplicationBuilder()
        .register_dependency(EventStore, lambda: event_store)
        .register_dependency(InMemoryEventTransport, lambda: event_transport)
    )


@pytest.fixture
def bank_account_app(base_app_builder: ApplicationBuilder):
    """Create application with BankAccount aggregate."""
    return base_app_builder.register_aggregate(BankAccount).build()


@pytest.fixture
def test_app(base_app_builder: ApplicationBuilder):
    """Create fully-configured test application via convention-based discovery."""
    return base_app_builder.convention_based("tests.fixtures.test_app").build()


@pytest.fixture
def command_handler(bank_account_app):
    """Resolve DelegateToAggregate from bank account app."""
    from interlock.application.commands import DelegateToAggregate

    return bank_account_app.resolve(DelegateToAggregate)


@pytest.fixture(autouse=True)
def clear_execution_context():
    """Automatically clear execution context after each test."""
    yield
    from interlock.context import clear_context

    clear_context()
