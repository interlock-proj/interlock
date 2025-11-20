"""Event store interfaces and implementations for durable event persistence."""

from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Any

from ulid import ULID

from ..aggregates.exceptions import ConcurrencyError
from .event import Event


class EventStore(ABC):
    """Abstract interface for durable event persistence.

    EventStore provides the foundation for event sourcing by persisting
    events as an immutable, append-only log. Each aggregate's events form
    a stream that can be replayed to reconstruct aggregate state.

    Key responsibilities:
    - **Durability**: Events survive system failures
    - **Ordering**: Events are stored and retrieved in sequence
    - **Concurrency Control**: Optimistic locking via expected_version
    - **Immutability**: Events cannot be modified after storage
    """

    @abstractmethod
    async def save_events(
        self,
        events: list[Event[Any]],
        expected_version: int,
    ) -> None:
        """Persist events to the event store with optimistic concurrency control.

        Args:
            events: List of events to persist. Each event includes metadata
                (id, aggregate_id, sequence_number, timestamp) and typed data.
            expected_version: The version the aggregate is expected to be at
                before these events are appended. Used for optimistic locking.

        Raises:
            ConcurrencyError: If expected_version doesn't match the current
                version in the store (another process modified the aggregate).

        Note:
            Events are appended atomically - either all events are saved or
            none are. The store assigns sequence numbers starting from
            expected_version + 1.
        """
        ...

    @abstractmethod
    async def load_events(
        self,
        aggregate_id: ULID,
        min_version: int,
    ) -> list[Event[Any]]:
        """Load events for an aggregate from the event store.

        Args:
            aggregate_id: The unique identifier of the aggregate whose
                events should be loaded.
            min_version: The minimum sequence number to load (inclusive).
                Use 0 to load all events, or a snapshot version to load
                only events after the snapshot.

        Returns:
            List of events in sequence order. Events may have been upcasted
            to newer schema versions by the store implementation.
        """
        ...


class InMemoryEventStore(EventStore):
    """Dictionary-based in-memory event store for testing.

    Stores events in a dictionary keyed by aggregate ID. Each aggregate's
    events are kept in a list ordered by sequence number.

    This implementation is suitable for:
    - Unit tests (fast, no external dependencies)
    - Development and experimentation
    - Examples and documentation

    **NOT suitable for production** due to:
    - No durability (data lost on restart)
    - No optimistic concurrency control (no version checking)
    - No transaction support (partial writes possible on errors)
    - Memory usage grows unbounded
    - No distributed coordination
    """

    def __init__(self) -> None:
        """Initialize an empty in-memory event store."""
        self.by_aggregate_id: dict[ULID, list[Event[Any]]] = defaultdict(list)

    async def save_events(
        self,
        events: list[Event[Any]],
        expected_version: int,
    ) -> None:
        """Append events to the aggregate's event list with version checking.

        Args:
            events: Events to store, typically from an aggregate's uncommitted events
            expected_version: Expected current version - must match actual version

        Raises:
            ConcurrencyError: If expected_version doesn't match the current version
        """
        if not events:
            return

        aggregate_id = events[0].aggregate_id

        # Check current version matches expected
        current_events = self.by_aggregate_id[aggregate_id]
        current_version = current_events[-1].sequence_number if current_events else 0

        if current_version != expected_version:
            raise ConcurrencyError(f"Expected version {expected_version}, got {current_version}")

        # Version matches, safe to append events
        for event in events:
            self.by_aggregate_id[aggregate_id].append(event)

    async def load_events(
        self,
        aggregate_id: ULID,
        min_version: int,
    ) -> list[Event[Any]]:
        """Load events for an aggregate starting from a minimum version.

        Args:
            aggregate_id: The aggregate whose events to load
            min_version: Minimum sequence number (inclusive). Use 0 for all events.

        Returns:
            List of events with sequence_number >= min_version, in order.
            Returns empty list if aggregate has no events.
        """
        return [
            event
            for event in self.by_aggregate_id[aggregate_id]
            if event.sequence_number >= min_version
        ]
