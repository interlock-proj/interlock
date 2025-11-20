"""Integration tests for Neo4jSnapshotBackend using real Neo4j via testcontainers."""

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from pydantic import BaseModel
from testcontainers.neo4j import Neo4jContainer
from ulid import ULID

from interlock.aggregates.aggregate import Aggregate
from interlock.events import Event
from interlock.integrations.neo4j import (
    Neo4jConfig,
    Neo4jConnectionManager,
    Neo4jEventStore,
    Neo4jSnapshotBackend,
    SnapshotStorageStrategy,
)


class OrderAggregate(Aggregate):
    """Sample aggregate for testing."""

    customer_id: str = ""
    total: float = 0.0
    item_count: int = 0


class DummyEvent(BaseModel):
    """Dummy event for creating events in Neo4j."""

    value: str


@pytest.fixture(scope="module")
def neo4j_container():
    """Start Neo4j container for tests."""
    # Use proper authentication credentials
    container = Neo4jContainer("neo4j:5", password="testpassword")
    with container:
        yield container


@pytest_asyncio.fixture
async def connection_manager(neo4j_container):
    """Create connection manager for Neo4j container."""
    config = Neo4jConfig(
        uri=neo4j_container.get_connection_url(),
        username=neo4j_container.username,
        password=neo4j_container.password,
    )
    async with Neo4jConnectionManager(config) as manager:
        yield manager


@pytest_asyncio.fixture
async def event_store(connection_manager):
    """Create and initialize event store (needed for snapshot relationships)."""
    store = Neo4jEventStore(connection_manager)
    await store.initialize_schema()
    yield store
    # Cleanup: Delete all data after each test
    async with connection_manager.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")


@pytest_asyncio.fixture
async def snapshot_backend_single(connection_manager):
    """Create snapshot backend with SINGLE strategy."""
    backend = Neo4jSnapshotBackend(connection_manager, strategy=SnapshotStorageStrategy.SINGLE)
    await backend.initialize_schema()
    return backend


@pytest_asyncio.fixture
async def snapshot_backend_versioned(connection_manager):
    """Create snapshot backend with VERSIONED strategy."""
    backend = Neo4jSnapshotBackend(connection_manager, strategy=SnapshotStorageStrategy.VERSIONED)
    await backend.initialize_schema()
    return backend


async def create_dummy_events(event_store, aggregate_id, count):
    """Helper to create dummy events for an aggregate."""
    events = [
        Event(
            id=ULID(),
            aggregate_id=aggregate_id,
            sequence_number=i,
            timestamp=datetime.now(timezone.utc),
            data=DummyEvent(value=f"event{i}"),
        )
        for i in range(1, count + 1)
    ]
    await event_store.save_events(events, expected_version=0)


@pytest.mark.asyncio
async def test_save_and_load_snapshot_single_strategy(snapshot_backend_single, event_store):
    """Test saving and loading snapshot with SINGLE strategy."""
    aggregate = OrderAggregate(
        id=ULID(), version=5, customer_id="CUST123", total=99.99, item_count=3
    )

    # Create events first (snapshots link to events)
    await create_dummy_events(event_store, aggregate.id, 5)

    # Mark snapshot time and save
    aggregate.mark_snapshot()
    await snapshot_backend_single.save_snapshot(aggregate)

    # Load snapshot
    loaded = await snapshot_backend_single.load_snapshot(aggregate.id)

    assert loaded is not None
    assert loaded.id == aggregate.id
    assert loaded.version == 5
    assert loaded.customer_id == "CUST123"
    assert loaded.total == 99.99
    assert loaded.item_count == 3


@pytest.mark.asyncio
async def test_single_strategy_overwrites(snapshot_backend_single, event_store):
    """Test that SINGLE strategy overwrites previous snapshot."""
    aggregate_id = ULID()

    # Create events
    await create_dummy_events(event_store, aggregate_id, 10)

    # Save first snapshot
    snapshot1 = OrderAggregate(id=aggregate_id, version=5, customer_id="CUST1", total=100.00)
    snapshot1.mark_snapshot()
    await snapshot_backend_single.save_snapshot(snapshot1)

    # Save second snapshot (should overwrite)
    snapshot2 = OrderAggregate(id=aggregate_id, version=10, customer_id="CUST2", total=200.00)
    snapshot2.mark_snapshot()
    await snapshot_backend_single.save_snapshot(snapshot2)

    # Load - should get latest
    loaded = await snapshot_backend_single.load_snapshot(aggregate_id)

    assert loaded.version == 10
    assert loaded.customer_id == "CUST2"
    assert loaded.total == 200.00


