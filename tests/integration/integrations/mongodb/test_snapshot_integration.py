"""Integration tests for MongoDBSnapshotBackend using real MongoDB via testcontainers."""

import pytest
import pytest_asyncio
from pydantic import BaseModel
from testcontainers.mongodb import MongoDbContainer
from ulid import ULID

from interlock.domain import Aggregate
from interlock.integrations.mongodb import (
    MongoDBConfig,
    MongoDBConnectionManager,
    MongoDBSnapshotBackend,
    SnapshotStorageStrategy,
)


class BankAccountState(BaseModel):
    """Sample aggregate state."""

    balance: float
    owner: str


class BankAccount(Aggregate):
    """Sample aggregate for testing."""

    balance: float
    owner: str


@pytest.fixture(scope="module")
def mongodb_container():
    """Start MongoDB container for tests."""
    container = MongoDbContainer("mongo:7")
    with container:
        yield container


@pytest_asyncio.fixture
async def connection_manager(mongodb_container):
    """Create connection manager for MongoDB container."""
    config = MongoDBConfig(uri=mongodb_container.get_connection_url(), database="test_interlock")
    async with MongoDBConnectionManager(config) as manager:
        yield manager


@pytest_asyncio.fixture
async def snapshot_backend_single(connection_manager):
    """Create snapshot backend with SINGLE strategy."""
    backend = MongoDBSnapshotBackend(connection_manager, strategy=SnapshotStorageStrategy.SINGLE)
    await backend.initialize_schema()
    yield backend
    # Cleanup
    await connection_manager.database["snapshots"].delete_many({})


@pytest_asyncio.fixture
async def snapshot_backend_versioned(connection_manager):
    """Create snapshot backend with VERSIONED strategy."""
    backend = MongoDBSnapshotBackend(connection_manager, strategy=SnapshotStorageStrategy.VERSIONED)
    await backend.initialize_schema()
    yield backend
    # Cleanup
    await connection_manager.database["snapshots"].delete_many({})


@pytest.mark.asyncio
async def test_save_and_load_snapshot_single_strategy(snapshot_backend_single):
    """Test saving and loading a snapshot with SINGLE strategy."""
    aggregate_id = ULID()
    aggregate = BankAccount(id=aggregate_id, version=10, balance=1000.0, owner="Alice")

    await snapshot_backend_single.save_snapshot(aggregate)
    loaded = await snapshot_backend_single.load_snapshot(aggregate_id)

    assert loaded is not None
    assert loaded.id == aggregate_id
    assert loaded.version == 10
    assert loaded.balance == 1000.0
    assert loaded.owner == "Alice"


@pytest.mark.asyncio
async def test_single_strategy_overwrites_snapshot(snapshot_backend_single):
    """Test that SINGLE strategy overwrites previous snapshot."""
    aggregate_id = ULID()

    # Save first snapshot
    aggregate1 = BankAccount(id=aggregate_id, version=10, balance=1000.0, owner="Alice")
    await snapshot_backend_single.save_snapshot(aggregate1)

    # Save second snapshot (should overwrite)
    aggregate2 = BankAccount(id=aggregate_id, version=20, balance=2000.0, owner="Alice")
    await snapshot_backend_single.save_snapshot(aggregate2)

    # Should only have latest
    loaded = await snapshot_backend_single.load_snapshot(aggregate_id)
    assert loaded is not None
    assert loaded.version == 20
    assert loaded.balance == 2000.0


@pytest.mark.asyncio
async def test_versioned_strategy_keeps_all_snapshots(snapshot_backend_versioned):
    """Test that VERSIONED strategy keeps all snapshot versions."""
    aggregate_id = ULID()

    # Save multiple snapshots
    aggregate1 = BankAccount(id=aggregate_id, version=10, balance=1000.0, owner="Alice")
    await snapshot_backend_versioned.save_snapshot(aggregate1)

    aggregate2 = BankAccount(id=aggregate_id, version=20, balance=2000.0, owner="Alice")
    await snapshot_backend_versioned.save_snapshot(aggregate2)

    aggregate3 = BankAccount(id=aggregate_id, version=30, balance=3000.0, owner="Alice")
    await snapshot_backend_versioned.save_snapshot(aggregate3)

    # Load without version should return latest
    loaded = await snapshot_backend_versioned.load_snapshot(aggregate_id)
    assert loaded is not None
    assert loaded.version == 30
    assert loaded.balance == 3000.0


