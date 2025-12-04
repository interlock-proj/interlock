"""Tests for aggregate repository."""

from decimal import Decimal

import pytest
from ulid import ULID

from interlock.application.aggregates.repository.cache import (
    AggregateCacheBackend,
    AlwaysCache,
    CacheStrategy,
)
from interlock.application.aggregates.repository.repository import (
    AggregateRepository,
)
from interlock.application.aggregates.repository.snapshot import (
    AggregateSnapshotStrategy,
    SnapshotAfterN,
)
from interlock.domain.exceptions import ConcurrencyError
from tests.fixtures.test_app.aggregates.bank_account import (
    BankAccount,
    DepositMoney,
    OpenAccount,
)

# AggregateFactory Tests


def test_aggregate_factory_create(bank_account_factory):
    """Test AggregateFactory creates aggregate with given ID."""
    account_id = ULID()
    account = bank_account_factory.create(account_id)

    assert isinstance(account, BankAccount)
    assert account.id == account_id
    assert account.version == 0


def test_aggregate_factory_get_type(bank_account_factory):
    """Test AggregateFactory returns correct aggregate type."""
    aggregate_type = bank_account_factory.get_type()
    assert aggregate_type == BankAccount


# Repository Acquire Tests


@pytest.mark.asyncio
async def test_repository_acquire_new_aggregate(repository):
    """Test acquiring a non-existent aggregate creates new instance."""
    account_id = ULID()

    async with repository.acquire(account_id) as account:
        assert isinstance(account, BankAccount)
        assert account.id == account_id
        assert account.version == 0
        assert account.owner == ""


@pytest.mark.asyncio
async def test_repository_acquire_from_cache(
    bank_account_app, bank_account_factory, in_memory_snapshot_backend
):
    """Test repository loads from cache when available."""
    # Create custom cache backend that tracks calls
    class TrackingCache(AggregateCacheBackend):
        def __init__(self):
            self.cache = {}
            self.get_calls = 0

        async def get_aggregate(self, aggregate_id):
            self.get_calls += 1
            return self.cache.get(aggregate_id)

        async def set_aggregate(self, aggregate):
            self.cache[aggregate.id] = aggregate

        async def remove_aggregate(self, aggregate_id):
            self.cache.pop(aggregate_id, None)

    tracking_cache = TrackingCache()

    repository = AggregateRepository(
        bank_account_factory,
        bank_account_app.event_bus,
        AggregateSnapshotStrategy.never(),
        CacheStrategy.never(),
        in_memory_snapshot_backend,
        tracking_cache,
    )

    # Pre-populate cache
    account_id = ULID()
    cached_account = BankAccount(id=account_id)
    cached_account.owner = "Cached Alice"
    cached_account.version = 5
    await tracking_cache.set_aggregate(cached_account)

    # Acquire should hit cache
    async with repository.acquire(account_id) as account:
        assert account.owner == "Cached Alice"
        assert account.version == 5

    assert tracking_cache.get_calls == 1


@pytest.mark.asyncio
async def test_repository_acquire_from_snapshot(
    repository, in_memory_snapshot_backend
):
    """Test repository loads from snapshot when no cache hit."""
    account_id = ULID()

    # Create and save snapshot
    snapshot = BankAccount(id=account_id)
    snapshot.owner = "Snapshot Bob"
    snapshot.balance = Decimal("200.00")
    snapshot.version = 10
    await in_memory_snapshot_backend.save_snapshot(snapshot)

    # Acquire should load from snapshot
    async with repository.acquire(account_id) as account:
        assert account.owner == "Snapshot Bob"
        assert account.balance == Decimal("200.00")
        assert account.version == 10


