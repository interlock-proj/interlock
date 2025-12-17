"""Tests for gradual migration with EagerUpcastingStrategy."""

import pytest
from pydantic import BaseModel
from ulid import ULID

from interlock.application.events.bus import EventBus
from interlock.application.events.delivery import SynchronousDelivery
from interlock.application.events.upcasting import (
    EagerUpcastingStrategy,
    EventUpcaster,
    LazyUpcastingStrategy,
    UpcasterMap,
    UpcastingPipeline,
)
from interlock.domain import Event

# Test event types


class MoneyDepositedV1(BaseModel):
    """Original version without source field."""

    amount: int


class MoneyDepositedV2(BaseModel):
    """New version with source field."""

    amount: int
    source: str


class MoneyDepositedV1ToV2(EventUpcaster[MoneyDepositedV1, MoneyDepositedV2]):
    """Upcaster from V1 to V2."""

    async def upcast_payload(self, data: MoneyDepositedV1) -> MoneyDepositedV2:
        return MoneyDepositedV2(amount=data.amount, source="migrated")


# Fixtures


@pytest.fixture
def upcaster():
    """Create the V1 to V2 upcaster."""
    return MoneyDepositedV1ToV2()


@pytest.fixture
def upcaster_map(upcaster):
    """Create an upcaster map with the V1->V2 upcaster."""
    return UpcasterMap.from_upcasters([upcaster])


@pytest.fixture
def eager_bus(event_store, event_transport, upcaster_map):
    """Create an EventBus with EagerUpcastingStrategy."""
    pipeline = UpcastingPipeline(EagerUpcastingStrategy(), upcaster_map)
    delivery = SynchronousDelivery(event_transport, [])
    return EventBus(event_store, delivery, pipeline)


@pytest.fixture
def lazy_bus(event_store, event_transport, upcaster_map):
    """Create an EventBus with LazyUpcastingStrategy."""
    pipeline = UpcastingPipeline(LazyUpcastingStrategy(), upcaster_map)
    delivery = SynchronousDelivery(event_transport, [])
    return EventBus(event_store, delivery, pipeline)


def create_v1_event(aggregate_id: ULID, seq: int = 1) -> Event[MoneyDepositedV1]:
    """Helper to create a V1 event."""
    return Event(
        aggregate_id=aggregate_id,
        data=MoneyDepositedV1(amount=100),
        sequence_number=seq,
    )


# Tests


@pytest.mark.asyncio
async def test_eager_strategy_rewrites_upcasted_events(event_store, eager_bus, aggregate_id):
    """Test that EagerUpcastingStrategy rewrites events after upcasting."""
    # Store a V1 event directly
    v1_event = create_v1_event(aggregate_id)
    await event_store.save_events([v1_event], expected_version=0)

    # Verify V1 is in the store
    raw_events = await event_store.load_events(aggregate_id, min_version=0)
    assert isinstance(raw_events[0].data, MoneyDepositedV1)

    # Load events through the bus (triggers upcasting + rewrite)
    loaded_events = await eager_bus.load_events(aggregate_id, min_version=0)

    # Verify we got V2 back
    assert isinstance(loaded_events[0].data, MoneyDepositedV2)
    assert loaded_events[0].data.source == "migrated"

    # Verify the store was updated with V2
    raw_events_after = await event_store.load_events(aggregate_id, min_version=0)
    assert isinstance(raw_events_after[0].data, MoneyDepositedV2)
    assert raw_events_after[0].data.source == "migrated"


@pytest.mark.asyncio
async def test_lazy_strategy_does_not_rewrite_events(event_store, lazy_bus, aggregate_id):
    """Test that LazyUpcastingStrategy does NOT rewrite events."""
    # Store a V1 event directly
    v1_event = create_v1_event(aggregate_id)
    await event_store.save_events([v1_event], expected_version=0)

    # Load events through the bus
    loaded_events = await lazy_bus.load_events(aggregate_id, min_version=0)

    # Verify we got V2 back (upcasted in memory)
    assert isinstance(loaded_events[0].data, MoneyDepositedV2)

    # Verify the store still has V1 (not rewritten)
    raw_events = await event_store.load_events(aggregate_id, min_version=0)
    assert isinstance(raw_events[0].data, MoneyDepositedV1)


