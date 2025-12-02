from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Generic, TypeVar

if TYPE_CHECKING:
    from ...aggregates import AggregateRepository
    from ...events.event import Event
    from .checkpoint import CheckpointBackend
    from .processor import EventProcessor
    from .projectors import AggregateProjector

P = TypeVar("P", bound="EventProcessor")


@dataclass
class CatchupResult:
    """Result from catchup operation with skip window for avoiding double-processing.

    When a catchup strategy processes historical data (e.g., loading snapshots),
    those events have already been incorporated into the processor's state. To
    avoid processing them again when the executor resumes from the subscription,
    we need to skip events up to a certain timestamp.

    Attributes:
        skip_before: Events with timestamp <= this value should be skipped.
            None means no skipping is needed.

    Example:
        >>> # Catchup loaded aggregates up to 2025-01-01 10:00:00
        >>> result = CatchupResult(skip_before=datetime(2025, 1, 1, 10, 0, 0))
        >>>
        >>> # Executor checks each event
        >>> if result.should_skip(event):
        ...     continue  # Already processed via snapshot
        >>> else:
        ...     await processor.handle(event.data)  # Process normally
    """

    skip_before: datetime | None = None

    def should_skip(self, event: "Event") -> bool:
        """Check if an event should be skipped (already processed during catchup).

        Args:
            event: The event to check

        Returns:
            True if event.timestamp <= skip_before (already processed),
            False if event should be processed normally
        """
        if self.skip_before is None:
            return False
        return event.timestamp <= self.skip_before


class CatchupStrategy(ABC, Generic[P]):
    """Strategy for catching up an event processor with the event store.

    Event processors can fall behind the write model when:
    - They cannot keep up with the event publication rate
    - They are created after events have already been published
    - They experience downtime or processing delays

    Different catchup strategies offer trade-offs between:
    - Speed: How quickly the processor catches up
    - Resource usage: Compute and memory requirements
    - Consistency: Guarantees about event ordering and completeness
    - Applicability: Which scenarios the strategy works for

    Implementations:
    - NoCatchup: Skip catchup entirely (for testing or specific use cases)
    - FromReplayingEvents: Replay all events from the event store
    - FromAggregateSnapshot: Initialize from aggregate snapshots
    - FromProcedure: Custom initialization via external procedure
    """

    @abstractmethod
    def is_blocking(self) -> bool:
        """Determine if catchup blocks new event processing.

        Returns:
            True if the processor must complete catchup before processing
            new events (blocking). False if catchup runs concurrently with
            new event processing (non-blocking) via asyncio.

        Note:
            Blocking catchup ensures consistency but may delay processing.
            Non-blocking catchup improves responsiveness but may process
            events out of order temporarily.
        """
        ...

    @abstractmethod
    async def catchup(self, processor: P) -> CatchupResult | None:
        """Execute the catchup strategy to synchronize with the event store.

        This method is invoked:
        - When the processor is first started
        - When the associated CatchupCondition is met during runtime

        Implementations should:
        - Load necessary state to bring the processor up to date
        - Handle errors gracefully (network issues, missing data, etc.)
        - Track progress to resume from failures

        Args:
            processor: The event processor instance to catch up

        Returns:
            CatchupResult if events should be skipped, None otherwise

        Raises:
            Implementation-specific exceptions for catchup failures
        """
        ...


class NoCatchup(CatchupStrategy):
    """No catchup - processor starts from current position.

    Use this strategy when:
    - The processor only needs to handle new events (not historical)
    - Historical state is not required for the read model
    - Testing scenarios where catchup is not needed

    Example:
        >>> # Notification processor that only sends for new events
        >>> processor = NotificationProcessor()
        >>> executor = EventProcessorExecutor(
        ...     subscription=event_bus.subscribe("notifications"),
        ...     processor=processor,
        ...     condition=Never(),
        ...     strategy=NoCatchup(),
        ...     batch_size=10
        ... )
    """

    def is_blocking(self) -> bool:
        """NoCatchup is non-blocking (nothing to block on).

        Returns:
            False - no catchup operation to wait for
        """
        return False

    async def catchup(self, processor: P) -> None:
        """No-op - no catchup is performed.

        Args:
            processor: The event processor (ignored)

        Returns:
            None - no skip window needed
        """
        return None


class FromReplayingEvents(CatchupStrategy):
    """Catch up by replaying all historical events from the event store.

    This is the conceptually simplest and most straightforward catchup strategy.
    It replays every event from the beginning (or from a checkpoint) through
    the event processor.

    **Advantages:**
    - Simple and correct - guarantees all events are processed
    - No additional infrastructure needed (uses existing event store)
    - interlock can optimize by filtering irrelevant events

    **Disadvantages:**
    - Can be very slow for large event stores (millions+ events)
    - May be intractable for high-volume systems
    - Processes events the processor doesn't care about
    - Resource intensive (CPU, memory, I/O)

    **Best for:**
    - Small to medium event stores (< 1M events)
    - Initial processor development and testing
    - Systems where correctness is more important than speed

    Note:
        This is the default and recommended strategy for most use cases.
        Only consider alternatives if replay time becomes problematic.
    """

    def is_blocking(self) -> bool:
        """Replay is typically blocking to ensure consistency.

        Returns:
            True - processor waits for replay before processing new events
        """
        return True

    async def catchup(self, processor: P) -> None:
        """Replay events from the event store.

        Args:
            processor: The event processor to replay events through

        Returns:
            None - no skip window needed

        Note:
            Implementation pending - will replay historical events
            through the processor's event handlers.
        """
        # TODO: Implement event replay from event store
        return None


