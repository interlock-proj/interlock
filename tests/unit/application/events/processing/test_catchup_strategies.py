"""Tests for catchup strategies."""

from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from pydantic import BaseModel
from ulid import ULID

from interlock.application.events.processing.processor import EventProcessor
from interlock.application.events.processing.projectors import AggregateProjector
from interlock.application.events.processing.strategies import (
    CatchupResult,
    FromAggregateSnapshot,
    NoCatchup,
)
from interlock.domain import Aggregate, Event
from interlock.routing import applies_event, handles_event


class UserCreated(BaseModel):
    name: str
    email: str


class UserUpdated(BaseModel):
    name: str


class User(Aggregate):
    name: str = ""
    email: str = ""

    @applies_event
    def apply_created(self, event: UserCreated):
        self.name = event.name
        self.email = event.email

    @applies_event
    def apply_updated(self, event: UserUpdated):
        self.name = event.name


class UserProcessor(EventProcessor):
    def __init__(self):
        super().__init__()
        self.users = {}

    @handles_event
    def handle_created(self, event: UserCreated):
        pass

    @handles_event
    def handle_updated(self, event: UserUpdated):
        pass


class UserProjector(AggregateProjector[User, UserProcessor]):
    def project(self, aggregate: User, processor: UserProcessor):
        processor.users[str(aggregate.id)] = {
            "name": aggregate.name,
            "email": aggregate.email,
        }


def create_event(aggregate_id: ULID, sequence_number: int, data: BaseModel) -> Event:
    return Event(
        id=ULID(),
        aggregate_id=aggregate_id,
        sequence_number=sequence_number,
        timestamp=datetime.now(timezone.utc),
        data=data,
    )


@pytest.mark.asyncio
async def test_no_catchup_returns_none():
    """Test NoCatchup strategy returns None immediately."""
    strategy = NoCatchup()
    processor = UserProcessor()

    result = await strategy.catchup(processor)

    assert result is None


@pytest.mark.skip(reason="Test needs refactoring for new API")
@pytest.mark.asyncio
async def test_snapshot_catchup_uses_projector():
    """Test FromAggregateSnapshot uses projector to initialize processor."""
    # Create test user aggregate
    user = User(id=ULID())
    user.apply(UserCreated(name="Alice", email="alice@example.com"))

    # Mock repository and checkpoint backend
    mock_repo = Mock()
    mock_repo.load.return_value = user

    mock_checkpoint = Mock()
    mock_checkpoint.load_checkpoint = Mock(return_value=None)
    mock_checkpoint.save_checkpoint = Mock(return_value=None)

    # Mock async methods
    async def async_load_checkpoint(processor_name):
        return None

    async def async_save_checkpoint(checkpoint):
        pass

    mock_checkpoint.load_checkpoint = async_load_checkpoint
    mock_checkpoint.save_checkpoint = async_save_checkpoint

    # Create processor and projector
    processor = UserProcessor()
    projector = UserProjector()
    strategy = FromAggregateSnapshot(mock_repo, projector, mock_checkpoint)

    # Execute catchup
    result = await strategy.catchup(processor)

    assert result is not None
    assert isinstance(result, CatchupResult)
    # Verify projector populated processor state
    assert str(user.id) in processor.users
    assert processor.users[str(user.id)]["name"] == "Alice"
    assert processor.users[str(user.id)]["email"] == "alice@example.com"
