"""Integration tests for correlation and causation ID propagation."""

from decimal import Decimal

import pytest
from ulid import ULID

from interlock.application import ApplicationBuilder
from interlock.application.middleware import ContextPropagationMiddleware
from interlock.application.events.processing import EventProcessor
from interlock.context import get_context
from interlock.routing import handles_event
from tests.fixtures.test_app.aggregates.bank_account import (
    AccountOpened,
    BankAccount,
    DepositMoney,
    MoneyDeposited,
    OpenAccount,
)


@pytest.mark.asyncio
async def test_correlation_id_propagates_to_events():
    """Correlation ID should propagate from command to events."""
    captured_events = []

    class EventCapturingProcessor(EventProcessor):
        @handles_event
        async def on_account_opened(self, event: AccountOpened) -> None:
            # Capture the full event from the event store
            pass

    app = (
        ApplicationBuilder()
        .register_middleware(ContextPropagationMiddleware)
        .register_middleware(ContextPropagationMiddleware)
        .register_aggregate(BankAccount)
        .register_event_processor(EventCapturingProcessor)
        .build()
    )

    # Capture events before they're delivered
    original_deliver = app.event_bus.delivery.deliver

    async def capture_deliver(events):
        captured_events.extend(events)
        return await original_deliver(events)

    app.event_bus.delivery.deliver = capture_deliver

    # Dispatch command with correlation ID
    account_id = ULID()
    correlation_id = ULID()
    command = OpenAccount(
        aggregate_id=account_id,
        owner="Alice",
        correlation_id=correlation_id,
        causation_id=correlation_id,
    )

    await app.dispatch(command)

    # Verify event has correlation ID
    assert len(captured_events) == 1
    event = captured_events[0]
    assert event.correlation_id == correlation_id
    assert event.causation_id == command.command_id


@pytest.mark.asyncio
async def test_correlation_id_auto_generated_when_missing():
    """Correlation ID should be auto-generated if not provided."""
    captured_events = []

    class EventCapturingProcessor(EventProcessor):
        @handles_event
        async def on_account_opened(self, event: AccountOpened) -> None:
            pass

    app = (
        ApplicationBuilder()
        .register_middleware(ContextPropagationMiddleware)
        .register_middleware(ContextPropagationMiddleware)
        .register_aggregate(BankAccount)
        .register_event_processor(EventCapturingProcessor)
        .build()
    )

    # Capture events
    original_deliver = app.event_bus.delivery.deliver

    async def capture_deliver(events):
        captured_events.extend(events)
        return await original_deliver(events)

    app.event_bus.delivery.deliver = capture_deliver

    # Dispatch command without correlation ID
    account_id = ULID()
    command = OpenAccount(aggregate_id=account_id, owner="Bob")

    assert command.correlation_id is None

    await app.dispatch(command)

    # Verify event has auto-generated correlation ID
    assert len(captured_events) == 1
    event = captured_events[0]
    assert event.correlation_id is not None
    assert isinstance(event.correlation_id, ULID)


@pytest.mark.asyncio
async def test_context_available_in_event_processor():
    """Event processors should have access to correlation context."""
    captured_contexts = []

    class ContextCapturingProcessor(EventProcessor):
        @handles_event
        async def on_account_opened(self, event: AccountOpened) -> None:
            captured_contexts.append(get_context())

    app = (
        ApplicationBuilder()
        .register_middleware(ContextPropagationMiddleware)
        .register_middleware(ContextPropagationMiddleware)
        .register_aggregate(BankAccount)
        .register_event_processor(ContextCapturingProcessor)
        .build()
    )

    account_id = ULID()
    correlation_id = ULID()
    command = OpenAccount(
        aggregate_id=account_id,
        owner="Charlie",
        correlation_id=correlation_id,
        causation_id=correlation_id,
    )

    await app.dispatch(command)

    # Verify context was available in processor
    assert len(captured_contexts) == 1
    ctx = captured_contexts[0]
    assert ctx.correlation_id == correlation_id


@pytest.mark.asyncio
async def test_context_cleared_after_command():
    """Context should be cleared after command completes."""
    app = (
        ApplicationBuilder()
        .register_middleware(ContextPropagationMiddleware)
        .register_middleware(ContextPropagationMiddleware)
        .register_aggregate(BankAccount)
        .build()
    )

    account_id = ULID()
    command = OpenAccount(aggregate_id=account_id, owner="Dave")

    await app.dispatch(command)

    # Context should be cleared
    ctx = get_context()
    assert ctx.correlation_id is None
    assert ctx.causation_id is None
    assert ctx.command_id is None