@pytest.mark.asyncio
async def test_versioned_strategy_keeps_all(snapshot_backend_versioned, event_store):
    """Test that VERSIONED strategy keeps all snapshots."""
    aggregate_id = ULID()

    # Create events
    await create_dummy_events(event_store, aggregate_id, 15)

    # Save multiple snapshots
    for version in [5, 10, 15]:
        snapshot = OrderAggregate(
            id=aggregate_id,
            version=version,
            customer_id=f"CUST{version}",
            total=version * 10.0,
        )
        snapshot.mark_snapshot()
        await snapshot_backend_versioned.save_snapshot(snapshot)

    # Load latest
    loaded = await snapshot_backend_versioned.load_snapshot(aggregate_id)
    assert loaded.version == 15

    # Load at specific version
    loaded_v10 = await snapshot_backend_versioned.load_snapshot(aggregate_id, intended_version=10)
    assert loaded_v10.version == 10
    assert loaded_v10.customer_id == "CUST10"

    # Load at version below all snapshots
    loaded_v3 = await snapshot_backend_versioned.load_snapshot(aggregate_id, intended_version=3)
    assert loaded_v3 is None


@pytest.mark.asyncio
async def test_load_snapshot_with_intended_version(snapshot_backend_versioned, event_store):
    """Test loading snapshot at or below intended version."""
    aggregate_id = ULID()

    # Create events
    await create_dummy_events(event_store, aggregate_id, 20)

    # Save snapshots at versions 5, 10, 15
    for version in [5, 10, 15]:
        snapshot = OrderAggregate(id=aggregate_id, version=version, total=float(version))
        snapshot.mark_snapshot()
        await snapshot_backend_versioned.save_snapshot(snapshot)

    # Request version 12 - should get version 10
    loaded = await snapshot_backend_versioned.load_snapshot(aggregate_id, intended_version=12)
    assert loaded.version == 10

    # Request version 20 - should get version 15
    loaded = await snapshot_backend_versioned.load_snapshot(aggregate_id, intended_version=20)
    assert loaded.version == 15


@pytest.mark.asyncio
async def test_load_nonexistent_snapshot(snapshot_backend_single):
    """Test loading snapshot for non-existent aggregate."""
    aggregate_id = ULID()
    loaded = await snapshot_backend_single.load_snapshot(aggregate_id)
    assert loaded is None


@pytest.mark.asyncio
async def test_multiple_aggregates_isolation(snapshot_backend_single, event_store):
    """Test that snapshots for different aggregates are isolated."""
    agg1_id = ULID()
    agg2_id = ULID()

    # Create events for both
    await create_dummy_events(event_store, agg1_id, 5)
    await create_dummy_events(event_store, agg2_id, 5)

    # Save snapshots
    snapshot1 = OrderAggregate(id=agg1_id, version=5, customer_id="CUST1", total=100.00)
    snapshot1.mark_snapshot()
    await snapshot_backend_single.save_snapshot(snapshot1)

    snapshot2 = OrderAggregate(id=agg2_id, version=5, customer_id="CUST2", total=200.00)
    snapshot2.mark_snapshot()
    await snapshot_backend_single.save_snapshot(snapshot2)

    # Load each
    loaded1 = await snapshot_backend_single.load_snapshot(agg1_id)
    loaded2 = await snapshot_backend_single.load_snapshot(agg2_id)

    assert loaded1.customer_id == "CUST1"
    assert loaded2.customer_id == "CUST2"
    assert loaded1.total == 100.00
    assert loaded2.total == 200.00


@pytest.mark.asyncio
async def test_snapshot_preserves_aggregate_state(snapshot_backend_single, event_store):
    """Test that snapshot correctly preserves all aggregate state."""
    aggregate = OrderAggregate(
        id=ULID(),
        version=10,
        customer_id="CUST_COMPLEX",
        total=999.99,
        item_count=42,
    )

    # Create events
    await create_dummy_events(event_store, aggregate.id, 10)

    # Save and reload
    aggregate.mark_snapshot()
    await snapshot_backend_single.save_snapshot(aggregate)
    loaded = await snapshot_backend_single.load_snapshot(aggregate.id)

    # Verify all fields
    assert loaded.id == aggregate.id
    assert loaded.version == aggregate.version
    assert loaded.customer_id == aggregate.customer_id
    assert loaded.total == aggregate.total
    assert loaded.item_count == aggregate.item_count
    # Verify uncommitted_events is excluded
    assert loaded.uncommitted_events == []
