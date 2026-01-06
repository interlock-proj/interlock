from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Generic, TypeVar

if TYPE_CHECKING:
    from ....domain import Event
    from .processor import EventProcessor

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

    def should_skip(self, event: "Event[Any]") -> bool:
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
    """

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
            Exception: Implementation-specific exceptions for catchup failures.
        """
        ...


class NoCatchup(CatchupStrategy["EventProcessor"]):
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

    async def catchup(self, processor: P) -> None:
        """No-op - no catchup is performed.

        Args:
            processor: The event processor (ignored)

        Returns:
            None - no skip window needed
        """
        return None
