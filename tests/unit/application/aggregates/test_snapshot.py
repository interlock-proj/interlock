"""Tests for aggregate snapshot backends and strategies."""

from datetime import timedelta
from decimal import Decimal

import pytest
from ulid import ULID

from interlock.application.aggregates.repository.snapshot import (
    AggregateSnapshotStorageBackend,
    AggregateSnapshotStrategy,
    InMemoryAggregateSnapshotStorageBackend,
    NeverSnapshot,
    NullAggregateSnapshotStorageBackend,
    SnapshotAfterN,
    SnapshotAfterTime,
)
from tests.fixtures.test_app.aggregates.bank_account import (
    BankAccount,
)
from tests.fixtures.test_app.aggregates.nested.order import Order

# Snapshot Strategy Tests


def test_never_snapshot_strategy():
    """Verify NeverSnapshot returns False for any aggregate."""
    strategy = NeverSnapshot()
    account = BankAccount()
    assert strategy.should_snapshot(account) is False


def test_snapshot_after_n_versions():
    """Test SnapshotAfterN snapshots at correct version intervals."""
    strategy = SnapshotAfterN(version_increment=5)

    account = BankAccount()
    account.version = 4
    assert strategy.should_snapshot(account) is False

    account.version = 5
    assert strategy.should_snapshot(account) is True

    account.version = 10
    assert strategy.should_snapshot(account) is True

    account.version = 11
    assert strategy.should_snapshot(account) is False


def test_snapshot_after_time_elapsed():
    """Test SnapshotAfterTime snapshots when time has elapsed."""
    strategy = SnapshotAfterTime(time_increment=timedelta(hours=1))

    account = BankAccount()
    # Set last snapshot time to 2 hours ago
    account.last_snapshot_time = account.last_event_time - timedelta(hours=2)

    assert strategy.should_snapshot(account) is True


def test_snapshot_after_time_not_elapsed():
    """Test SnapshotAfterTime doesn't snapshot before time elapsed."""
    strategy = SnapshotAfterTime(time_increment=timedelta(hours=1))

    account = BankAccount()
    # Last snapshot time is recent (within the hour)
    account.last_snapshot_time = account.last_event_time

    assert strategy.should_snapshot(account) is False


def test_snapshot_strategy_factory_methods():
    """Verify snapshot strategy factory methods work correctly."""
    strategy = AggregateSnapshotStrategy.never()
    assert isinstance(strategy, NeverSnapshot)
    account = BankAccount()
    assert strategy.should_snapshot(account) is False


# NullAggregateSnapshotStorageBackend Tests


@pytest.mark.asyncio
async def test_null_backend_save_does_nothing():
    """Verify NullAggregateSnapshotStorageBackend.save_snapshot is no-op."""
    backend = NullAggregateSnapshotStorageBackend()
    account = BankAccount()
    await backend.save_snapshot(account)
    # Should not raise error


@pytest.mark.asyncio
async def test_null_backend_load_returns_none():
    """Verify NullAggregateSnapshotStorageBackend.load_snapshot returns None."""
    backend = NullAggregateSnapshotStorageBackend()
    result = await backend.load_snapshot(ULID())
    assert result is None

    result_with_version = await backend.load_snapshot(ULID(), version=10)
    assert result_with_version is None


@pytest.mark.asyncio
async def test_null_backend_list_ids_returns_empty():
    """Verify NullAggregateSnapshotStorageBackend returns empty list."""
    backend = NullAggregateSnapshotStorageBackend()
    result = await backend.list_aggregate_ids_by_type(BankAccount)
    assert result == []


@pytest.mark.asyncio
async def test_aggregate_snapshot_backend_factory_methods():
    """Verify snapshot backend factory methods work correctly."""
    backend = AggregateSnapshotStorageBackend.null()
    assert isinstance(backend, NullAggregateSnapshotStorageBackend)
    assert await backend.load_snapshot(ULID()) is None


# InMemoryAggregateSnapshotStorageBackend Tests


@pytest.mark.asyncio
async def test_in_memory_save_and_load():
    """Test in-memory backend save/load round trip."""
    backend = InMemoryAggregateSnapshotStorageBackend()

    account = BankAccount(id=ULID())
    account.owner = "Alice"
    account.balance = Decimal("100.00")
    account.version = 5

    await backend.save_snapshot(account)

    loaded = await backend.load_snapshot(account.id)
    assert loaded is not None
    assert loaded.id == account.id
    assert loaded.owner == "Alice"
    assert loaded.balance == Decimal("100.00")
    assert loaded.version == 5


@pytest.mark.asyncio
async def test_in_memory_load_latest_snapshot():
    """Test in-memory backend returns latest snapshot."""
    backend = InMemoryAggregateSnapshotStorageBackend()

    account_id = ULID()

    # Save multiple snapshots with increasing versions
    for version in [1, 3, 5, 7]:
        account = BankAccount(id=account_id)
        account.version = version
        account.balance = Decimal(str(version * 10))
        await backend.save_snapshot(account)

    # Load without version - should get latest
    loaded = await backend.load_snapshot(account_id)
    assert loaded is not None
    assert loaded.version == 7
    assert loaded.balance == Decimal("70")


@pytest.mark.asyncio
async def test_in_memory_load_with_intended_version():
    """Test in-memory backend loads correct version."""
    backend = InMemoryAggregateSnapshotStorageBackend()

    account_id = ULID()

    # Save multiple snapshots
    for version in [1, 3, 5, 7, 10]:
        account = BankAccount(id=account_id)
        account.version = version
        account.balance = Decimal(str(version * 10))
        await backend.save_snapshot(account)

    # Load with intended version 6 - should get version 5
    loaded = await backend.load_snapshot(account_id, intended_version=6)
    assert loaded is not None
    assert loaded.version == 5
    assert loaded.balance == Decimal("50")

    # Load with intended version 12 - should get latest (10)
    loaded = await backend.load_snapshot(account_id, intended_version=12)
    assert loaded is not None
    assert loaded.version == 10


@pytest.mark.asyncio
async def test_in_memory_list_aggregate_ids_by_type():
    """Test in-memory backend filters by aggregate type."""
    backend = InMemoryAggregateSnapshotStorageBackend()

    # Save BankAccount snapshots
    account1_id = ULID()
    account2_id = ULID()
    account1 = BankAccount(id=account1_id)
    account2 = BankAccount(id=account2_id)
    await backend.save_snapshot(account1)
    await backend.save_snapshot(account2)

    # Save Order snapshot
    order_id = ULID()
    order = Order(id=order_id)
    await backend.save_snapshot(order)

    # List BankAccount IDs
    bank_ids = await backend.list_aggregate_ids_by_type(BankAccount)
    assert len(bank_ids) == 2
    assert account1_id in bank_ids
    assert account2_id in bank_ids
    assert order_id not in bank_ids

    # List Order IDs
    order_ids = await backend.list_aggregate_ids_by_type(Order)
    assert len(order_ids) == 1
    assert order_id in order_ids


@pytest.mark.asyncio
async def test_in_memory_no_snapshot_returns_none():
    """Test in-memory backend returns None for missing aggregate."""
    backend = InMemoryAggregateSnapshotStorageBackend()

    non_existent_id = ULID()
    loaded = await backend.load_snapshot(non_existent_id)
    assert loaded is None

    loaded_with_version = await backend.load_snapshot(non_existent_id, intended_version=10)
    assert loaded_with_version is None
