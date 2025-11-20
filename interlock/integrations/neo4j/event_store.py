"""Neo4j implementation of EventStore."""

import importlib
from typing import Any

from ulid import ULID

from ...aggregates.exceptions import ConcurrencyError
from ...events import Event, EventStore
from .connection import Neo4jConnectionManager

# Cypher queries as constants
CREATE_AGGREGATE_INDEX = "CREATE INDEX aggregate_id_index IF NOT EXISTS FOR (a:Aggregate) ON (a.id)"

CREATE_EVENT_INDEX = (
    "CREATE INDEX event_lookup IF NOT EXISTS FOR (e:Event) ON (e.aggregate_id, e.sequence_number)"
)

CREATE_AGGREGATE_CONSTRAINT = (
    "CREATE CONSTRAINT aggregate_id_unique IF NOT EXISTS FOR (a:Aggregate) REQUIRE a.id IS UNIQUE"
)

GET_CURRENT_VERSION = """
MERGE (a:Aggregate {id: $aggregate_id})
ON CREATE SET a.type = $aggregate_type
WITH a
OPTIONAL MATCH (a)-[:HAS_EVENT]->(e:Event)
WITH a, e ORDER BY e.sequence_number DESC
RETURN COALESCE(HEAD(COLLECT(e.sequence_number)), 0) as current_version
LIMIT 1
"""

CREATE_EVENT = """
MATCH (a:Aggregate {id: $aggregate_id})
CREATE (e:Event {
    id: $event_id,
    aggregate_id: $aggregate_id,
    sequence_number: $sequence_number,
    timestamp: datetime($timestamp),
    data_type: $data_type,
    data_module: $data_module,
    data_json: $data_json
})
CREATE (a)-[:HAS_EVENT]->(e)
"""

LINK_EVENTS = """
MATCH (prev:Event {id: $prev_id})
MATCH (curr:Event {id: $curr_id})
CREATE (prev)-[:NEXT_EVENT]->(curr)
"""

LINK_TO_LAST_EVENT = """
MATCH (a:Aggregate {id: $aggregate_id})-[:HAS_EVENT]->(prev:Event)
WHERE prev.sequence_number = $prev_seq
MATCH (curr:Event {id: $curr_id})
CREATE (prev)-[:NEXT_EVENT]->(curr)
"""

LOAD_EVENTS = """
MATCH (a:Aggregate {id: $aggregate_id})-[:HAS_EVENT]->(e:Event)
WHERE e.sequence_number >= $min_version
RETURN e ORDER BY e.sequence_number ASC
"""


class Neo4jEventStore(EventStore):
    """Neo4j-backed async event store.

    Stores events as nodes with relationships for stream ordering.
    Event types are stored as module paths for dynamic loading.
    """

    def __init__(self, connection_manager: Neo4jConnectionManager):
        self.connection_manager = connection_manager

    async def initialize_schema(self) -> None:
        """Create required indexes and constraints."""
        async with self.connection_manager.session() as session:
            # Create constraint first (which includes index automatically)
            await session.run(CREATE_AGGREGATE_CONSTRAINT)
            await session.run(CREATE_EVENT_INDEX)

    async def save_events(self, events: list[Event[Any]], expected_version: int) -> None:
        """Save events with optimistic concurrency control."""
        if not events:
            return

        aggregate_id = str(events[0].aggregate_id)

        async with self.connection_manager.transaction() as tx:
            current_version = await self._get_current_version(
                tx, aggregate_id, type(events[0].data).__name__
            )
            self._check_version(expected_version, current_version)
            await self._persist_events(tx, events, aggregate_id, expected_version)

    async def load_events(self, aggregate_id: ULID, min_version: int = 0) -> list[Event[Any]]:
        """Load events from specified version onwards."""
        async with self.connection_manager.session() as session:
            result = await session.run(
                LOAD_EVENTS,
                aggregate_id=str(aggregate_id),
                min_version=min_version,
            )
            return [self._deserialize_event(rec["e"]) async for rec in result]

    async def _get_current_version(self, tx: object, aggregate_id: str, aggregate_type: str) -> int:
        """Get current version of aggregate."""
        result = await tx.run(  # type: ignore[attr-defined]
            GET_CURRENT_VERSION,
            aggregate_id=aggregate_id,
            aggregate_type=aggregate_type,
        )
        record = await result.single()  # type: ignore[attr-defined]
        if record is None:
            return 0
        return record["current_version"]  # type: ignore[no-any-return]

    def _check_version(self, expected: int, current: int) -> None:
        """Verify expected version matches current."""
        if current != expected:
            raise ConcurrencyError(f"Expected version {expected}, got {current}")

    async def _persist_events(
        self,
        tx: object,
        events: list[Event[Any]],
        aggregate_id: str,
        expected_version: int,
    ) -> None:
        """Persist events and link them in order."""
        last_event_id: str | None = None

        for event in events:
            await self._create_event(tx, event, aggregate_id)
            await self._link_event(tx, event, last_event_id, aggregate_id, expected_version)
            last_event_id = str(event.id)

    async def _create_event(self, tx: object, event: Event[Any], aggregate_id: str) -> None:
        """Create event node."""
        data_class = type(event.data)
        await tx.run(  # type: ignore[attr-defined]
            CREATE_EVENT,
            aggregate_id=aggregate_id,
            event_id=str(event.id),
            sequence_number=event.sequence_number,
            timestamp=event.timestamp.isoformat(),
            data_type=data_class.__name__,
            data_module=data_class.__module__,
            data_json=event.data.model_dump_json(),
        )

    async def _link_event(
        self,
        tx: object,
        event: Event[Any],
        last_event_id: str | None,
        aggregate_id: str,
        expected_version: int,
    ) -> None:
        """Link event to previous event in stream."""
        if last_event_id:
            await tx.run(LINK_EVENTS, prev_id=last_event_id, curr_id=str(event.id))  # type: ignore[attr-defined]
        elif expected_version > 0:
            await tx.run(  # type: ignore[attr-defined]
                LINK_TO_LAST_EVENT,
                aggregate_id=aggregate_id,
                prev_seq=expected_version,
                curr_id=str(event.id),
            )

    def _deserialize_event(self, event_node: dict[str, Any]) -> Event[Any]:
        """Deserialize event from Neo4j node."""
        data_module = event_node["data_module"]
        data_type = event_node["data_type"]
        data_json = event_node["data_json"]

        event_class = self._load_class(data_module, data_type)
        data = event_class.model_validate_json(data_json)  # type: ignore[attr-defined]

        # Convert Neo4j DateTime to Python datetime
        timestamp = event_node["timestamp"]
        if hasattr(timestamp, "to_native"):
            timestamp = timestamp.to_native()

        return Event(
            id=ULID.from_str(event_node["id"]),
            aggregate_id=ULID.from_str(event_node["aggregate_id"]),
            sequence_number=event_node["sequence_number"],
            timestamp=timestamp,
            data=data,
        )

    def _load_class(self, module_name: str, class_name: str) -> type:
        """Dynamically load a class from its module path."""
        module = importlib.import_module(module_name)
        return getattr(module, class_name)  # type: ignore[no-any-return]
