"""Tests for Event[T] wrapper annotation in event handlers."""

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel

from interlock.application.events.processing import EventProcessor
from interlock.domain import Event
from interlock.routing import handles_event
from interlock.testing import ProcessorScenario


# Test event types
class MoneyDeposited(BaseModel):
    """Event payload for money deposit."""

    amount: Decimal


class AccountOpened(BaseModel):
    """Event payload for account opening."""

    owner: str


# Test processors with different annotation styles


class PayloadOnlyProcessor(EventProcessor):
    """Processor that uses payload-only annotation (traditional style)."""

    def __init__(self):
        self.received_events: list[BaseModel] = []
        self.received_types: list[type] = []

    @handles_event
    async def on_deposit(self, event: MoneyDeposited) -> None:
        self.received_events.append(event)
        self.received_types.append(type(event))


class WrapperProcessor(EventProcessor):
    """Processor that uses Event[T] wrapper annotation."""

    def __init__(self):
        self.received_events: list[Event[BaseModel]] = []
        self.received_aggregate_ids: list[UUID] = []
        self.received_sequence_numbers: list[int] = []

    @handles_event
    async def on_deposit(self, event: Event[MoneyDeposited]) -> None:
        self.received_events.append(event)
        self.received_aggregate_ids.append(event.aggregate_id)
        self.received_sequence_numbers.append(event.sequence_number)


class MixedProcessor(EventProcessor):
    """Processor with both annotation styles."""

    def __init__(self):
        self.payload_events: list[BaseModel] = []
        self.wrapper_events: list[Event[BaseModel]] = []

    @handles_event
    async def on_deposit(self, event: MoneyDeposited) -> None:
        """Handler that receives just the payload."""
        self.payload_events.append(event)

    @handles_event
    async def on_account_opened(self, event: Event[AccountOpened]) -> None:
        """Handler that receives the full wrapper."""
        self.wrapper_events.append(event)


# Tests


@pytest.mark.asyncio
async def test_payload_annotation_receives_payload():
    """Test that payload-only annotation receives just the payload."""
    processor = PayloadOnlyProcessor()
    event_data = MoneyDeposited(amount=Decimal("100.00"))

    # Simulate what the executor does - pass an Event wrapper
    aggregate_id = uuid4()
    event = Event(
        aggregate_id=aggregate_id,
        data=event_data,
        sequence_number=1,
    )

    await processor.handle(event)

    assert len(processor.received_events) == 1
    assert processor.received_events[0] == event_data
    assert processor.received_types[0] is MoneyDeposited


@pytest.mark.asyncio
async def test_wrapper_annotation_receives_full_event():
    """Test that Event[T] annotation receives the full wrapper."""
    processor = WrapperProcessor()
    event_data = MoneyDeposited(amount=Decimal("100.00"))

    aggregate_id = uuid4()
    event = Event(
        aggregate_id=aggregate_id,
        data=event_data,
        sequence_number=42,
    )

    await processor.handle(event)

    assert len(processor.received_events) == 1
    assert processor.received_events[0] is event
    assert processor.received_aggregate_ids[0] == aggregate_id
    assert processor.received_sequence_numbers[0] == 42


@pytest.mark.asyncio
async def test_mixed_processor_handles_both_styles():
    """Test that a processor can have both annotation styles."""
    processor = MixedProcessor()

    aggregate_id = uuid4()

    # Send a MoneyDeposited event (payload handler)
    deposit_data = MoneyDeposited(amount=Decimal("50.00"))
    deposit_event = Event(
        aggregate_id=aggregate_id,
        data=deposit_data,
        sequence_number=1,
    )
    await processor.handle(deposit_event)

    # Send an AccountOpened event (wrapper handler)
    opened_data = AccountOpened(owner="Alice")
    opened_event = Event(
        aggregate_id=aggregate_id,
        data=opened_data,
        sequence_number=2,
    )
    await processor.handle(opened_event)

    # Verify payload handler received payload
    assert len(processor.payload_events) == 1
    assert processor.payload_events[0] == deposit_data

    # Verify wrapper handler received full event
    assert len(processor.wrapper_events) == 1
    assert processor.wrapper_events[0] is opened_event


@pytest.mark.asyncio
async def test_backward_compat_passing_payload_directly():
    """Test backward compatibility when passing payload directly."""
    processor = PayloadOnlyProcessor()
    event_data = MoneyDeposited(amount=Decimal("100.00"))

    # Pass just the payload (for testing scenarios)
    await processor.handle(event_data)

    assert len(processor.received_events) == 1
    assert processor.received_events[0] == event_data


@pytest.mark.asyncio
async def test_processor_scenario_with_wrapper_annotation():
    """Test that ProcessorScenario works with wrapper annotations."""
    processor = WrapperProcessor()
    scenario = ProcessorScenario(processor)

    scenario.given(
        MoneyDeposited(amount=Decimal("100.00")),
        MoneyDeposited(amount=Decimal("50.00")),
    ).should_have_state(lambda p: len(p.received_events) == 2)

    await scenario.execute_scenario()

    # Verify we got aggregate_id and sequence_number
    assert len(processor.received_aggregate_ids) == 2
    assert len(processor.received_sequence_numbers) == 2


@pytest.mark.asyncio
async def test_wrapper_annotation_access_to_metadata():
    """Test that wrapper annotation provides access to all event metadata."""
    processor = WrapperProcessor()

    correlation_id = uuid4()
    causation_id = uuid4()
    aggregate_id = uuid4()

    event = Event(
        aggregate_id=aggregate_id,
        data=MoneyDeposited(amount=Decimal("100.00")),
        sequence_number=5,
        correlation_id=correlation_id,
        causation_id=causation_id,
    )

    await processor.handle(event)

    received = processor.received_events[0]
    assert received.aggregate_id == aggregate_id
    assert received.sequence_number == 5
    assert received.correlation_id == correlation_id
    assert received.causation_id == causation_id
    assert received.data.amount == Decimal("100.00")
