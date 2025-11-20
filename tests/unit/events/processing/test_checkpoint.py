"""Tests for checkpoint backend implementations."""

from datetime import datetime

import pytest
from ulid import ULID

from interlock.events.processing.checkpoint import (
    Checkpoint,
    InMemoryCheckpointBackend,
)


def test_checkpoint_creation():
    """Test creating a checkpoint with all fields."""
    processor_name = "TestProcessor"
    processed_ids = {ULID(), ULID()}
    max_timestamp = datetime(2025, 1, 1, 12, 0, 0)
    events_processed = 1500

    checkpoint = Checkpoint(
        processor_name=processor_name,
        processed_aggregate_ids=processed_ids,
        max_timestamp=max_timestamp,
        events_processed=events_processed,
    )

    assert checkpoint.processor_name == processor_name
    assert checkpoint.processed_aggregate_ids == processed_ids
    assert checkpoint.max_timestamp == max_timestamp
    assert checkpoint.events_processed == events_processed


@pytest.fixture
def checkpoint_backend():
    """Create a fresh in-memory checkpoint backend."""
    return InMemoryCheckpointBackend()


@pytest.mark.asyncio
async def test_load_nonexistent_checkpoint(checkpoint_backend):
    """Test loading a checkpoint that doesn't exist returns None."""
    result = await checkpoint_backend.load_checkpoint("NonexistentProcessor")
    assert result is None


@pytest.mark.asyncio
async def test_save_and_load_checkpoint(checkpoint_backend):
    """Test saving and loading a checkpoint."""
    checkpoint = Checkpoint(
        processor_name="TestProcessor",
        processed_aggregate_ids={ULID(), ULID()},
        max_timestamp=datetime(2025, 1, 1, 12, 0, 0),
        events_processed=100,
    )

    await checkpoint_backend.save_checkpoint(checkpoint)
    loaded = await checkpoint_backend.load_checkpoint("TestProcessor")

    assert loaded is not None
    assert loaded.processor_name == checkpoint.processor_name
    assert loaded.processed_aggregate_ids == checkpoint.processed_aggregate_ids
    assert loaded.max_timestamp == checkpoint.max_timestamp
    assert loaded.events_processed == checkpoint.events_processed


@pytest.mark.asyncio
async def test_save_overwrites_existing_checkpoint(checkpoint_backend):
    """Test that saving a checkpoint overwrites the previous one."""
    checkpoint1 = Checkpoint(
        processor_name="TestProcessor",
        processed_aggregate_ids={ULID()},
        max_timestamp=datetime(2025, 1, 1, 12, 0, 0),
        events_processed=50,
    )

    checkpoint2 = Checkpoint(
        processor_name="TestProcessor",
        processed_aggregate_ids={ULID(), ULID()},
        max_timestamp=datetime(2025, 1, 1, 13, 0, 0),
        events_processed=150,
    )

    await checkpoint_backend.save_checkpoint(checkpoint1)
    await checkpoint_backend.save_checkpoint(checkpoint2)

    loaded = await checkpoint_backend.load_checkpoint("TestProcessor")

    assert loaded is not None
    assert loaded.events_processed == 150
    assert len(loaded.processed_aggregate_ids) == 2


@pytest.mark.asyncio
async def test_multiple_processors(checkpoint_backend):
    """Test that different processors have separate checkpoints."""
    checkpoint1 = Checkpoint(
        processor_name="Processor1",
        processed_aggregate_ids={ULID()},
        max_timestamp=datetime(2025, 1, 1, 12, 0, 0),
        events_processed=100,
    )

    checkpoint2 = Checkpoint(
        processor_name="Processor2",
        processed_aggregate_ids={ULID(), ULID()},
        max_timestamp=datetime(2025, 1, 1, 13, 0, 0),
        events_processed=200,
    )

    await checkpoint_backend.save_checkpoint(checkpoint1)
    await checkpoint_backend.save_checkpoint(checkpoint2)

    loaded1 = await checkpoint_backend.load_checkpoint("Processor1")
    loaded2 = await checkpoint_backend.load_checkpoint("Processor2")

    assert loaded1 is not None
    assert loaded2 is not None
    assert loaded1.events_processed == 100
    assert loaded2.events_processed == 200
    assert len(loaded1.processed_aggregate_ids) == 1
    assert len(loaded2.processed_aggregate_ids) == 2
