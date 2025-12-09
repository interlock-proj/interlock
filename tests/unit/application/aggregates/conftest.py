"""Fixtures for aggregate repository tests."""

import pytest

from interlock.application.aggregates.repository import AggregateFactory
from interlock.application.aggregates.repository.cache import (
    AggregateCacheBackend,
    CacheStrategy,
)
from interlock.application.aggregates.repository.repository import (
    AggregateRepository,
)
from interlock.application.aggregates.repository.snapshot import (
    AggregateSnapshotStrategy,
    InMemoryAggregateSnapshotStorageBackend,
)
from tests.fixtures.test_app.aggregates.bank_account import BankAccount


@pytest.fixture
def bank_account_factory():
    """Create a factory for BankAccount aggregates."""
    return AggregateFactory(BankAccount)


@pytest.fixture
def in_memory_snapshot_backend():
    """Create an in-memory snapshot backend."""
    return InMemoryAggregateSnapshotStorageBackend()


@pytest.fixture
def repository(bank_account_app, bank_account_factory, in_memory_snapshot_backend):
    """Create a repository with default strategies."""
    return AggregateRepository(
        bank_account_factory,
        bank_account_app.event_bus,
        AggregateSnapshotStrategy.never(),
        CacheStrategy.never(),
        in_memory_snapshot_backend,
        AggregateCacheBackend.null(),
    )
