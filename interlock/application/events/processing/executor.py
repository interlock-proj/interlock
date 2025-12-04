from datetime import timedelta
from typing import Generic, TypeVar

from ....context import ExecutionContext, clear_context, set_context
from ....domain import utc_now
from ..transport import EventSubscription
from .conditions import CatchupCondition, Lag
from .processor import EventProcessor
from .strategies import CatchupResult, CatchupStrategy

P = TypeVar("P", bound=EventProcessor)


class EventProcessorExecutor(Generic[P]):
    """Runtime execution engine for event processors.

    EventProcessorExecutor manages the continuous processing of events by:
    1. Subscribing to an event stream via EventSubscription
    2. Batching events for efficient processing
    3. Monitoring processor lag (backlog and event age)
    4. Triggering catchup strategies when conditions are met

    This is the "event loop" that drives event processors. It runs
    continuously, pulling events from the subscription and routing them
    to the processor's handlers.

    **Batching:**
    Events are processed in batches to improve throughput. After each
    batch, lag metrics are calculated to determine if catchup is needed.

    **Lag Monitoring:**
    After each batch, the executor measures:
    - Unprocessed events (subscription depth)
    - Average event age (time from event.timestamp to processing)

    **Catchup Triggering:**
    If the CatchupCondition evaluates to True, the CatchupStrategy is
    executed. Blocking strategies pause event processing; non-blocking
    strategies run concurrently.

    Attributes:
        subscription: Event stream to consume from
        processor: Event processor with handler methods
        condition: Condition for triggering catchup
        strategy: Strategy for catching up when triggered
        batch_size: Number of events to process before checking lag

    Example:
        >>> subscription = await event_bus.subscribe("orders")
        >>> processor = OrderReadModelProcessor()
        >>> condition = AnyOf(
        ...     AfterNEvents(1000),
        ...     AfterNAge(timedelta(minutes=5))
        ... )
        >>> strategy = FromReplayingEvents()
        >>>
        >>> executor = EventProcessorExecutor(
        ...     subscription=subscription,
        ...     processor=processor,
        ...     condition=condition,
        ...     strategy=strategy,
        ...     batch_size=100
        ... )
        >>> await executor.run()  # Run forever, processing events

    Note:
        The run() method runs indefinitely until interrupted. Use asyncio
        task cancellation or exception handling to stop it gracefully.
    """

    __slots__ = (
        "processor",
        "condition",
        "strategy",
        "batch_size",
    )

    def __init__(
        self,
        processor: P,
        condition: CatchupCondition,
        strategy: CatchupStrategy[P],
        batch_size: int = 1000,
    ) -> None:
        """Initialize the executor with its dependencies.

        Args:
            processor: Processor with event handlers
            condition: When to trigger catchup
            strategy: How to catch up when triggered
            batch_size: Events to process per batch (must be > 0)

        Raises:
            ValueError: If batch_size <= 0
        """
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        self.processor = processor
        self.condition = condition
        self.strategy = strategy
        self.batch_size = batch_size

    async def process_event_batch(
        self,
        subscription: EventSubscription,
        catchup_result: CatchupResult | None = None,
    ) -> timedelta:
        """Process a batch of events and calculate average event age.

        Pulls batch_size events from the subscription, routes each to the
        processor's handlers, and calculates the mean age of processed events.

        If a catchup_result is provided, events in the skip window are skipped
        to avoid double-processing events that were already incorporated during
        catchup.

        For each event, the execution context is restored from the event
        metadata before processing, allowing processors to:
        - Access correlation/causation IDs for logging
        - Dispatch new commands with proper context inheritance
        - Track the causal chain in sagas and process managers

        The context is cleared after each event to prevent leakage.

        Args:
            subscription: The subscription to pull events from.
            catchup_result: The skip window from catchup operation (Optional)

        Returns:
            Average time between event.timestamp and processing time

        Raises:
            StopAsyncIteration: If subscription ends
            Any exceptions raised by event handlers
        """
        total_lag_time = timedelta()
        events_processed = 0

        for _ in range(self.batch_size):
            event = await subscription.next()
            total_lag_time += utc_now() - event.timestamp

            # Skip events in the skip window (already processed during catchup)
            if catchup_result and catchup_result.should_skip(event):
                continue

            events_processed += 1

            # Restore context from event metadata before processing
            # This allows event processors to dispatch commands with proper
            # causation
            context_set = False
            if event.correlation_id is not None:
                ctx = ExecutionContext(
                    correlation_id=event.correlation_id,
                    causation_id=event.id,
                    command_id=None,
                )
                set_context(ctx)
                context_set = True

            try:
                await self.processor.handle(event.data)
            finally:
                # Clear context only if we set it to prevent leakage
                if context_set:
                    clear_context()

        # If we didn't process any events, avoid division by zero
        if events_processed == 0:
            return timedelta()

        return total_lag_time / events_processed

    async def process_batch_and_check_catchup(
        self,
        subscription: EventSubscription,
        catchup_result: CatchupResult | None = None,
    ) -> CatchupResult | None:
        """Process a batch, measure lag, and trigger catchup if needed.

        This method encapsulates one iteration of the main event loop:
        1. Process a batch of events
        2. Measure lag (average age + unprocessed count)
        3. Clear skip window after first batch post-catchup
        4. Trigger catchup if condition is met

        Args:
            subscription: Event subscription to pull from
            catchup_result: Skip window from previous catchup (if any)

        Returns:
            New catchup result if catchup was triggered, None otherwise

        Raises:
            StopAsyncIteration: If subscription ends
            Any exceptions from event handlers or catchup strategy
        """
        # Process batch and measure lag
        average_event_age = await self.process_event_batch(
            subscription=subscription,
            catchup_result=catchup_result,
        )
        lag = Lag(
            average_event_age=average_event_age,
            unprocessed_events=await subscription.depth(),
        )

        # Clear skip window after first batch (one-time use)
        # The skip window prevents double-processing events that were
        # already incorporated during the catchup operation
        new_catchup_result = None

        # Trigger catchup if condition met
        if self.condition.should_catchup(lag):
            new_catchup_result = await self.strategy.catchup(self.processor)

        return new_catchup_result

    async def run(self, subscription: EventSubscription) -> None:
        """Run the event processing loop continuously.

        This method runs indefinitely, processing events in batches and
        triggering catchup when the condition is met. It will only stop
        if:
        - The subscription ends (StopAsyncIteration)
        - An unhandled exception is raised
        - The async task is cancelled

        The method performs initial catchup at startup, then enters the main
        processing loop. If catchup returns a skip window, events in that
        window are skipped until we encounter an event beyond the window.

        Raises:
            StopAsyncIteration: When subscription ends
            Any exceptions from event handlers or catchup strategy
        """
        # Execute initial catchup at startup
        catchup_result = await self.strategy.catchup(self.processor)

        while True:
            catchup_result = await self.process_batch_and_check_catchup(
                subscription=subscription,
                catchup_result=catchup_result,
            )
