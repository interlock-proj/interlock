"""Tests for EventProcessorExecutor."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from interlock.application.events import InMemoryEventTransport
from interlock.application.events.processing.conditions import (
    AfterNAge,
    AfterNEvents,
    Never,
)
from interlock.application.events.processing.executor import (
    EventProcessorExecutor,
)
from interlock.application.events.processing.processor import EventProcessor
from interlock.application.events.processing.strategies import (
    CatchupResult,
    CatchupStrategy,
    NoCatchup,
)
from interlock.context import clear_context, get_context
from interlock.domain import Event
from interlock.routing import handles_event
from tests.fixtures.test_app import AccountStatisticsProcessor
from tests.fixtures.test_app.aggregates.bank_account import (
    AccountOpened,
    MoneyDeposited,
)

# Fixtures


@pytest.fixture
def transport():
    """Create an InMemoryEventTransport."""
    return InMemoryEventTransport()


@pytest.fixture
def processor():
    """Create an AccountStatisticsProcessor."""
    return AccountStatisticsProcessor()


@pytest.fixture
def executor(processor):
    """Create a default executor."""
    return EventProcessorExecutor(processor, Never(), NoCatchup(), batch_size=3)


@pytest.fixture
def now():
    """Current timestamp for consistent testing."""
    return datetime.now(timezone.utc)


def event(data, timestamp=None, correlation_id=None):
    """Create a test event with sensible defaults."""
    return Event(
        id=uuid4(),
        aggregate_id=uuid4(),
        data=data,
        sequence_number=1,
        timestamp=timestamp or datetime.now(timezone.utc),
        correlation_id=correlation_id,
    )


async def publish_and_subscribe(transport, events):
    """Publish events and return subscription."""
    await transport.publish_events(events)
    return await transport.subscribe("test")


class MockCatchupStrategy(CatchupStrategy):
    """Mock catchup strategy that tracks calls."""

    def __init__(self, result=None):
        self.catchup_calls = 0
        self.result = result

    async def catchup(self, processor):
        self.catchup_calls += 1
        return self.result


# Constructor Tests


def test_executor_init_defaults(processor):
    """Test executor initializes with default batch_size."""
    executor = EventProcessorExecutor(processor, Never(), NoCatchup())
    assert executor.processor is processor
    assert executor.batch_size == 1000


def test_executor_init_custom_batch_size(processor):
    """Test executor initializes with custom batch_size."""
    executor = EventProcessorExecutor(processor, Never(), NoCatchup(), batch_size=50)
    assert executor.batch_size == 50


def test_executor_init_validates_batch_size(processor):
    """Test executor raises ValueError for invalid batch_size."""
    with pytest.raises(ValueError, match="batch_size must be positive"):
        EventProcessorExecutor(processor, Never(), NoCatchup(), batch_size=0)

    with pytest.raises(ValueError, match="batch_size must be positive"):
        EventProcessorExecutor(processor, Never(), NoCatchup(), batch_size=-10)


# Event Batch Processing Tests


@pytest.mark.asyncio
async def test_process_batch_routes_events(executor, processor, transport):
    """Test executor processes events and routes to handlers."""
    sub = await publish_and_subscribe(
        transport,
        [
            event(AccountOpened(owner="Alice")),
            event(MoneyDeposited(amount=Decimal("100.00"))),
            event(MoneyDeposited(amount=Decimal("50.00"))),
        ],
    )

    await executor.process_event_batch(sub)

    assert processor.total_accounts_opened == 1
    assert processor.total_deposits == Decimal("150.00")
    assert processor.deposit_count == 2


@pytest.mark.asyncio
async def test_process_batch_calculates_lag(transport, processor, now):
    """Test executor calculates average event age correctly."""
    executor = EventProcessorExecutor(processor, Never(), NoCatchup(), batch_size=2)
    old_time = now - timedelta(minutes=10)

    sub = await publish_and_subscribe(
        transport,
        [
            event(AccountOpened(owner="Bob"), timestamp=old_time),
            event(AccountOpened(owner="Charlie"), timestamp=old_time),
        ],
    )

    avg_age = await executor.process_event_batch(sub)

    assert timedelta(minutes=9, seconds=50) <= avg_age <= timedelta(minutes=10, seconds=10)


@pytest.mark.asyncio
async def test_process_batch_respects_skip_window(executor, processor, transport, now):
    """Test executor skips events in catchup skip window."""
    old = now - timedelta(minutes=10)
    recent = now - timedelta(minutes=1)
    skip_before = now - timedelta(minutes=5)

    sub = await publish_and_subscribe(
        transport,
        [
            event(AccountOpened(owner="Alice"), timestamp=old),
            event(MoneyDeposited(amount=Decimal("100.00")), timestamp=old),
            event(MoneyDeposited(amount=Decimal("50.00")), timestamp=recent),
        ],
    )

    await executor.process_event_batch(sub, CatchupResult(skip_before))

    assert processor.total_accounts_opened == 0  # Skipped
    assert processor.total_deposits == Decimal("50.00")  # Only recent


@pytest.mark.asyncio
async def test_process_batch_returns_zero_when_all_skipped(transport, processor, now):
    """Test executor returns zero lag when all events skipped."""
    executor = EventProcessorExecutor(processor, Never(), NoCatchup(), batch_size=2)
    old = now - timedelta(hours=1)

    sub = await publish_and_subscribe(
        transport,
        [
            event(AccountOpened(owner="Alice"), timestamp=old),
            event(AccountOpened(owner="Bob"), timestamp=old),
        ],
    )

    avg_age = await executor.process_event_batch(sub, CatchupResult(now))

    assert avg_age == timedelta()
    assert processor.total_accounts_opened == 0


@pytest.mark.asyncio
async def test_process_batch_restores_context(transport):
    """Test executor restores context from event metadata."""
    context_captured = []

    class ContextCaptor(EventProcessor):
        @handles_event
        async def on_account_opened(self, event: AccountOpened):
            ctx = get_context()
            context_captured.append((ctx.correlation_id, ctx.causation_id))

    executor = EventProcessorExecutor(ContextCaptor(), Never(), NoCatchup(), batch_size=2)
    correlation_id = uuid4()
    event1_id, event2_id = uuid4(), uuid4()

    await transport.publish_events(
        [
            Event(
                id=event1_id,
                aggregate_id=uuid4(),
                data=AccountOpened(owner="Alice"),
                sequence_number=1,
                timestamp=datetime.now(timezone.utc),
                correlation_id=correlation_id,
            ),
            Event(
                id=event2_id,
                aggregate_id=uuid4(),
                data=AccountOpened(owner="Bob"),
                sequence_number=2,
                timestamp=datetime.now(timezone.utc),
                correlation_id=correlation_id,
            ),
        ]
    )
    sub = await transport.subscribe("test")

    await executor.process_event_batch(sub)

    assert context_captured == [
        (correlation_id, event1_id),
        (correlation_id, event2_id),
    ]


@pytest.mark.asyncio
async def test_process_batch_clears_context(executor, transport):
    """Test executor clears context after processing."""
    clear_context()
    correlation_id = uuid4()

    sub = await publish_and_subscribe(
        transport,
        [
            event(AccountOpened(owner="Alice"), correlation_id=correlation_id),
        ],
    )

    executor.batch_size = 1
    await executor.process_event_batch(sub)

    assert get_context().correlation_id is None


@pytest.mark.asyncio
async def test_process_batch_handles_missing_correlation_id(executor, processor, transport):
    """Test executor handles events without correlation_id."""
    sub = await publish_and_subscribe(
        transport,
        [
            event(AccountOpened(owner="Alice"), correlation_id=None),
        ],
    )

    executor.batch_size = 1
    await executor.process_event_batch(sub)

    assert processor.total_accounts_opened == 1


# Batch and Catchup Logic Tests


@pytest.mark.asyncio
async def test_batch_and_catchup_no_trigger(transport):
    """Test batch processing when catchup condition not met."""
    processor = AccountStatisticsProcessor()
    strategy = MockCatchupStrategy()
    executor = EventProcessorExecutor(processor, Never(), strategy, batch_size=2)

    sub = await publish_and_subscribe(
        transport,
        [
            event(AccountOpened(owner="Alice")),
            event(AccountOpened(owner="Bob")),
        ],
    )

    result = await executor.process_batch_and_check_catchup(sub)

    assert result is None
    assert strategy.catchup_calls == 0
    assert processor.total_accounts_opened == 2


@pytest.mark.asyncio
async def test_batch_and_catchup_triggers(transport):
    """Test batch processing triggers catchup when condition met."""
    processor = AccountStatisticsProcessor()
    strategy = MockCatchupStrategy(CatchupResult())
    executor = EventProcessorExecutor(processor, AfterNEvents(1), strategy, batch_size=1)

    sub = await publish_and_subscribe(
        transport, [event(AccountOpened(owner=f"User{i}")) for i in range(3)]
    )

    result = await executor.process_batch_and_check_catchup(sub)

    assert result is not None
    assert strategy.catchup_calls == 1


@pytest.mark.asyncio
async def test_batch_and_catchup_with_skip_window(transport, now):
    """Test batch processing with skip window from previous catchup."""
    processor = AccountStatisticsProcessor()
    executor = EventProcessorExecutor(processor, Never(), MockCatchupStrategy(), batch_size=2)
    old = now - timedelta(minutes=10)

    sub = await publish_and_subscribe(
        transport,
        [
            event(AccountOpened(owner="Old"), timestamp=old),
            event(AccountOpened(owner="New"), timestamp=now),
        ],
    )

    skip_before = now - timedelta(minutes=5)
    result = await executor.process_batch_and_check_catchup(sub, CatchupResult(skip_before))

    assert result is None
    assert processor.total_accounts_opened == 1


@pytest.mark.asyncio
async def test_batch_and_catchup_by_event_age(transport, now):
    """Test catchup triggered by event age condition."""
    processor = AccountStatisticsProcessor()
    strategy = MockCatchupStrategy(CatchupResult())
    executor = EventProcessorExecutor(
        processor, AfterNAge(timedelta(minutes=5)), strategy, batch_size=2
    )
    old = now - timedelta(minutes=10)

    sub = await publish_and_subscribe(
        transport,
        [
            event(AccountOpened(owner="Alice"), timestamp=old),
            event(AccountOpened(owner="Bob"), timestamp=old),
        ],
    )

    result = await executor.process_batch_and_check_catchup(sub)

    assert result is not None
    assert strategy.catchup_calls == 1


# Run Method Tests


@pytest.mark.asyncio
async def test_run_executes_initial_catchup(processor, transport):
    """Test executor runs initial catchup on startup."""
    strategy = MockCatchupStrategy()
    executor = EventProcessorExecutor(processor, Never(), strategy, batch_size=1)
    sub = await transport.subscribe("test")

    with pytest.raises(IndexError):  # No events to process
        await executor.run(sub)

    assert strategy.catchup_calls == 1


@pytest.mark.asyncio
async def test_run_processes_multiple_batches(transport):
    """Test run method processes multiple batches."""
    processor = AccountStatisticsProcessor()
    executor = EventProcessorExecutor(processor, Never(), NoCatchup(), batch_size=2)

    sub = await publish_and_subscribe(
        transport, [event(AccountOpened(owner=f"User{i}")) for i in range(4)]
    )

    await executor.process_batch_and_check_catchup(sub)
    assert processor.total_accounts_opened == 2

    await executor.process_batch_and_check_catchup(sub)
    assert processor.total_accounts_opened == 4


@pytest.mark.asyncio
async def test_run_triggers_catchup_during_processing(transport):
    """Test run method triggers catchup when condition met."""
    processor = AccountStatisticsProcessor()
    strategy = MockCatchupStrategy(CatchupResult())
    executor = EventProcessorExecutor(processor, AfterNEvents(1), strategy, batch_size=1)

    sub = await publish_and_subscribe(
        transport, [event(AccountOpened(owner=f"User{i}")) for i in range(3)]
    )

    # First batch triggers catchup (2 events remain)
    result = await executor.process_batch_and_check_catchup(sub)
    assert result is not None
    assert strategy.catchup_calls == 1

    # Second batch doesn't trigger (only 1 event left)
    result = await executor.process_batch_and_check_catchup(sub, result)
    assert result is None


# Error Handling Tests


@pytest.mark.asyncio
async def test_executor_propagates_exceptions(transport):
    """Test executor propagates exceptions from event handlers."""

    class FailingProcessor(EventProcessor):
        @handles_event
        async def on_account_opened(self, event: AccountOpened):
            raise ValueError("Handler error")

    executor = EventProcessorExecutor(FailingProcessor(), Never(), NoCatchup(), batch_size=1)
    sub = await publish_and_subscribe(
        transport,
        [
            event(AccountOpened(owner="Alice")),
        ],
    )

    with pytest.raises(ValueError, match="Handler error"):
        await executor.process_event_batch(sub)


@pytest.mark.asyncio
async def test_executor_clears_context_on_exception(transport):
    """Test executor clears context even when handler raises."""
    clear_context()

    class FailingProcessor(EventProcessor):
        @handles_event
        async def on_account_opened(self, event: AccountOpened):
            raise ValueError("Handler error")

    executor = EventProcessorExecutor(FailingProcessor(), Never(), NoCatchup(), batch_size=1)
    correlation_id = uuid4()
    sub = await publish_and_subscribe(
        transport,
        [
            event(AccountOpened(owner="Alice"), correlation_id=correlation_id),
        ],
    )

    with pytest.raises(ValueError):
        await executor.process_event_batch(sub)

    assert get_context().correlation_id is None


# Lag Calculation Test


@pytest.mark.asyncio
async def test_executor_calculates_lag_accurately(transport, processor, now):
    """Test executor averages event ages correctly."""
    executor = EventProcessorExecutor(processor, Never(), NoCatchup(), batch_size=3)

    sub = await publish_and_subscribe(
        transport,
        [
            event(
                AccountOpened(owner=f"User{i}"),
                timestamp=now - timedelta(minutes=i * 5),  # 0, 5, 10 min old
            )
            for i in range(3)
        ],
    )

    avg_age = await executor.process_event_batch(sub)

    # Average: (0 + 5 + 10) / 3 = 5 minutes
    assert timedelta(minutes=4, seconds=50) <= avg_age <= timedelta(minutes=5, seconds=10)
