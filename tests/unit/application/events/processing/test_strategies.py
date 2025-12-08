"""Tests for catchup strategies."""

import pytest
from datetime import datetime, timedelta, timezone
from ulid import ULID

from interlock.application.events.processing.processor import EventProcessor
from interlock.application.events.processing.strategies import (
    CatchupResult,
    NoCatchup,
)
from interlock.domain import Event
from pydantic import BaseModel


class TestEvent(BaseModel):
    """Test event for CatchupResult tests."""
    value: str


# CatchupResult Tests


def test_catchup_result_creation_with_skip_before():
    """Test CatchupResult creation with skip_before timestamp."""
    timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    result = CatchupResult(skip_before=timestamp)
    assert result.skip_before == timestamp


def test_catchup_result_creation_without_skip_before():
    """Test CatchupResult creation with None skip_before."""
    result = CatchupResult()
    assert result.skip_before is None


def test_catchup_result_should_skip_with_none():
    """Test should_skip returns False when skip_before is None."""
    result = CatchupResult(skip_before=None)
    event = Event(
        id=ULID(),
        aggregate_id=ULID(),
        data=TestEvent(value="test"),
        sequence_number=1,
        timestamp=datetime.now(timezone.utc),
    )
    assert not result.should_skip(event)


def test_catchup_result_should_skip_older_event():
    """Test should_skip returns True for events before skip_before."""
    skip_before = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    result = CatchupResult(skip_before=skip_before)

    old_event = Event(
        id=ULID(),
        aggregate_id=ULID(),
        data=TestEvent(value="old"),
        sequence_number=1,
        timestamp=datetime(2025, 1, 1, 11, 0, 0, tzinfo=timezone.utc),
    )
    assert result.should_skip(old_event)


def test_catchup_result_should_skip_exact_timestamp():
    """Test should_skip returns True for events at exact skip_before."""
    skip_before = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    result = CatchupResult(skip_before=skip_before)

    exact_event = Event(
        id=ULID(),
        aggregate_id=ULID(),
        data=TestEvent(value="exact"),
        sequence_number=1,
        timestamp=skip_before,
    )
    assert result.should_skip(exact_event)


def test_catchup_result_should_not_skip_newer_event():
    """Test should_skip returns False for events after skip_before."""
    skip_before = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    result = CatchupResult(skip_before=skip_before)

    new_event = Event(
        id=ULID(),
        aggregate_id=ULID(),
        data=TestEvent(value="new"),
        sequence_number=1,
        timestamp=datetime(2025, 1, 1, 13, 0, 0, tzinfo=timezone.utc),
    )
    assert not result.should_skip(new_event)


def test_catchup_result_should_skip_boundary_cases():
    """Test should_skip with various boundary conditions."""
    skip_before = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    result = CatchupResult(skip_before=skip_before)

    # One microsecond before
    just_before = Event(
        id=ULID(),
        aggregate_id=ULID(),
        data=TestEvent(value="before"),
        sequence_number=1,
        timestamp=skip_before - timedelta(microseconds=1),
    )
    assert result.should_skip(just_before)

    # One microsecond after
    just_after = Event(
        id=ULID(),
        aggregate_id=ULID(),
        data=TestEvent(value="after"),
        sequence_number=1,
        timestamp=skip_before + timedelta(microseconds=1),
    )
    assert not result.should_skip(just_after)


@pytest.mark.asyncio
async def test_no_catchup_returns_none():
    """Test NoCatchup.catchup returns None."""
    strategy = NoCatchup()
    processor = EventProcessor()

    result = await strategy.catchup(processor)

    assert result is None


@pytest.mark.asyncio
async def test_no_catchup_does_not_modify_processor():
    """Test NoCatchup doesn't modify processor state."""
    strategy = NoCatchup()
    processor = EventProcessor()

    # Add some state to processor
    processor.test_attr = "original"  # type: ignore

    await strategy.catchup(processor)

    # State should be unchanged
    assert processor.test_attr == "original"  # type: ignore
