"""Neo4j implementation of AggregateSnapshotStorageBackend."""

import importlib
from enum import Enum
from typing import Any

from ulid import ULID

from ...aggregates import Aggregate, AggregateSnapshotStorageBackend
from .connection import Neo4jConnectionManager


class SnapshotStorageStrategy(str, Enum):
    """Strategy for storing snapshots."""

    SINGLE = "single"  # Keep only latest snapshot per aggregate
    VERSIONED = "versioned"  # Keep all snapshot versions


# Cypher queries as constants
CREATE_SNAPSHOT_INDEX = (
    "CREATE INDEX snapshot_lookup IF NOT EXISTS FOR (s:Snapshot) ON (s.aggregate_id, s.version)"
)

SAVE_SNAPSHOT_SINGLE = """
MATCH (a:Aggregate {id: $aggregate_id})
OPTIONAL MATCH (a)-[:HAS_SNAPSHOT]->(old:Snapshot)
DETACH DELETE old
WITH a
MATCH (e:Event {aggregate_id: $aggregate_id, sequence_number: $version})
CREATE (s:Snapshot {
    id: $snapshot_id,
    aggregate_id: $aggregate_id,
    version: $version,
    timestamp: datetime($timestamp),
    aggregate_type: $aggregate_type,
    aggregate_module: $aggregate_module,
    state_json: $state_json
})
CREATE (a)-[:HAS_SNAPSHOT]->(s)
CREATE (s)-[:SNAPSHOT_AT_EVENT]->(e)
"""

SAVE_SNAPSHOT_VERSIONED = """
MATCH (a:Aggregate {id: $aggregate_id})
MATCH (e:Event {aggregate_id: $aggregate_id, sequence_number: $version})
CREATE (s:Snapshot {
    id: $snapshot_id,
    aggregate_id: $aggregate_id,
    version: $version,
    timestamp: datetime($timestamp),
    aggregate_type: $aggregate_type,
    aggregate_module: $aggregate_module,
    state_json: $state_json
})
CREATE (a)-[:HAS_SNAPSHOT]->(s)
CREATE (s)-[:SNAPSHOT_AT_EVENT]->(e)
"""

LOAD_SNAPSHOT = """
MATCH (a:Aggregate {id: $aggregate_id})-[:HAS_SNAPSHOT]->(s:Snapshot)
WHERE $intended_version IS NULL OR s.version <= $intended_version
RETURN s
ORDER BY s.version DESC
LIMIT 1
"""

LIST_AGGREGATE_IDS_BY_TYPE = """
MATCH (s:Snapshot)
WHERE s.aggregate_module + '.' + s.aggregate_type = $aggregate_type
RETURN DISTINCT s.aggregate_id
"""


class Neo4jSnapshotBackend(AggregateSnapshotStorageBackend):
    """Neo4j-backed async snapshot storage.

    Supports two storage strategies:
    - SINGLE: Overwrites snapshot (one per aggregate)
    - VERSIONED: Keeps all snapshot versions

    Graph relationships:
    - (Aggregate)-[:HAS_SNAPSHOT]->(Snapshot)
    - (Snapshot)-[:SNAPSHOT_AT_EVENT]->(Event)
    """

    def __init__(
        self,
        connection_manager: Neo4jConnectionManager,
        strategy: SnapshotStorageStrategy = SnapshotStorageStrategy.SINGLE,
    ):
        self.connection_manager = connection_manager
        self.strategy = strategy

    async def initialize_schema(self) -> None:
        """Create required indexes."""
        async with self.connection_manager.session() as session:
            await session.run(CREATE_SNAPSHOT_INDEX)

    async def save_snapshot(self, aggregate: Aggregate) -> None:
        """Save aggregate snapshot with relationships to aggregate and event."""
        aggregate_class = type(aggregate)
        query = (
            SAVE_SNAPSHOT_VERSIONED
            if self.strategy == SnapshotStorageStrategy.VERSIONED
            else SAVE_SNAPSHOT_SINGLE
        )

        async with self.connection_manager.session() as session:
            await session.run(
                query,
                snapshot_id=str(ULID()),
                aggregate_id=str(aggregate.id),
                version=aggregate.version,
                timestamp=aggregate.last_snapshot_time.isoformat(),
                aggregate_type=aggregate_class.__name__,
                aggregate_module=aggregate_class.__module__,
                state_json=aggregate.model_dump_json(exclude={"uncommitted_events"}),
            )

    async def load_snapshot(
        self, aggregate_id: ULID, intended_version: int | None = None
    ) -> Aggregate | None:
        """Load latest snapshot at or below intended version."""
        async with self.connection_manager.session() as session:
            result = await session.run(
                LOAD_SNAPSHOT,
                aggregate_id=str(aggregate_id),
                intended_version=intended_version,
            )

            record = await result.single()
            if not record:
                return None

            return self._deserialize_snapshot(record["s"])

    async def list_aggregate_ids_by_type(self, aggregate_type: type[Aggregate]) -> list[ULID]:
        """Get all aggregate IDs of a given type that have snapshots.

        This is used by catchup strategies to discover all aggregates of a
        particular type that need processing.

        Args:
            aggregate_type: The aggregate class type

        Returns:
            List of aggregate IDs with snapshots for this type

        Examples:
            >>> from myapp.aggregates import Order
            >>> order_ids = await backend.list_aggregate_ids_by_type(Order)
        """
        aggregate_type_str = f"{aggregate_type.__module__}.{aggregate_type.__name__}"

        async with self.connection_manager.session() as session:
            result = await session.run(
                LIST_AGGREGATE_IDS_BY_TYPE,
                aggregate_type=aggregate_type_str,
            )

            aggregate_ids = []
            async for record in result:
                aggregate_ids.append(ULID.from_str(record["aggregate_id"]))

            return aggregate_ids

    def _deserialize_snapshot(self, snapshot_node: dict[str, Any]) -> Aggregate:
        """Deserialize aggregate from Neo4j snapshot node."""
        aggregate_module = snapshot_node["aggregate_module"]
        aggregate_type = snapshot_node["aggregate_type"]
        state_json = snapshot_node["state_json"]

        aggregate_class = self._load_class(aggregate_module, aggregate_type)
        return aggregate_class.model_validate_json(state_json)  # type: ignore[no-any-return, attr-defined]

    def _load_class(self, module_name: str, class_name: str) -> type:
        """Dynamically load a class from its module path."""
        module = importlib.import_module(module_name)
        return getattr(module, class_name)  # type: ignore[no-any-return]
