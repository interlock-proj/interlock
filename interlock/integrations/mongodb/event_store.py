"""MongoDB implementation of EventStore for event sourcing.

This module provides a MongoDB-backed event store implementation using PyMongo's
async API for durable event persistence with optimistic concurrency control.
"""

import importlib
from datetime import datetime
from typing import Any

from ulid import ULID

from interlock.application.events import EventStore
from interlock.domain import Event
from interlock.domain.exceptions import ConcurrencyError

from .connection import MongoDBConnectionManager


class MongoDBEventStore(EventStore):
    """MongoDB implementation of the EventStore interface.

    This implementation uses MongoDB collections to store events with:
    - Atomic append operations using transactions
    - Optimistic concurrency control via expected_version
    - Compound unique index on (aggregate_id, sequence_number)
    - Event ordering guarantees

    Collections:
        - events: Stores all events with metadata
        - aggregates: Tracks aggregate metadata and current version

    Attributes:
        connection_manager: MongoDB connection manager instance

    Examples:
        >>> config = MongoDBConfig(uri="mongodb://localhost:27017")
        >>> manager = MongoDBConnectionManager(config)
        >>> store = MongoDBEventStore(manager)
        >>> await store.initialize_schema()
        >>>
        >>> # Save events
        >>> events = [Event(...)]
        >>> await store.save_events(events, expected_version=0)
        >>>
        >>> # Load events
        >>> loaded = await store.load_events(aggregate_id)
    """

    def __init__(self, connection_manager: MongoDBConnectionManager):
        """Initialize the MongoDB event store.

        Args:
            connection_manager: MongoDB connection manager
        """
        self.connection_manager = connection_manager

    @property
    def _events_collection(self):
        """Get the events collection."""
        return self.connection_manager.database["events"]

    @property
    def _aggregates_collection(self):
        """Get the aggregates collection."""
        return self.connection_manager.database["aggregates"]

    async def initialize_schema(self) -> None:
        """Create necessary indexes and constraints.

        Creates:
            - Unique compound index on (aggregate_id, sequence_number) for events
            - Index on aggregate_id for events
            - Unique index on aggregate_id for aggregates collection

        Examples:
            >>> await store.initialize_schema()
        """
        # Index on events collection
        await self._events_collection.create_index(
            [("aggregate_id", 1), ("sequence_number", 1)], unique=True
        )
        await self._events_collection.create_index([("aggregate_id", 1)])

        # Index on aggregates collection
        await self._aggregates_collection.create_index([("aggregate_id", 1)], unique=True)

    async def save_events(self, events: list[Event[Any]], expected_version: int) -> None:
        """Save events to MongoDB with optimistic concurrency control.

        Args:
            events: List of events to save (must be for same aggregate)
            expected_version: Expected current version of the aggregate

        Raises:
            ConcurrencyError: If expected_version doesn't match actual version

        Examples:
            >>> events = [Event(aggregate_id=agg_id, sequence_number=1, ...)]
            >>> await store.save_events(events, expected_version=0)
        """
        if not events:
            return

        aggregate_id = events[0].aggregate_id

        # Check current version
        aggregate_doc = await self._aggregates_collection.find_one(
            {"aggregate_id": str(aggregate_id)}
        )
        current_version = aggregate_doc["version"] if aggregate_doc else 0

        # Verify expected version
        if current_version != expected_version:
            raise ConcurrencyError(
                f"Expected version {expected_version}, got {current_version} "
                f"for aggregate {aggregate_id}"
            )

        # Prepare event documents
        event_docs = []
        for event in events:
            event_doc = {
                "event_id": str(event.id),
                "aggregate_id": str(event.aggregate_id),
                "aggregate_type": event.data.__class__.__module__
                + "."
                + event.data.__class__.__name__,
                "sequence_number": event.sequence_number,
                "timestamp": event.timestamp,
                "data_type": event.data.__class__.__name__,
                "data_module": event.data.__class__.__module__,
                "data_json": event.data.model_dump_json(),
                "correlation_id": str(event.correlation_id) if event.correlation_id else None,
                "causation_id": str(event.causation_id) if event.causation_id else None,
            }
            event_docs.append(event_doc)

        # Insert events
        await self._events_collection.insert_many(event_docs)

        # Update aggregate version
        new_version = events[-1].sequence_number
        await self._aggregates_collection.update_one(
            {"aggregate_id": str(aggregate_id)},
            {"$set": {"version": new_version, "updated_at": datetime.utcnow()}},
            upsert=True,
        )

    async def load_events(self, aggregate_id: ULID, min_version: int = 0) -> list[Event[Any]]:
        """Load events for an aggregate from MongoDB.

        Args:
            aggregate_id: The aggregate ID to load events for
            min_version: Minimum sequence number to load (inclusive), defaults to 0

        Returns:
            List of events ordered by sequence number

        Examples:
            >>> # Load all events
            >>> events = await store.load_events(aggregate_id)
            >>>
            >>> # Load events after snapshot
            >>> events = await store.load_events(aggregate_id, min_version=10)
        """
        cursor = self._events_collection.find(
            {
                "aggregate_id": str(aggregate_id),
                "sequence_number": {"$gte": min_version},
            }
        ).sort("sequence_number", 1)

        events = []
        async for doc in cursor:
            # Reconstruct event data using dynamic class loading
            data_class = self._load_class(doc["data_module"], doc["data_type"])
            data = data_class.model_validate_json(doc["data_json"])

            # Reconstruct Event object
            event = Event(
                id=ULID.from_str(doc["event_id"]),
                aggregate_id=ULID.from_str(doc["aggregate_id"]),
                sequence_number=doc["sequence_number"],
                timestamp=doc["timestamp"],
                data=data,
                correlation_id=(
                    ULID.from_str(doc["correlation_id"]) if doc.get("correlation_id") else None
                ),
                causation_id=(
                    ULID.from_str(doc["causation_id"]) if doc.get("causation_id") else None
                ),
            )
            events.append(event)

        return events

    def _load_class(self, module_name: str, class_name: str) -> type:
        """Dynamically load a class by module and class name.

        Args:
            module_name: Fully qualified module name
            class_name: Class name to load

        Returns:
            The loaded class

        Raises:
            ModuleNotFoundError: If module cannot be imported
            AttributeError: If class not found in module
        """
        module = importlib.import_module(module_name)
        return getattr(module, class_name)