@pytest.mark.asyncio
async def test_multiple_commands_same_correlation():
    """Multiple commands can share the same correlation ID."""
    captured_events = []

    class EventCapturingProcessor(EventProcessor):
        @handles_event
        async def on_account_opened(self, event: AccountOpened) -> None:
            pass

        @handles_event
        async def on_money_deposited(self, event: MoneyDeposited) -> None:
            pass

    app = (
        ApplicationBuilder()
        .register_middleware(ContextPropagationMiddleware)
        .register_middleware(ContextPropagationMiddleware)
        .register_aggregate(BankAccount)
        .register_event_processor(EventCapturingProcessor)
        .build()
    )

    # Capture events
    original_deliver = app.event_bus.delivery.deliver

    async def capture_deliver(events):
        captured_events.extend(events)
        return await original_deliver(events)

    app.event_bus.delivery.deliver = capture_deliver

    # Use same correlation ID for multiple commands
    account_id = ULID()
    correlation_id = ULID()

    # Open account
    open_cmd = OpenAccount(
        aggregate_id=account_id,
        owner="Eve",
        correlation_id=correlation_id,
        causation_id=correlation_id,
    )
    await app.dispatch(open_cmd)

    # Deposit money with same correlation
    deposit_cmd = DepositMoney(
        aggregate_id=account_id,
        amount=Decimal("100.00"),
        correlation_id=correlation_id,
        causation_id=ULID(),  # Different causation
    )
    await app.dispatch(deposit_cmd)

    # Both events should have same correlation ID
    assert len(captured_events) == 2
    assert captured_events[0].correlation_id == correlation_id
    assert captured_events[1].correlation_id == correlation_id


@pytest.mark.asyncio
async def test_without_correlation_tracking_middleware():
    """Without correlation tracking, events should have None correlation_id."""
    captured_events = []

    class EventCapturingProcessor(EventProcessor):
        @handles_event
        async def on_account_opened(self, event: AccountOpened) -> None:
            pass

    app = (
        ApplicationBuilder()
        # NOT using ContextPropagationMiddleware
        .register_aggregate(BankAccount)
        .register_event_processor(EventCapturingProcessor)
        .build()
    )

    # Capture events
    original_deliver = app.event_bus.delivery.deliver

    async def capture_deliver(events):
        captured_events.extend(events)
        return await original_deliver(events)

    app.event_bus.delivery.deliver = capture_deliver

    account_id = ULID()
    command = OpenAccount(aggregate_id=account_id, owner="Frank")

    await app.dispatch(command)

    # Event should not have correlation ID
    assert len(captured_events) == 1
    event = captured_events[0]
    assert event.correlation_id is None
    assert event.causation_id is None


@pytest.mark.asyncio
async def test_event_causation_is_command_id():
    """Events should have causation_id equal to the command_id that caused them."""
    captured_events = []

    class EventCapturingProcessor(EventProcessor):
        @handles_event
        async def on_account_opened(self, event: AccountOpened) -> None:
            pass

    app = (
        ApplicationBuilder()
        .register_middleware(ContextPropagationMiddleware)
        .register_middleware(ContextPropagationMiddleware)
        .register_aggregate(BankAccount)
        .register_event_processor(EventCapturingProcessor)
        .build()
    )

    # Capture events
    original_deliver = app.event_bus.delivery.deliver

    async def capture_deliver(events):
        captured_events.extend(events)
        return await original_deliver(events)

    app.event_bus.delivery.deliver = capture_deliver

    account_id = ULID()
    correlation_id = ULID()
    command = OpenAccount(
        aggregate_id=account_id,
        owner="Grace",
        correlation_id=correlation_id,
        causation_id=correlation_id,
    )

    await app.dispatch(command)

    # Event's causation should be the command's ID
    assert len(captured_events) == 1
    event = captured_events[0]
    assert event.causation_id == command.command_id
    assert event.correlation_id == correlation_id


@pytest.mark.asyncio
async def test_full_causation_chain():
    """Test full causation chain: Command → Event → (theoretical) Saga Command."""
    captured_event = None
    captured_context_in_processor = None

    class ContextCapturingProcessor(EventProcessor):
        @handles_event
        async def on_account_opened(self, event: AccountOpened) -> None:
            nonlocal captured_event, captured_context_in_processor
            captured_context_in_processor = get_context()

    app = (
        ApplicationBuilder()
        .register_middleware(ContextPropagationMiddleware)
        .register_middleware(ContextPropagationMiddleware)
        .register_aggregate(BankAccount)
        .register_event_processor(ContextCapturingProcessor)
        .build()
    )

    # Capture events
    original_deliver = app.event_bus.delivery.deliver

    async def capture_deliver(events):
        nonlocal captured_event
        if events:
            captured_event = events[0]
        return await original_deliver(events)

    app.event_bus.delivery.deliver = capture_deliver

    # Dispatch command
    account_id = ULID()
    correlation_id = ULID()
    command = OpenAccount(
        aggregate_id=account_id,
        owner="Henry",
        correlation_id=correlation_id,
        causation_id=correlation_id,
    )

    await app.dispatch(command)

    # Verify chain: Command → Event
    assert captured_event is not None
    assert captured_event.correlation_id == correlation_id
    assert captured_event.causation_id == command.command_id

    # Verify context in processor (Event → Saga would use this)
    assert captured_context_in_processor is not None
    assert captured_context_in_processor.correlation_id == correlation_id
    # In processor, causation would be the event ID for any saga commands
