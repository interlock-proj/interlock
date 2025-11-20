"""Unit tests for Neo4jSnapshotBackend using mocks."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from ulid import ULID

from ouroboros.aggregates.aggregate import Aggregate
from ouroboros.integrations.neo4j import (
    Neo4jConnectionManager,
    Neo4jSnapshotBackend,
    SnapshotStorageStrategy,
)


class SampleAggregate(Aggregate):
    """Sample aggregate for snapshot tests."""

    counter: int = 0


@pytest.fixture
def mock_connection_manager():
    """Create a mock connection manager."""
    return MagicMock(spec=Neo4jConnectionManager)


@pytest.fixture
def snapshot_backend_single(mock_connection_manager):
    """Create snapshot backend with SINGLE strategy."""
    return Neo4jSnapshotBackend(mock_connection_manager, strategy=SnapshotStorageStrategy.SINGLE)


@pytest.fixture
def snapshot_backend_versioned(mock_connection_manager):
    """Create snapshot backend with VERSIONED strategy."""
    return Neo4jSnapshotBackend(mock_connection_manager, strategy=SnapshotStorageStrategy.VERSIONED)


@pytest.mark.asyncio
async def test_initialize_schema(snapshot_backend_single, mock_connection_manager):
    """Test schema initialization creates indexes."""
    mock_session = AsyncMock()
    mock_connection_manager.session.return_value.__aenter__.return_value = mock_session

    await snapshot_backend_single.initialize_schema()

    assert mock_session.run.call_count == 1  # Index only for SINGLE


@pytest.mark.asyncio
async def test_save_snapshot_single_strategy(snapshot_backend_single, mock_connection_manager):
    """Test saving snapshot with SINGLE strategy."""
    aggregate = SampleAggregate(id=ULID(), version=5, counter=10)
    aggregate.mark_snapshot()

    mock_session = AsyncMock()
    mock_connection_manager.session.return_value.__aenter__.return_value = mock_session

    await snapshot_backend_single.save_snapshot(aggregate)

    # Verify run was called with snapshot data
    mock_session.run.assert_called_once()
    call_args = mock_session.run.call_args
    assert call_args[1]["aggregate_id"] == str(aggregate.id)
    assert call_args[1]["version"] == 5


@pytest.mark.asyncio
async def test_save_snapshot_versioned_strategy(
    snapshot_backend_versioned, mock_connection_manager
):
    """Test saving snapshot with VERSIONED strategy."""
    aggregate = SampleAggregate(id=ULID(), version=5, counter=10)
    aggregate.mark_snapshot()

    mock_session = AsyncMock()
    mock_connection_manager.session.return_value.__aenter__.return_value = mock_session

    await snapshot_backend_versioned.save_snapshot(aggregate)

    mock_session.run.assert_called_once()
    call_args = mock_session.run.call_args
    assert call_args[1]["version"] == 5


@pytest.mark.asyncio
async def test_load_snapshot_found(snapshot_backend_single, mock_connection_manager):
    """Test loading existing snapshot."""
    aggregate_id = ULID()

    mock_session = AsyncMock()
    mock_result = AsyncMock()

    snapshot_node = {
        "id": str(ULID()),
        "aggregate_id": str(aggregate_id),
        "version": 5,
        "timestamp": datetime.now(timezone.utc),
        "aggregate_type": "SampleAggregate",
        "aggregate_module": "tests.unit.integrations.neo4j.test_snapshot",
        "state_json": (
            f'{{"id": "{aggregate_id}", "version": 5, "counter": 10, '
            f'"last_snapshot_time": "2024-01-01T00:00:00Z", '
            f'"last_event_time": "2024-01-01T00:00:00Z"}}'
        ),
    }

    mock_result.single.return_value = {"s": snapshot_node}
    mock_session.run.return_value = mock_result
    mock_connection_manager.session.return_value.__aenter__.return_value = mock_session

    snapshot = await snapshot_backend_single.load_snapshot(aggregate_id)

    assert snapshot is not None
    assert snapshot.id == aggregate_id
    assert snapshot.version == 5
    assert snapshot.counter == 10


@pytest.mark.asyncio
async def test_load_snapshot_not_found(snapshot_backend_single, mock_connection_manager):
    """Test loading non-existent snapshot returns None."""
    aggregate_id = ULID()

    mock_session = AsyncMock()
    mock_result = AsyncMock()
    mock_result.single.return_value = None

    mock_session.run.return_value = mock_result
    mock_connection_manager.session.return_value.__aenter__.return_value = mock_session

    snapshot = await snapshot_backend_single.load_snapshot(aggregate_id)

    assert snapshot is None


@pytest.mark.asyncio
async def test_load_snapshot_with_intended_version(
    snapshot_backend_single, mock_connection_manager
):
    """Test loading snapshot with intended version parameter."""
    aggregate_id = ULID()

    mock_session = AsyncMock()
    mock_result = AsyncMock()

    snapshot_node = {
        "id": str(ULID()),
        "aggregate_id": str(aggregate_id),
        "version": 3,
        "timestamp": datetime.now(timezone.utc),
        "aggregate_type": "SampleAggregate",
        "aggregate_module": "tests.unit.integrations.neo4j.test_snapshot",
        "state_json": (
            f'{{"id": "{aggregate_id}", "version": 3, "counter": 5, '
            f'"last_snapshot_time": "2024-01-01T00:00:00Z", '
            f'"last_event_time": "2024-01-01T00:00:00Z"}}'
        ),
    }

    mock_result.single.return_value = {"s": snapshot_node}
    mock_session.run.return_value = mock_result
    mock_connection_manager.session.return_value.__aenter__.return_value = mock_session

    snapshot = await snapshot_backend_single.load_snapshot(aggregate_id, intended_version=5)

    assert snapshot is not None
    assert snapshot.version == 3  # Got version <= 5


@pytest.mark.asyncio
async def test_load_class(snapshot_backend_single):
    """Test dynamic class loading."""
    from ouroboros.aggregates.aggregate import Aggregate

    cls = snapshot_backend_single._load_class("ouroboros.aggregates.aggregate", "Aggregate")
    assert cls == Aggregate
