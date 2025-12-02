"""Integration tests for Neo4jEventStore using real Neo4j via testcontainers."""

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from pydantic import BaseModel
from testcontainers.neo4j import Neo4jContainer
from ulid import ULID

from interlock.domain.exceptions import ConcurrencyError
from interlock.domain import Event
from interlock.integrations.neo4j import (
    Neo4jConfig,
    Neo4jConnectionManager,
    Neo4jEventStore,
)


class OrderCreated(BaseModel):
    """Sample event data."""

    customer_id: str
    total: float


class ItemAdded(BaseModel):
    """Sample event data."""

    product_id: str
    quantity: int


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
    """Create and initialize event store."""
    store = Neo4jEventStore(connection_manager)
    await store.initialize_schema()
    yield store
    # Cleanup: Delete all data after each test
    async with connection_manager.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")


@pytest.mark.asyncio
async def test_save_and_load_single_event(event_store):
    """Test saving and loading a single event."""
    aggregate_id = ULID()
    event = Event(
        id=ULID(),
        aggregate_id=aggregate_id,
        sequence_number=1,
        timestamp=datetime.now(timezone.utc),
        data=OrderCreated(customer_id="CUST123", total=99.99),
    )

    await event_store.save_events([event], expected_version=0)
    loaded_events = await event_store.load_events(aggregate_id)

    assert len(loaded_events) == 1
    assert loaded_events[0].aggregate_id == aggregate_id
    assert loaded_events[0].sequence_number == 1
    assert loaded_events[0].data.customer_id == "CUST123"
    assert loaded_events[0].data.total == 99.99


@pytest.mark.asyncio
async def test_save_and_load_multiple_events(event_store):
    """Test saving and loading multiple events in order."""
    aggregate_id = ULID()
    events = [
        Event(
            id=ULID(),
            aggregate_id=aggregate_id,
            sequence_number=1,
            timestamp=datetime.now(timezone.utc),
            data=OrderCreated(customer_id="CUST456", total=150.00),
        ),
        Event(
            id=ULID(),
            aggregate_id=aggregate_id,
            sequence_number=2,
            timestamp=datetime.now(timezone.utc),
            data=ItemAdded(product_id="PROD1", quantity=2),
        ),
        Event(
            id=ULID(),
            aggregate_id=aggregate_id,
            sequence_number=3,
            timestamp=datetime.now(timezone.utc),
            data=ItemAdded(product_id="PROD2", quantity=1),
        ),
    ]

    await event_store.save_events(events, expected_version=0)
    loaded_events = await event_store.load_events(aggregate_id)

    assert len(loaded_events) == 3
    assert loaded_events[0].sequence_number == 1
    assert loaded_events[1].sequence_number == 2
    assert loaded_events[2].sequence_number == 3
    assert isinstance(loaded_events[0].data, OrderCreated)
    assert isinstance(loaded_events[1].data, ItemAdded)
    assert isinstance(loaded_events[2].data, ItemAdded)


@pytest.mark.asyncio
async def test_load_events_from_version(event_store):
    """Test loading events from a specific version."""
    aggregate_id = ULID()
    events = [
        Event(
            id=ULID(),
            aggregate_id=aggregate_id,
            sequence_number=i,
            timestamp=datetime.now(timezone.utc),
            data=ItemAdded(product_id=f"PROD{i}", quantity=1),
        )
        for i in range(1, 6)
    ]

    await event_store.save_events(events, expected_version=0)
    loaded_events = await event_store.load_events(aggregate_id, min_version=3)

    assert len(loaded_events) == 3
    assert loaded_events[0].sequence_number == 3
    assert loaded_events[1].sequence_number == 4
    assert loaded_events[2].sequence_number == 5


@pytest.mark.asyncio
async def test_append_events_to_existing_stream(event_store):
    """Test appending new events to an existing stream."""
    aggregate_id = ULID()

    # Save initial events
    initial_events = [
        Event(
            id=ULID(),
            aggregate_id=aggregate_id,
            sequence_number=1,
            timestamp=datetime.now(timezone.utc),
            data=OrderCreated(customer_id="CUST789", total=200.00),
        ),
    ]
    await event_store.save_events(initial_events, expected_version=0)

    # Append more events
    new_events = [
        Event(
            id=ULID(),
            aggregate_id=aggregate_id,
            sequence_number=2,
            timestamp=datetime.now(timezone.utc),
            data=ItemAdded(product_id="PROD3", quantity=3),
        ),
    ]
    await event_store.save_events(new_events, expected_version=1)

    # Load all events
    all_events = await event_store.load_events(aggregate_id)
    assert len(all_events) == 2
    assert all_events[0].sequence_number == 1
    assert all_events[1].sequence_number == 2


@pytest.mark.asyncio
async def test_concurrency_conflict_detection(event_store):
    """Test that concurrent writes are detected."""
    aggregate_id = ULID()

    # Save initial event
    event1 = Event(
        id=ULID(),
        aggregate_id=aggregate_id,
        sequence_number=1,
        timestamp=datetime.now(timezone.utc),
        data=OrderCreated(customer_id="CUST999", total=50.00),
    )
    await event_store.save_events([event1], expected_version=0)

    # Try to save with wrong expected version
    event2 = Event(
        id=ULID(),
        aggregate_id=aggregate_id,
        sequence_number=2,
        timestamp=datetime.now(timezone.utc),
        data=ItemAdded(product_id="PROD4", quantity=1),
    )

    with pytest.raises(ConcurrencyError) as exc_info:
        await event_store.save_events([event2], expected_version=0)

    assert "Expected version 0, got 1" in str(exc_info.value)


@pytest.mark.asyncio
async def test_load_nonexistent_aggregate(event_store):
    """Test loading events for non-existent aggregate returns empty list."""
    aggregate_id = ULID()
    events = await event_store.load_events(aggregate_id)
    assert events == []


@pytest.mark.asyncio
async def test_multiple_aggregates_isolation(event_store):
    """Test that events for different aggregates are isolated."""
    agg1_id = ULID()
    agg2_id = ULID()

    event1 = Event(
        id=ULID(),
        aggregate_id=agg1_id,
        sequence_number=1,
        timestamp=datetime.now(timezone.utc),
        data=OrderCreated(customer_id="CUST1", total=100.00),
    )
    event2 = Event(
        id=ULID(),
        aggregate_id=agg2_id,
        sequence_number=1,
        timestamp=datetime.now(timezone.utc),
        data=OrderCreated(customer_id="CUST2", total=200.00),
    )

    await event_store.save_events([event1], expected_version=0)
    await event_store.save_events([event2], expected_version=0)

    agg1_events = await event_store.load_events(agg1_id)
    agg2_events = await event_store.load_events(agg2_id)

    assert len(agg1_events) == 1
    assert len(agg2_events) == 1
    assert agg1_events[0].data.customer_id == "CUST1"
    assert agg2_events[0].data.customer_id == "CUST2"
