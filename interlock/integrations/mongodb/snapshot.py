"""MongoDB implementation of AggregateSnapshotStorageBackend."""

import importlib
from datetime import datetime
from enum import Enum
from typing import Any

from ulid import ULID

from interlock.aggregates import Aggregate, AggregateSnapshotStorageBackend

from .connection import MongoDBConnectionManager


class SnapshotStorageStrategy(str, Enum):
    """Strategy for storing snapshots."""

    SINGLE = "single"  # Keep only latest snapshot per aggregate
    VERSIONED = "versioned"  # Keep all snapshot versions


class MongoDBSnapshotBackend(AggregateSnapshotStorageBackend):
    """MongoDB-backed async snapshot storage.

    Supports two storage strategies:
    - SINGLE: Overwrites snapshot (one per aggregate) using replace_one with upsert
    - VERSIONED: Keeps all snapshot versions as separate documents

    Collections:
        - snapshots: Stores aggregate snapshots with metadata

    Examples:
        >>> config = MongoDBConfig(uri="mongodb://localhost:27017")
        >>> manager = MongoDBConnectionManager(config)
        >>> backend = MongoDBSnapshotBackend(manager, SnapshotStorageStrategy.SINGLE)
        >>> await backend.initialize_schema()
        >>>
        >>> # Save snapshot
        >>> await backend.save_snapshot(aggregate)
        >>>
        >>> # Load snapshot
        >>> snapshot = await backend.load_snapshot(aggregate_id)
    """

    def __init__(
        self,
        connection_manager: MongoDBConnectionManager,
        strategy: SnapshotStorageStrategy = SnapshotStorageStrategy.SINGLE,
    ):
        """Initialize the MongoDB snapshot backend.

        Args:
            connection_manager: MongoDB connection manager
            strategy: Storage strategy (SINGLE or VERSIONED)
        """
        self.connection_manager = connection_manager
        self.strategy = strategy

    @property
    def _snapshots_collection(self):
        """Get the snapshots collection."""
        return self.connection_manager.database["snapshots"]

    async def initialize_schema(self) -> None:
        """Create necessary indexes for snapshot storage.

        Creates:
            - Compound index on (aggregate_id, version) descending for efficient lookup
            - Index on aggregate_type for list_aggregate_ids_by_type queries

        Examples:
            >>> await backend.initialize_schema()
        """
        # Index for efficient snapshot lookup by aggregate and version
        await self._snapshots_collection.create_index(
            [
                ("aggregate_id", 1),
                ("version", -1),
            ]  # version descending for latest first
        )
        # Index for querying by aggregate type
        await self._snapshots_collection.create_index([("aggregate_type", 1)])

    async def save_snapshot(self, aggregate: Aggregate) -> None:
        """Save aggregate snapshot to MongoDB.

        For SINGLE strategy: Uses replace_one with upsert to overwrite existing snapshot
        For VERSIONED strategy: Inserts new snapshot document, keeping all versions

        Args:
            aggregate: The aggregate to snapshot

        Examples:
            >>> await backend.save_snapshot(my_aggregate)
        """
        aggregate_class = type(aggregate)

        snapshot_doc = {
            "aggregate_id": str(aggregate.id),
            "aggregate_type": f"{aggregate_class.__module__}.{aggregate_class.__name__}",
            "aggregate_module": aggregate_class.__module__,
            "aggregate_class_name": aggregate_class.__name__,
            "version": aggregate.version,
            "state_json": aggregate.model_dump_json(exclude={"uncommitted_events"}),
            "created_at": datetime.utcnow(),
        }

        if self.strategy == SnapshotStorageStrategy.SINGLE:
            # Replace existing snapshot for this aggregate (keep only latest)
            await self._snapshots_collection.replace_one(
                {"aggregate_id": str(aggregate.id)}, snapshot_doc, upsert=True
            )
        else:  # VERSIONED
            # Insert new snapshot, keeping all versions
            await self._snapshots_collection.insert_one(snapshot_doc)

    async def load_snapshot(
        self, aggregate_id: ULID, intended_version: int | None = None
    ) -> Aggregate | None:
        """Load latest snapshot at or below intended version.

        Args:
            aggregate_id: The aggregate ID to load snapshot for
            intended_version: Maximum version to load (None for latest)

        Returns:
            The aggregate snapshot if found, None otherwise

        Examples:
            >>> # Load latest snapshot
            >>> snapshot = await backend.load_snapshot(aggregate_id)
            >>>
            >>> # Load snapshot at or below version 10
            >>> snapshot = await backend.load_snapshot(aggregate_id, intended_version=10)
        """
        query = {"aggregate_id": str(aggregate_id)}

        if intended_version is not None:
            query["version"] = {"$lte": intended_version}

        # Find the latest snapshot matching the criteria
        snapshot_doc = await self._snapshots_collection.find_one(
            query,
            sort=[("version", -1)],  # Descending order, get latest first
        )

        if not snapshot_doc:
            return None

        return self._deserialize_snapshot(snapshot_doc)

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

        # For SINGLE strategy, we get one document per aggregate
        # For VERSIONED, we need to get distinct aggregate_ids
        cursor = self._snapshots_collection.find(
            {"aggregate_type": aggregate_type_str}, {"aggregate_id": 1}
        )

        aggregate_ids = set()
        async for doc in cursor:
            aggregate_ids.add(ULID.from_str(doc["aggregate_id"]))

        return list(aggregate_ids)

    def _deserialize_snapshot(self, snapshot_doc: dict[str, Any]) -> Aggregate:
        """Deserialize aggregate from MongoDB snapshot document.

        Args:
            snapshot_doc: MongoDB document containing snapshot data

        Returns:
            Reconstructed aggregate instance
        """
        aggregate_module = snapshot_doc["aggregate_module"]
        aggregate_class_name = snapshot_doc["aggregate_class_name"]
        state_json = snapshot_doc["state_json"]

        aggregate_class = self._load_class(aggregate_module, aggregate_class_name)
        return aggregate_class.model_validate_json(state_json)  # type: ignore[no-any-return]

    def _load_class(self, module_name: str, class_name: str) -> type:
        """Dynamically load a class from its module path.

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
        return getattr(module, class_name)  # type: ignore[no-any-return]
