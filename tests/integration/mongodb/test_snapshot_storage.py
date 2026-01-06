"""Integration tests for MongoSnapshotStorage."""

from uuid import uuid4

import pytest
import pytest_asyncio

from interlock.domain import Aggregate
from interlock.integrations.mongodb import MongoConfiguration, MongoSnapshotStorage


class BankAccount(Aggregate):
    """Test aggregate for snapshot tests."""

    owner: str = ""
    balance: int = 0


@pytest_asyncio.fixture
async def single_snapshot_storage(mongo_config_single_snapshot: MongoConfiguration):
    """Create a MongoSnapshotStorage in single mode."""
    return MongoSnapshotStorage(mongo_config_single_snapshot)


@pytest_asyncio.fixture
async def multiple_snapshot_storage(mongo_config_multiple_snapshot: MongoConfiguration):
    """Create a MongoSnapshotStorage in multiple mode."""
    return MongoSnapshotStorage(mongo_config_multiple_snapshot)


# ============ Single Mode Tests ============


@pytest.mark.integration
@pytest.mark.asyncio
async def test_single_mode_save_and_load(single_snapshot_storage: MongoSnapshotStorage):
    """Test saving and loading a snapshot in single mode."""
    aggregate = BankAccount(owner="Alice", balance=100)
    aggregate.version = 5

    await single_snapshot_storage.save_snapshot(aggregate)
    loaded = await single_snapshot_storage.load_snapshot(aggregate.id)

    assert loaded is not None
    assert loaded.id == aggregate.id
    assert loaded.owner == "Alice"
    assert loaded.balance == 100
    assert loaded.version == 5


@pytest.mark.integration
@pytest.mark.asyncio
async def test_single_mode_overwrites_snapshot(
    single_snapshot_storage: MongoSnapshotStorage,
):
    """Test that single mode overwrites the previous snapshot."""
    aggregate_id = uuid4()

    # Save first version
    aggregate = BankAccount(id=aggregate_id, owner="Bob", balance=50)
    aggregate.version = 1
    await single_snapshot_storage.save_snapshot(aggregate)

    # Save second version (should overwrite)
    aggregate.balance = 150
    aggregate.version = 5
    await single_snapshot_storage.save_snapshot(aggregate)

    # Load should return the latest
    loaded = await single_snapshot_storage.load_snapshot(aggregate_id)
    assert loaded is not None
    assert loaded.balance == 150
    assert loaded.version == 5


@pytest.mark.integration
@pytest.mark.asyncio
async def test_single_mode_intended_version_filter(
    single_snapshot_storage: MongoSnapshotStorage,
):
    """Test that single mode respects intended_version filter."""
    aggregate = BankAccount(owner="Charlie", balance=200)
    aggregate.version = 10
    await single_snapshot_storage.save_snapshot(aggregate)

    # Load with higher intended version - should work
    loaded = await single_snapshot_storage.load_snapshot(aggregate.id, intended_version=15)
    assert loaded is not None
    assert loaded.version == 10

    # Load with exact intended version - should work
    loaded = await single_snapshot_storage.load_snapshot(aggregate.id, intended_version=10)
    assert loaded is not None

    # Load with lower intended version - should return None
    loaded = await single_snapshot_storage.load_snapshot(aggregate.id, intended_version=5)
    assert loaded is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_single_mode_load_nonexistent(
    single_snapshot_storage: MongoSnapshotStorage,
):
    """Test loading a snapshot that doesn't exist."""
    loaded = await single_snapshot_storage.load_snapshot(uuid4())
    assert loaded is None


# ============ Multiple Mode Tests ============


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multiple_mode_save_and_load(
    multiple_snapshot_storage: MongoSnapshotStorage,
):
    """Test saving and loading a snapshot in multiple mode."""
    aggregate = BankAccount(owner="Dave", balance=300)
    aggregate.version = 3

    await multiple_snapshot_storage.save_snapshot(aggregate)
    loaded = await multiple_snapshot_storage.load_snapshot(aggregate.id)

    assert loaded is not None
    assert loaded.id == aggregate.id
    assert loaded.owner == "Dave"
    assert loaded.balance == 300
    assert loaded.version == 3


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multiple_mode_keeps_versions(
    multiple_snapshot_storage: MongoSnapshotStorage,
):
    """Test that multiple mode keeps multiple versions."""
    aggregate_id = uuid4()

    # Save version 5
    aggregate = BankAccount(id=aggregate_id, owner="Eve", balance=100)
    aggregate.version = 5
    await multiple_snapshot_storage.save_snapshot(aggregate)

    # Save version 10
    aggregate.balance = 200
    aggregate.version = 10
    await multiple_snapshot_storage.save_snapshot(aggregate)

    # Save version 15
    aggregate.balance = 300
    aggregate.version = 15
    await multiple_snapshot_storage.save_snapshot(aggregate)

    # Load latest (no intended_version)
    loaded = await multiple_snapshot_storage.load_snapshot(aggregate_id)
    assert loaded is not None
    assert loaded.version == 15
    assert loaded.balance == 300

    # Load with intended_version=12 (should get version 10)
    loaded = await multiple_snapshot_storage.load_snapshot(aggregate_id, intended_version=12)
    assert loaded is not None
    assert loaded.version == 10
    assert loaded.balance == 200

    # Load with intended_version=7 (should get version 5)
    loaded = await multiple_snapshot_storage.load_snapshot(aggregate_id, intended_version=7)
    assert loaded is not None
    assert loaded.version == 5
    assert loaded.balance == 100

    # Load with intended_version=3 (should return None - no snapshot at or below 3)
    loaded = await multiple_snapshot_storage.load_snapshot(aggregate_id, intended_version=3)
    assert loaded is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multiple_mode_load_nonexistent(
    multiple_snapshot_storage: MongoSnapshotStorage,
):
    """Test loading a snapshot that doesn't exist."""
    loaded = await multiple_snapshot_storage.load_snapshot(uuid4())
    assert loaded is None


# ============ List by Type Tests ============


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_aggregate_ids_by_type(single_snapshot_storage: MongoSnapshotStorage):
    """Test listing aggregate IDs by type."""
    # Create multiple aggregates
    agg1 = BankAccount(owner="User1", balance=100)
    agg1.version = 1
    agg2 = BankAccount(owner="User2", balance=200)
    agg2.version = 1
    agg3 = BankAccount(owner="User3", balance=300)
    agg3.version = 1

    await single_snapshot_storage.save_snapshot(agg1)
    await single_snapshot_storage.save_snapshot(agg2)
    await single_snapshot_storage.save_snapshot(agg3)

    ids = await single_snapshot_storage.list_aggregate_ids_by_type(BankAccount)

    assert len(ids) == 3
    assert agg1.id in ids
    assert agg2.id in ids
    assert agg3.id in ids


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_aggregate_ids_empty(single_snapshot_storage: MongoSnapshotStorage):
    """Test listing aggregate IDs when none exist."""

    class OtherAggregate(Aggregate):
        name: str = ""

    ids = await single_snapshot_storage.list_aggregate_ids_by_type(OtherAggregate)
    assert ids == []