@pytest.mark.asyncio
async def test_load_snapshot_with_intended_version(snapshot_backend_versioned):
    """Test loading snapshot at or below intended version."""
    aggregate_id = ULID()

    # Save multiple versions
    aggregate1 = BankAccount(id=aggregate_id, version=10, balance=1000.0, owner="Alice")
    await snapshot_backend_versioned.save_snapshot(aggregate1)

    aggregate2 = BankAccount(id=aggregate_id, version=20, balance=2000.0, owner="Alice")
    await snapshot_backend_versioned.save_snapshot(aggregate2)

    aggregate3 = BankAccount(id=aggregate_id, version=30, balance=3000.0, owner="Alice")
    await snapshot_backend_versioned.save_snapshot(aggregate3)

    # Load at version 15 should get version 10
    loaded = await snapshot_backend_versioned.load_snapshot(aggregate_id, intended_version=15)
    assert loaded is not None
    assert loaded.version == 10

    # Load at version 25 should get version 20
    loaded = await snapshot_backend_versioned.load_snapshot(aggregate_id, intended_version=25)
    assert loaded is not None
    assert loaded.version == 20

    # Load at version 35 should get version 30
    loaded = await snapshot_backend_versioned.load_snapshot(aggregate_id, intended_version=35)
    assert loaded is not None
    assert loaded.version == 30


@pytest.mark.asyncio
async def test_load_nonexistent_snapshot(snapshot_backend_single):
    """Test loading non-existent snapshot returns None."""
    aggregate_id = ULID()
    loaded = await snapshot_backend_single.load_snapshot(aggregate_id)
    assert loaded is None


@pytest.mark.asyncio
async def test_list_aggregate_ids_by_type_single_strategy(snapshot_backend_single):
    """Test listing aggregate IDs by type with SINGLE strategy."""
    # Create multiple BankAccount snapshots
    agg1_id = ULID()
    agg2_id = ULID()
    agg3_id = ULID()

    agg1 = BankAccount(id=agg1_id, version=10, balance=1000.0, owner="Alice")
    agg2 = BankAccount(id=agg2_id, version=10, balance=2000.0, owner="Bob")
    agg3 = BankAccount(id=agg3_id, version=10, balance=3000.0, owner="Charlie")

    await snapshot_backend_single.save_snapshot(agg1)
    await snapshot_backend_single.save_snapshot(agg2)
    await snapshot_backend_single.save_snapshot(agg3)

    # List all BankAccount IDs
    ids = await snapshot_backend_single.list_aggregate_ids_by_type(BankAccount)

    assert len(ids) == 3
    assert agg1_id in ids
    assert agg2_id in ids
    assert agg3_id in ids


@pytest.mark.asyncio
async def test_list_aggregate_ids_by_type_versioned_strategy(
    snapshot_backend_versioned,
):
    """Test listing aggregate IDs by type with VERSIONED strategy."""
    agg1_id = ULID()
    agg2_id = ULID()

    # Save multiple versions of same aggregates
    agg1_v1 = BankAccount(id=agg1_id, version=10, balance=1000.0, owner="Alice")
    agg1_v2 = BankAccount(id=agg1_id, version=20, balance=1500.0, owner="Alice")
    agg2_v1 = BankAccount(id=agg2_id, version=10, balance=2000.0, owner="Bob")

    await snapshot_backend_versioned.save_snapshot(agg1_v1)
    await snapshot_backend_versioned.save_snapshot(agg1_v2)
    await snapshot_backend_versioned.save_snapshot(agg2_v1)

    # Should return unique aggregate IDs (not duplicate for multiple versions)
    ids = await snapshot_backend_versioned.list_aggregate_ids_by_type(BankAccount)

    assert len(ids) == 2
    assert agg1_id in ids
    assert agg2_id in ids


@pytest.mark.asyncio
async def test_list_aggregate_ids_empty(snapshot_backend_single):
    """Test listing aggregate IDs when none exist."""
    ids = await snapshot_backend_single.list_aggregate_ids_by_type(BankAccount)
    assert ids == []


@pytest.mark.asyncio
async def test_multiple_aggregates_isolation(snapshot_backend_single):
    """Test that snapshots for different aggregates are isolated."""
    agg1_id = ULID()
    agg2_id = ULID()

    agg1 = BankAccount(id=agg1_id, version=10, balance=1000.0, owner="Alice")
    agg2 = BankAccount(id=agg2_id, version=10, balance=2000.0, owner="Bob")

    await snapshot_backend_single.save_snapshot(agg1)
    await snapshot_backend_single.save_snapshot(agg2)

    loaded1 = await snapshot_backend_single.load_snapshot(agg1_id)
    loaded2 = await snapshot_backend_single.load_snapshot(agg2_id)

    assert loaded1 is not None
    assert loaded2 is not None
    assert loaded1.owner == "Alice"
    assert loaded2.owner == "Bob"
    assert loaded1.balance == 1000.0
    assert loaded2.balance == 2000.0