@pytest.mark.asyncio
async def test_repository_acquire_with_events(repository):
    """Test repository replays events after snapshot."""
    account_id = ULID()

    # Create account and emit events
    async with repository.acquire(account_id) as account:
        account.handle(OpenAccount(aggregate_id=account_id, owner="Charlie"))
        account.handle(
            DepositMoney(aggregate_id=account_id, amount=Decimal("50.00"))
        )

    # Acquire again - should replay events
    async with repository.acquire(account_id) as account:
        assert account.owner == "Charlie"
        assert account.balance == Decimal("50.00")
        assert account.version == 2


@pytest.mark.asyncio
async def test_repository_acquire_saves_on_change(repository):
    """Test repository auto-saves when aggregate changes."""
    account_id = ULID()

    # Create and modify aggregate
    async with repository.acquire(account_id) as account:
        account.handle(OpenAccount(aggregate_id=account_id, owner="Diana"))
        assert len(account.uncommitted_events) == 1

    # Acquire again - changes should be persisted
    async with repository.acquire(account_id) as account:
        assert account.owner == "Diana"
        assert account.version == 1
        assert len(account.uncommitted_events) == 0


@pytest.mark.asyncio
async def test_repository_acquire_no_save_unchanged(repository):
    """Test repository doesn't save if aggregate unchanged."""
    account_id = ULID()

    # Create account
    async with repository.acquire(account_id) as account:
        account.handle(OpenAccount(aggregate_id=account_id, owner="Eve"))

    # Acquire without changes
    async with repository.acquire(account_id) as account:
        original_version = account.version
        # Don't make any changes

    # Version should remain the same
    async with repository.acquire(account_id) as account:
        assert account.version == original_version


@pytest.mark.asyncio
async def test_repository_acquire_clears_events_on_error(repository):
    """Test repository clears uncommitted events on exception."""
    account_id = ULID()

    # Create account first
    async with repository.acquire(account_id) as account:
        account.handle(OpenAccount(aggregate_id=account_id, owner="Frank"))

    # Attempt to make changes that fail
    with pytest.raises(ValueError, match="Amount must be positive"):
        async with repository.acquire(account_id) as account:
            account.handle(
                DepositMoney(
                    aggregate_id=account_id, amount=Decimal("-10.00")
                )
            )

    # Events should have been cleared, account state unchanged
    async with repository.acquire(account_id) as account:
        assert account.balance == Decimal("0.00")
        assert account.version == 1


# Repository Save Tests


@pytest.mark.asyncio
async def test_repository_snapshots_on_save(
    bank_account_app, bank_account_factory, in_memory_snapshot_backend
):
    """Test repository creates snapshot based on strategy."""
    repository = AggregateRepository(
        bank_account_factory,
        bank_account_app.event_bus,
        SnapshotAfterN(version_increment=2),
        CacheStrategy.never(),
        in_memory_snapshot_backend,
        AggregateCacheBackend.null(),
    )

    account_id = ULID()

    # Create account and reach version 2
    async with repository.acquire(account_id) as account:
        account.handle(OpenAccount(aggregate_id=account_id, owner="Henry"))
        account.handle(
            DepositMoney(aggregate_id=account_id, amount=Decimal("100.00"))
        )

    # Snapshot should exist
    snapshot = await in_memory_snapshot_backend.load_snapshot(account_id)
    assert snapshot is not None
    assert snapshot.version == 2
    assert snapshot.owner == "Henry"


