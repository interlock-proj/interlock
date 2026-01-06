"""MongoDB implementation of EventStore."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

from interlock.application.events.store import EventStore
from interlock.domain import Event
from interlock.domain.exceptions import ConcurrencyError
from interlock.integrations.mongodb.collection import (
    IndexDirection,
    IndexedCollection,
    IndexSpec,
)
from interlock.integrations.mongodb.config import MongoConfiguration
from interlock.integrations.mongodb.type_loader import get_qualified_name, load_type

# Index specifications for the events collection
EVENT_STREAM_INDEX = IndexSpec(
    keys=[
        ("aggregate_id", IndexDirection.ASC),
        ("sequence_number", IndexDirection.ASC),
    ],
    unique=True,
)
AGGREGATE_ID_INDEX = IndexSpec(keys=[("aggregate_id", IndexDirection.ASC)])

EVENTS_INDEXES = [EVENT_STREAM_INDEX, AGGREGATE_ID_INDEX]


class EventDocument(BaseModel):
    """Event document representation for MongoDB storage."""

    event_id: str
    aggregate_id: str
    sequence_number: int
    timestamp: datetime
    correlation_id: str | None
    causation_id: str | None
    event_type: str
    data: dict[str, Any]

    @classmethod
    def from_value(cls, event: Event[Any]) -> "EventDocument":
        """Create a document from an Event."""
        return cls(
            event_id=str(event.id),
            aggregate_id=str(event.aggregate_id),
            sequence_number=event.sequence_number,
            timestamp=event.timestamp,
            correlation_id=str(event.correlation_id) if event.correlation_id else None,
            causation_id=str(event.causation_id) if event.causation_id else None,
            event_type=get_qualified_name(type(event.data)),
            data=event.data.model_dump(mode="json"),
        )

    def to_value(self) -> Event[Any]:
        """Convert the document back to an Event."""
        event_type = load_type(self.event_type)

        return Event(
            id=UUID(self.event_id),
            aggregate_id=UUID(self.aggregate_id),
            sequence_number=self.sequence_number,
            timestamp=self.timestamp,
            correlation_id=UUID(self.correlation_id) if self.correlation_id else None,
            causation_id=UUID(self.causation_id) if self.causation_id else None,
            data=event_type(**self.data),
        )


class MongoEventStore(EventStore):
    """MongoDB-backed event store with optimistic concurrency control.

    Stores events in a MongoDB collection with a unique compound index on
    (aggregate_id, sequence_number) to enforce ordering and enable optimistic
    concurrency control.

    The store supports:
    - Atomic event persistence with version checking
    - Loading events by aggregate ID with optional version filtering
    - Rewriting events for schema migration (upcasting)

    Event data types are automatically resolved via dynamic import from
    the stored qualified type name - no manual registration required.

    Example:
        >>> from interlock.integrations.mongodb import (
        ...     MongoConfiguration, MongoEventStore
        ... )
        >>>
        >>> config = MongoConfiguration()
        >>> store = MongoEventStore(config)
        >>>
        >>> # Save events with optimistic concurrency
        >>> await store.save_events(events, expected_version=0)
        >>>
        >>> # Load all events for an aggregate
        >>> events = await store.load_events(aggregate_id, min_version=0)
    """

    def __init__(self, config: MongoConfiguration) -> None:
        """Initialize the MongoDB event store.

        Args:
            config: MongoDB configuration providing connection and collections.
        """
        self._collection = IndexedCollection(config.events, indexes=EVENTS_INDEXES)

    async def save_events(
        self,
        events: list[Event[Any]],
        expected_version: int,
    ) -> None:
        """Persist events to MongoDB with optimistic concurrency control.

        Events are inserted atomically. If any event's sequence number
        conflicts with an existing event, the entire operation fails with
        a ConcurrencyError.

        Args:
            events: List of events to persist.
            expected_version: Expected aggregate version before these events.

        Raises:
            ConcurrencyError: If expected_version doesn't match the current
                version (duplicate sequence number detected).
        """
        if not events:
            return

        aggregate_id = events[0].aggregate_id

        # Verify expected version by checking current max sequence number
        latest = await self._collection.find_latest(
            {"aggregate_id": str(aggregate_id)},
            sort_field="sequence_number",
        )
        current_version = latest["sequence_number"] if latest else 0

        if current_version != expected_version:
            raise ConcurrencyError(
                f"Expected version {expected_version}, got {current_version}"
            )

        # Convert events to documents
        documents = [
            EventDocument.from_value(event).model_dump(mode="json") for event in events
        ]

        try:
            await self._collection.insert_many(documents, ordered=True)
        except DuplicateKeyError as e:
            raise ConcurrencyError(
                f"Concurrent modification detected for aggregate {aggregate_id}"
            ) from e

    async def load_events(
        self,
        aggregate_id: UUID,
        min_version: int,
    ) -> list[Event[Any]]:
        """Load events for an aggregate from MongoDB.

        Args:
            aggregate_id: The aggregate whose events to load.
            min_version: Minimum sequence number (inclusive).

        Returns:
            List of events in sequence order.
        """
        cursor = self._collection.find(
            {
                "aggregate_id": str(aggregate_id),
                "sequence_number": {"$gte": min_version},
            },
            sort=[("sequence_number", IndexDirection.ASC)],
        )

        return [EventDocument.model_validate(doc).to_value() async for doc in cursor]

    async def rewrite_events(self, events: list[Event[Any]]) -> None:
        """Rewrite existing events in place for schema migration.

        Updates events by matching (aggregate_id, sequence_number).

        Args:
            events: Events with updated data to write back.
        """
        for event in events:
            doc = EventDocument.from_value(event).model_dump(mode="json")
            await self._collection.update_one(
                {
                    "aggregate_id": str(event.aggregate_id),
                    "sequence_number": event.sequence_number,
                },
                {"$set": doc},
            )