@pytest.mark.asyncio
async def test_second_load_returns_v2_from_store(
    event_store, event_transport, eager_bus, aggregate_id
):
    """Test that after rewrite, subsequent loads get V2 directly."""
    # Store a V1 event
    v1_event = create_v1_event(aggregate_id)
    await event_store.save_events([v1_event], expected_version=0)

    # First load - upcasts and rewrites
    first_load = await eager_bus.load_events(aggregate_id, min_version=0)
    assert isinstance(first_load[0].data, MoneyDepositedV2)

    # Create a new bus WITHOUT the upcaster (simulates removing old code)
    empty_pipeline = UpcastingPipeline(EagerUpcastingStrategy(), UpcasterMap())
    bus_no_upcaster = EventBus(
        event_store, SynchronousDelivery(event_transport, []), empty_pipeline
    )

    # Second load - should get V2 directly from store
    second_load = await bus_no_upcaster.load_events(aggregate_id, min_version=0)
    assert isinstance(second_load[0].data, MoneyDepositedV2)
    assert second_load[0].data.source == "migrated"


@pytest.mark.asyncio
async def test_only_changed_events_are_rewritten(event_store, eager_bus, aggregate_id):
    """Test that events that don't need upcasting are not rewritten."""
    # Store one V1 and one V2 event
    v1_event = create_v1_event(aggregate_id, seq=1)
    v2_event = Event(
        aggregate_id=aggregate_id,
        data=MoneyDepositedV2(amount=200, source="direct"),
        sequence_number=2,
    )
    await event_store.save_events([v1_event], expected_version=0)
    await event_store.save_events([v2_event], expected_version=1)

    # Load events
    loaded_events = await eager_bus.load_events(aggregate_id, min_version=0)

    # Both should be V2
    assert isinstance(loaded_events[0].data, MoneyDepositedV2)
    assert isinstance(loaded_events[1].data, MoneyDepositedV2)

    # First should be migrated, second should retain original source
    assert loaded_events[0].data.source == "migrated"
    assert loaded_events[1].data.source == "direct"

    # Verify store
    raw_events = await event_store.load_events(aggregate_id, min_version=0)
    assert raw_events[0].data.source == "migrated"
    assert raw_events[1].data.source == "direct"


@pytest.mark.asyncio
async def test_event_metadata_preserved_after_rewrite(event_store, eager_bus, aggregate_id):
    """Test that event metadata is preserved when rewriting."""
    from datetime import datetime, timezone

    original_timestamp = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    correlation_id = ULID()
    causation_id = ULID()
    event_id = ULID()

    v1_event = Event(
        id=event_id,
        aggregate_id=aggregate_id,
        data=MoneyDepositedV1(amount=100),
        sequence_number=1,
        timestamp=original_timestamp,
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
    await event_store.save_events([v1_event], expected_version=0)

    # Load and trigger rewrite
    await eager_bus.load_events(aggregate_id, min_version=0)

    # Check store has preserved metadata
    raw_events = await event_store.load_events(aggregate_id, min_version=0)
    rewritten = raw_events[0]

    assert rewritten.id == event_id
    assert rewritten.aggregate_id == aggregate_id
    assert rewritten.sequence_number == 1
    assert rewritten.timestamp == original_timestamp
    assert rewritten.correlation_id == correlation_id
    assert rewritten.causation_id == causation_id
    assert isinstance(rewritten.data, MoneyDepositedV2)


@pytest.mark.asyncio
async def test_no_rewrite_when_no_upcasting_needed(event_store, eager_bus, aggregate_id):
    """Test that no rewrite occurs if events are already current version."""
    # Store a V2 event directly
    v2_event = Event(
        aggregate_id=aggregate_id,
        data=MoneyDepositedV2(amount=100, source="original"),
        sequence_number=1,
    )
    await event_store.save_events([v2_event], expected_version=0)

    # Load events (upcaster only handles V1, not V2)
    loaded_events = await eager_bus.load_events(aggregate_id, min_version=0)

    # Should still be V2 with original source
    assert isinstance(loaded_events[0].data, MoneyDepositedV2)
    assert loaded_events[0].data.source == "original"

    # Store should be unchanged
    raw_events = await event_store.load_events(aggregate_id, min_version=0)
    assert raw_events[0].data.source == "original"