@pytest.mark.asyncio
async def test_repository_handles_concurrency_error(
    bank_account_app, bank_account_factory, in_memory_snapshot_backend
):
    """Test repository invalidates cache on concurrency error."""
    # Create mock event bus that raises ConcurrencyError
    class FailingEventBus:
        def __init__(self, real_bus):
            self.real_bus = real_bus
            self.calls = 0

        async def load_events(self, *args, **kwargs):
            return await self.real_bus.load_events(*args, **kwargs)

        async def publish_events(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise ConcurrencyError("Concurrent modification")
            return await self.real_bus.publish_events(*args, **kwargs)

    # Create cache backend that tracks removals
    class TrackingCache(AggregateCacheBackend):
        def __init__(self):
            self.cache = {}
            self.removed_ids = []

        async def get_aggregate(self, aggregate_id):
            return self.cache.get(aggregate_id)

        async def set_aggregate(self, aggregate):
            self.cache[aggregate.id] = aggregate

        async def remove_aggregate(self, aggregate_id):
            self.removed_ids.append(aggregate_id)
            self.cache.pop(aggregate_id, None)

    tracking_cache = TrackingCache()
    failing_bus = FailingEventBus(bank_account_app.event_bus)

    repository = AggregateRepository(
        bank_account_factory,
        failing_bus,
        AggregateSnapshotStrategy.never(),
        CacheStrategy.never(),
        in_memory_snapshot_backend,
        tracking_cache,
    )

    account_id = ULID()

    # Attempt to modify aggregate - should raise ConcurrencyError
    with pytest.raises(ConcurrencyError):
        async with repository.acquire(account_id) as account:
            account.handle(OpenAccount(aggregate_id=account_id, owner="Ivy"))

    # Cache should have been invalidated
    assert account_id in tracking_cache.removed_ids


@pytest.mark.asyncio
async def test_repository_caches_on_read_without_changes(
    bank_account_app, bank_account_factory, in_memory_snapshot_backend
):
    """Test repository caches aggregate in high-read scenario."""
    # Create cache backend that tracks calls
    class TrackingCache(AggregateCacheBackend):
        def __init__(self):
            self.cache = {}
            self.set_calls = 0
            self.get_calls = 0

        async def get_aggregate(self, aggregate_id):
            self.get_calls += 1
            return self.cache.get(aggregate_id)

        async def set_aggregate(self, aggregate):
            self.set_calls += 1
            self.cache[aggregate.id] = aggregate

        async def remove_aggregate(self, aggregate_id):
            self.cache.pop(aggregate_id, None)

    tracking_cache = TrackingCache()

    repository = AggregateRepository(
        bank_account_factory,
        bank_account_app.event_bus,
        AggregateSnapshotStrategy.never(),
        AlwaysCache(),  # Always cache
        in_memory_snapshot_backend,
        tracking_cache,
    )

    account_id = ULID()

    # Create account
    async with repository.acquire(account_id) as account:
        account.handle(OpenAccount(aggregate_id=account_id, owner="Alice"))

    # No caching yet (aggregate changed)
    assert tracking_cache.set_calls == 0

    # Load without making changes (high-read scenario)
    async with repository.acquire(account_id) as account:
        # Just read, no modifications
        assert account.owner == "Alice"

    # Should have cached on read
    assert tracking_cache.set_calls == 1

    # Load again - should hit cache
    async with repository.acquire(account_id) as account:
        assert account.owner == "Alice"

    # Should have retrieved from cache
    assert (
        tracking_cache.get_calls == 3
    )  # Once for each acquire (including create)
    assert tracking_cache.cache[account_id] is not None


# Repository List Tests


@pytest.mark.asyncio
async def test_repository_list_all_ids(
    repository, in_memory_snapshot_backend
):
    """Test repository lists all aggregate IDs."""
    # Create multiple accounts
    account1_id = ULID()
    account2_id = ULID()

    async with repository.acquire(account1_id) as account:
        account.handle(OpenAccount(aggregate_id=account1_id, owner="Kate"))

    async with repository.acquire(account2_id) as account:
        account.handle(OpenAccount(aggregate_id=account2_id, owner="Leo"))

    # Note: list_all_ids returns IDs from snapshot backend
    # Since we're using NeverSnapshot strategy, this will be empty
    # unless we manually save snapshots
    await in_memory_snapshot_backend.save_snapshot(
        BankAccount(id=account1_id)
    )
    await in_memory_snapshot_backend.save_snapshot(
        BankAccount(id=account2_id)
    )

    ids = await repository.list_all_ids()
    assert len(ids) == 2
    assert account1_id in ids
    assert account2_id in ids

