from typing import Any

from ulid import ULID

from ...domain import Event
from .delivery import EventDelivery
from .store import EventStore
from .upcasting import UpcastingPipeline


class EventBus:
    """Coordinates event persistence, upcasting, and delivery.

    EventBus is the main entry point for publishing and loading events in
    the event sourcing infrastructure. It orchestrates:

    1. **Upcasting**: Transforms events to correct schema versions (via pipeline)
    2. **Persistence**: Durably stores events (via EventStore)
    3. **Delivery**: Delivers events to processors (via EventDelivery)

    The bus ensures events flow through the upcasting pipeline in both
    directions - events are upcasted when written (eager strategy) and
    when read (lazy strategy) based on the configured UpcastingPipeline.

    Event delivery is controlled by the EventDelivery strategy:
    - SynchronousDelivery: Processors execute immediately during publish_events()
    - AsynchronousDelivery: Processors consume via subscriptions (run_event_processors())

    The delivery strategy determines architectural trade-offs between simplicity
    (synchronous) and scalability (asynchronous with separate processor execution).
    """

    def __init__(
        self,
        store: EventStore,
        delivery: EventDelivery,
        upcasting_pipeline: UpcastingPipeline,
    ):
        """Initialize the event bus with its dependencies.

        Args:
            store: Persistent storage for event sourcing
            delivery: Delivery strategy for executing processors
            upcasting_pipeline: Pipeline for event schema evolution
        """
        self.store = store
        self.delivery = delivery
        self.upcasting_pipeline = upcasting_pipeline

    async def publish_events(
        self,
        events: list[Event[Any]],
        expected_version: int,
    ) -> None:
        """Publish events to storage and deliver to processors.

        This method coordinates the full event publishing flow:
        1. Upcast events to target versions (based on strategy)
        2. Persist events to the event store (with optimistic locking)
        3. Deliver events to processors (based on delivery strategy)

        Args:
            events: List of events to publish, typically from an aggregate's
                uncommitted_events after handling a command.
            expected_version: The aggregate version before these events,
                used for optimistic concurrency control.

        Raises:
            ConcurrencyError: If another process modified the aggregate
                (expected_version doesn't match current version in store).
            Exception: Any exception raised by the delivery strategy.
                For SynchronousDelivery, processor errors will fail the command.
        """
        upcasted_events = await self.upcasting_pipeline.write_upcast(events)
        await self.store.save_events(upcasted_events, expected_version)
        await self.delivery.deliver(upcasted_events)

    async def load_events(
        self,
        aggregate_id: ULID,
        min_version: int,
    ) -> list[Event[Any]]:
        """Load events from storage with schema evolution applied.

        This method coordinates event loading:
        1. Retrieve events from the event store
        2. Upcast events to current schema versions (based on strategy)
        3. Return complete Event objects ready for aggregate reconstruction

        Args:
            aggregate_id: Unique identifier of the aggregate to load events for
            min_version: Minimum event sequence number to load (inclusive).
                Use 0 to load all events, or snapshot_version + 1 to load
                only events after a snapshot.

        Returns:
            List of complete Event objects in sequence order, upcasted to
            current schema versions, including all metadata (timestamp, etc.).
        """
        events = await self.store.load_events(aggregate_id, min_version)
        return await self.upcasting_pipeline.read_upcast(events)
