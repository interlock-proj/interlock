"""Unit tests for Neo4jEventStore using mocks."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel
from ulid import ULID

from interlock.domain.exceptions import ConcurrencyError
from interlock.domain import Event
from interlock.integrations.neo4j import Neo4jConnectionManager, Neo4jEventStore


class SampleEventData(BaseModel):
    """Sample event data model for testing."""

    value: str


@pytest.fixture
def mock_connection_manager():
    """Create a mock connection manager."""
    manager = MagicMock(spec=Neo4jConnectionManager)
    return manager


@pytest.fixture
def event_store(mock_connection_manager):
    """Create event store with mocked connection."""
    return Neo4jEventStore(mock_connection_manager)


@pytest.mark.asyncio
async def test_initialize_schema(event_store, mock_connection_manager):
    """Test schema initialization creates indexes and constraints."""
    mock_session = AsyncMock()
    mock_connection_manager.session.return_value.__aenter__.return_value = mock_session

    await event_store.initialize_schema()

    assert mock_session.run.call_count == 2  # 1 constraint + 1 index


@pytest.mark.asyncio
async def test_save_events_empty_list(event_store):
    """Test saving empty event list does nothing."""
    await event_store.save_events([], expected_version=0)
    # Should return early without any DB operations


@pytest.mark.asyncio
async def test_save_events_success(event_store, mock_connection_manager):
    """Test successful event save."""
    aggregate_id = ULID()
    event = Event(
        id=ULID(),
        aggregate_id=aggregate_id,
        sequence_number=1,
        timestamp=datetime.now(timezone.utc),
        data=SampleEventData(value="test"),
    )

    mock_tx = AsyncMock()
    mock_result = AsyncMock()
    mock_result.single.return_value = {"current_version": 0}
    mock_tx.run.return_value = mock_result

    mock_connection_manager.transaction.return_value.__aenter__.return_value = mock_tx

    await event_store.save_events([event], expected_version=0)

    # Verify transaction was used
    assert mock_tx.run.call_count >= 2  # Version check + event creation


@pytest.mark.asyncio
async def test_save_events_concurrency_conflict(event_store, mock_connection_manager):
    """Test concurrency exception raised on version mismatch."""
    aggregate_id = ULID()
    event = Event(
        id=ULID(),
        aggregate_id=aggregate_id,
        sequence_number=1,
        timestamp=datetime.now(timezone.utc),
        data=SampleEventData(value="test"),
    )

    mock_tx = AsyncMock()
    mock_result = AsyncMock()
    mock_result.single.return_value = {"current_version": 5}  # Mismatch!
    mock_tx.run.return_value = mock_result

    mock_connection_manager.transaction.return_value.__aenter__.return_value = mock_tx

    with pytest.raises(ConcurrencyError) as exc_info:
        await event_store.save_events([event], expected_version=0)

    assert "Expected version 0, got 5" in str(exc_info.value)


@pytest.mark.asyncio
async def test_load_events(event_store, mock_connection_manager):
    """Test loading events from store."""
    aggregate_id = ULID()

    # Mock Neo4j result
    mock_session = AsyncMock()
    mock_result = AsyncMock()

    event_node = {
        "id": str(ULID()),
        "aggregate_id": str(aggregate_id),
        "sequence_number": 1,
        "timestamp": datetime.now(timezone.utc),
        "data_type": "SampleEventData",
        "data_module": "tests.unit.integrations.neo4j.test_event_store",
        "data_json": '{"value": "test"}',
    }

    # Make async iteration work
    async def async_iter(self):
        yield {"e": event_node}

    mock_result.__aiter__ = async_iter
    mock_session.run.return_value = mock_result
    mock_connection_manager.session.return_value.__aenter__.return_value = mock_session

    events = await event_store.load_events(aggregate_id, min_version=0)

    assert len(events) == 1
    assert events[0].aggregate_id == aggregate_id
    assert events[0].sequence_number == 1


@pytest.mark.asyncio
async def test_load_class_success(event_store):
    """Test dynamic class loading."""
    cls = event_store._load_class("pydantic", "BaseModel")
    assert cls == BaseModel


@pytest.mark.asyncio
async def test_load_class_invalid_module(event_store):
    """Test dynamic class loading with invalid module."""
    with pytest.raises(ModuleNotFoundError):
        event_store._load_class("nonexistent.module", "SomeClass")