class FromAggregateSnapshot(CatchupStrategy[P], Generic[P]):
    """Initialize processor state from aggregate snapshots.

    This strategy loads fully-hydrated aggregates (snapshot + events) and
    projects their current state into the processor using an AggregateProjector.
    This is much faster than replaying all historical events.

    The strategy is resumable - it saves checkpoints after processing batches
    of aggregates, allowing it to resume from the last checkpoint after crashes.

    **Applicable when:**
    - Read model is derived from aggregate state
    - Aggregate snapshots are available and maintained
    - You can write an AggregateProjector to translate aggregate → processor state

    **Advantages:**
    - Much faster than full event replay
    - Resumable via checkpoints (crash recovery)
    - Leverages existing snapshot infrastructure
    - Type-safe with full generic support

    **Disadvantages:**
    - Requires snapshot strategy to be configured
    - Requires writing an AggregateProjector
    - Only processes current aggregate state (not full event history)

    **Not applicable when:**
    - Processor needs access to all historical events (use FromReplayingEvents)
    - No snapshots are maintained

    Type Parameters:
        A: Aggregate type to load
        P: Processor type to initialize

    Example:
        >>> class UserProfileProjector(AggregateProjector[User, UserProfileProcessor]):
        ...     async def project(self, user: User, processor: UserProfileProcessor):
        ...         processor.profiles[user.id] = {"name": user.name, "email": user.email}
        >>>
        >>> strategy = FromAggregateSnapshot(
        ...     repository=user_repository,
        ...     projector=UserProfileProjector(),
        ...     checkpoint_backend=InMemoryCheckpointBackend()
        ... )
        >>>
        >>> # Executor will call:
        >>> result = await strategy.catchup(processor)
        >>> # Processor is now hydrated from all User aggregates
        >>> # result.skip_before tells executor to skip old events
    """

    def __init__(
        self,
        repository: "AggregateRepository",
        projector: "AggregateProjector",
        checkpoint_backend: "CheckpointBackend",
    ):
        """Initialize the snapshot-based catchup strategy.

        Args:
            repository: Repository for loading aggregates of type A
            projector: Projector to translate aggregate state → processor state
            checkpoint_backend: Backend for saving/loading checkpoints
        """
        self.repository: AggregateRepository = repository
        self.projector: AggregateProjector = projector
        self.checkpoint_backend: CheckpointBackend = checkpoint_backend

    def is_blocking(self) -> bool:
        """Snapshot loading is blocking for consistency.

        Returns:
            True - processor loads all aggregates before processing new events
        """
        return True

    async def catchup(self, processor: P) -> CatchupResult:
        """Load aggregates from snapshots and project into processor.

        This method:
        1. Loads checkpoint (if exists) to resume from previous progress
        2. Gets all aggregate IDs of the repository's type
        3. Filters out already-processed IDs from checkpoint
        4. For each remaining aggregate:
           - Loads it via repository (snapshot + events)
           - Projects it into processor
           - Tracks max timestamp
           - Saves checkpoint every N aggregates
        5. Returns CatchupResult with skip window

        Args:
            processor: The event processor to hydrate

        Returns:
            CatchupResult with skip_before set to the maximum aggregate.last_event_time,
            allowing the executor to skip events that were already incorporated into
            the loaded aggregates.

        Raises:
            Any exceptions from repository.acquire(), projector.project(),
            or checkpoint_backend operations.
        """
        from .checkpoint import Checkpoint

        processor_name = processor.__class__.__name__

        # Load checkpoint to resume from previous progress
        checkpoint = await self.checkpoint_backend.load_checkpoint(processor_name)
        if checkpoint is None:
            checkpoint = Checkpoint(
                processor_name=processor_name,
                processed_aggregate_ids=set(),
                max_timestamp=datetime.min.replace(tzinfo=None),
                events_processed=0,
            )

        # Get all aggregate IDs of this type
        all_ids = await self.repository.list_all_ids()

        # Filter out already processed
        remaining_ids = [
            agg_id
            for agg_id in all_ids
            if agg_id not in checkpoint.processed_aggregate_ids
        ]

        # Process each aggregate
        for agg_id in remaining_ids:
            # Load fully-hydrated aggregate (snapshot + events)
            async with self.repository.acquire(agg_id) as aggregate:
                # Project aggregate state into processor
                await self.projector.project(aggregate, processor)

                # Track progress in checkpoint
                if aggregate.last_event_time > checkpoint.max_timestamp:
                    checkpoint.max_timestamp = aggregate.last_event_time
                checkpoint.processed_aggregate_ids.add(agg_id)
                checkpoint.events_processed += aggregate.version

                # Save checkpoint every 100 aggregates for resumability
                if len(checkpoint.processed_aggregate_ids) % 100 == 0:
                    await self.checkpoint_backend.save_checkpoint(checkpoint)

        # Save final checkpoint
        await self.checkpoint_backend.save_checkpoint(checkpoint)

        # Return skip window to avoid double-processing
        return CatchupResult(skip_before=checkpoint.max_timestamp)
