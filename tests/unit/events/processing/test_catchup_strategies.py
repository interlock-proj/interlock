"""Tests for catchup strategies."""

from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from pydantic import BaseModel
from ulid import ULID

from ouroboros.aggregates.aggregate import Aggregate
from ouroboros.events.event import Event
from ouroboros.events.processing.processor import EventProcessor
from ouroboros.events.processing.projectors import AggregateProjector
from ouroboros.events.processing.strategies import (
    CatchupResult,
    FromAggregateSnapshot,
    NoCatchup,
)
from ouroboros.routing import applies_event, handles_event


class UserCreated(BaseModel):
    name: str
    email: str


class UserUpdated(BaseModel):
    name: str


class User(Aggregate):
    name: str = ""
    email: str = ""

    @applies_event
    def apply_created(self, event: UserCreated) -> None:
        self.name = event.name
        self.email = event.email

    @applies_event
    def apply_updated(self, event: UserUpdated) -> None:
        self.name = event.name


class UserProfileProcessor(EventProcessor):
    def __init__(self):
        self.profiles: dict[ULID, dict] = {}

    @handles_event
    async def on_user_created(self, event: UserCreated) -> None:
        pass


class UserProfileProjector(AggregateProjector[User, UserProfileProcessor]):
    async def project(self, aggregate: User, processor: UserProfileProcessor) -> None:
        processor.profiles[aggregate.id] = {
            "name": aggregate.name,
            "email": aggregate.email,
            "version": aggregate.version,
        }


@pytest.mark.asyncio
async def test_no_catchup_returns_none():
    """Test that NoCatchup.catchup() returns None."""
    strategy = NoCatchup()
    processor = UserProfileProcessor()

    result = await strategy.catchup(processor)

    assert result is None


def test_no_catchup_is_not_blocking():
    """Test that NoCatchup is non-blocking."""
    strategy = NoCatchup()
    assert strategy.is_blocking() is False


def test_catchup_result_with_skip_window():
    """Test CatchupResult with a skip window."""
    skip_before = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    result = CatchupResult(skip_before=skip_before)

    old_event = Event(
        aggregate_id=ULID(),
        data=UserCreated(name="Test", email="test@example.com"),
        sequence_number=1,
        timestamp=datetime(2025, 1, 1, 11, 0, 0, tzinfo=timezone.utc),
    )
    assert result.should_skip(old_event) is True

    exact_event = Event(
        aggregate_id=ULID(),
        data=UserCreated(name="Test", email="test@example.com"),
        sequence_number=1,
        timestamp=skip_before,
    )
    assert result.should_skip(exact_event) is True

    new_event = Event(
        aggregate_id=ULID(),
        data=UserCreated(name="Test", email="test@example.com"),
        sequence_number=1,
        timestamp=datetime(2025, 1, 1, 13, 0, 0, tzinfo=timezone.utc),
    )
    assert result.should_skip(new_event) is False


def test_catchup_result_without_skip_window():
    """Test CatchupResult with no skip window."""
    result = CatchupResult(skip_before=None)

    event = Event(
        aggregate_id=ULID(),
        data=UserCreated(name="Test", email="test@example.com"),
        sequence_number=1,
    )
    assert result.should_skip(event) is False


def test_from_aggregate_snapshot_is_blocking():
    """Test that FromAggregateSnapshot is blocking."""
    strategy = FromAggregateSnapshot(
        repository=Mock(),
        projector=Mock(),
        checkpoint_backend=Mock(),
    )
    assert strategy.is_blocking() is True
