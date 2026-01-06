"""Integration tests for MongoEventStore."""

from uuid import uuid4

import pytest
import pytest_asyncio
from pydantic import BaseModel

from interlock.domain import Event
from interlock.domain.exceptions import ConcurrencyError
from interlock.integrations.mongodb import MongoConfiguration, MongoEventStore


class AccountCreated(BaseModel):
    owner: str


class MoneyDeposited(BaseModel):
    amount: int


@pytest_asyncio.fixture
async def event_store(mongo_config: MongoConfiguration):
    """Create a MongoEventStore for testing."""
    return MongoEventStore(mongo_config)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_save_and_load_events(event_store: MongoEventStore):
    """Test saving and loading events."""
    aggregate_id = uuid4()

    events = [
        Event(
            aggregate_id=aggregate_id,
            sequence_number=1,
            data=AccountCreated(owner="Alice"),
        ),
        Event(
            aggregate_id=aggregate_id,
            sequence_number=2,
            data=MoneyDeposited(amount=100),
        ),
    ]

    await event_store.save_events(events, expected_version=0)

    loaded = await event_store.load_events(aggregate_id, min_version=0)

    assert len(loaded) == 2
    assert loaded[0].sequence_number == 1
    assert isinstance(loaded[0].data, AccountCreated)
    assert loaded[0].data.owner == "Alice"
    assert loaded[1].sequence_number == 2
    assert isinstance(loaded[1].data, MoneyDeposited)
    assert loaded[1].data.amount == 100


@pytest.mark.integration
@pytest.mark.asyncio
async def test_load_events_with_min_version(event_store: MongoEventStore):
    """Test loading events with min_version filter."""
    aggregate_id = uuid4()

    events = [
        Event(
            aggregate_id=aggregate_id,
            sequence_number=1,
            data=AccountCreated(owner="Bob"),
        ),
        Event(
            aggregate_id=aggregate_id,
            sequence_number=2,
            data=MoneyDeposited(amount=50),
        ),
        Event(
            aggregate_id=aggregate_id,
            sequence_number=3,
            data=MoneyDeposited(amount=75),
        ),
    ]

    await event_store.save_events(events, expected_version=0)

    # Load only events from version 2 onwards
    loaded = await event_store.load_events(aggregate_id, min_version=2)

    assert len(loaded) == 2
    assert loaded[0].sequence_number == 2
    assert loaded[1].sequence_number == 3


@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrency_error_on_version_mismatch(event_store: MongoEventStore):
    """Test that saving with wrong expected_version raises ConcurrencyError."""
    aggregate_id = uuid4()

    events = [
        Event(
            aggregate_id=aggregate_id,
            sequence_number=1,
            data=AccountCreated(owner="Charlie"),
        ),
    ]

    await event_store.save_events(events, expected_version=0)

    # Try to save with wrong expected version
    new_events = [
        Event(
            aggregate_id=aggregate_id,
            sequence_number=2,
            data=MoneyDeposited(amount=100),
        ),
    ]

    with pytest.raises(ConcurrencyError):
        await event_store.save_events(new_events, expected_version=0)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrency_error_on_duplicate_sequence(event_store: MongoEventStore):
    """Test that duplicate sequence numbers raise ConcurrencyError."""
    aggregate_id = uuid4()

    events = [
        Event(
            aggregate_id=aggregate_id,
            sequence_number=1,
            data=AccountCreated(owner="Dave"),
        ),
    ]

    await event_store.save_events(events, expected_version=0)

    # Try to save with duplicate sequence number
    duplicate_events = [
        Event(
            aggregate_id=aggregate_id,
            sequence_number=1,
            data=MoneyDeposited(amount=100),
        ),
    ]

    with pytest.raises(ConcurrencyError):
        await event_store.save_events(duplicate_events, expected_version=0)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_save_multiple_batches(event_store: MongoEventStore):
    """Test saving events in multiple batches."""
    aggregate_id = uuid4()

    batch1 = [
        Event(
            aggregate_id=aggregate_id,
            sequence_number=1,
            data=AccountCreated(owner="Eve"),
        ),
    ]
    await event_store.save_events(batch1, expected_version=0)

    batch2 = [
        Event(
            aggregate_id=aggregate_id,
            sequence_number=2,
            data=MoneyDeposited(amount=100),
        ),
    ]
    await event_store.save_events(batch2, expected_version=1)

    loaded = await event_store.load_events(aggregate_id, min_version=0)
    assert len(loaded) == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_load_events_for_nonexistent_aggregate(event_store: MongoEventStore):
    """Test loading events for an aggregate with no events."""
    aggregate_id = uuid4()

    loaded = await event_store.load_events(aggregate_id, min_version=0)

    assert loaded == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_save_empty_events_list(event_store: MongoEventStore):
    """Test that saving empty events list is a no-op."""
    await event_store.save_events([], expected_version=0)
    # Should not raise any errors


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rewrite_events(event_store: MongoEventStore):
    """Test rewriting events for schema migration."""
    aggregate_id = uuid4()

    events = [
        Event(
            aggregate_id=aggregate_id,
            sequence_number=1,
            data=AccountCreated(owner="Original"),
        ),
    ]
    await event_store.save_events(events, expected_version=0)

    # Rewrite with updated data
    updated_events = [
        Event(
            id=events[0].id,
            aggregate_id=aggregate_id,
            sequence_number=1,
            timestamp=events[0].timestamp,
            data=AccountCreated(owner="Updated"),
        ),
    ]
    await event_store.rewrite_events(updated_events)

    loaded = await event_store.load_events(aggregate_id, min_version=0)
    assert len(loaded) == 1
    assert loaded[0].data.owner == "Updated"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_events_preserve_correlation_and_causation_ids(
    event_store: MongoEventStore,
):
    """Test that correlation and causation IDs are preserved."""
    aggregate_id = uuid4()
    correlation_id = uuid4()
    causation_id = uuid4()

    events = [
        Event(
            aggregate_id=aggregate_id,
            sequence_number=1,
            data=AccountCreated(owner="Frank"),
            correlation_id=correlation_id,
            causation_id=causation_id,
        ),
    ]

    await event_store.save_events(events, expected_version=0)

    loaded = await event_store.load_events(aggregate_id, min_version=0)

    assert len(loaded) == 1
    assert loaded[0].correlation_id == correlation_id
    assert loaded[0].causation_id == causation_id
