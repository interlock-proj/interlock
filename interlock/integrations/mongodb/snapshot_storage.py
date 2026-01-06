"""MongoDB implementation of AggregateSnapshotStorageBackend."""

from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from interlock.application.aggregates.repository.snapshot import (
    AggregateSnapshotStorageBackend,
)
from interlock.domain import Aggregate
from interlock.integrations.mongodb.collection import (
    IndexDirection,
    IndexedCollection,
    IndexSpec,
)
from interlock.integrations.mongodb.config import MongoConfiguration
from interlock.integrations.mongodb.type_loader import get_qualified_name, load_type


class SnapshotDocument(BaseModel):
    """Aggregate snapshot document representation for MongoDB storage."""

    aggregate_id: str
    aggregate_type: str = Field(description="Fully qualified type name of the aggregate")
    version: int
    snapshot: dict[str, Any] = Field(description="Serialized aggregate state")

    @classmethod
    def from_value(cls, aggregate: Aggregate) -> "SnapshotDocument":
        """Create a document from an aggregate."""
        return cls(
            aggregate_id=str(aggregate.id),
            aggregate_type=get_qualified_name(type(aggregate)),
            version=aggregate.version,
            snapshot=aggregate.model_dump(mode="json"),
        )

    def to_value(self) -> Aggregate:
        """Convert the document back to an aggregate."""
        aggregate_type = load_type(self.aggregate_type)
        result: Aggregate = aggregate_type(**self.snapshot)
        return result


class SnapshotStrategy(ABC):
    """Strategy for snapshot storage behavior.

    Encapsulates the differences between single and multiple snapshot modes:
    - Index specifications
    - Save behavior (overwrite vs append)
    - Load behavior (simple lookup vs version filtering)
    """

    @property
    @abstractmethod
    def indexes(self) -> list[IndexSpec]:
        """Index specifications for this strategy."""
        ...

    @abstractmethod
    async def save(
        self,
        collection: IndexedCollection,
        aggregate: Aggregate,
    ) -> None:
        """Save a snapshot using this strategy."""
        ...

    @abstractmethod
    async def load(
        self,
        collection: IndexedCollection,
        aggregate_id: UUID,
        intended_version: int | None,
    ) -> dict[str, Any] | None:
        """Load a snapshot document using this strategy."""
        ...


class SingleSnapshotStrategy(SnapshotStrategy):
    """Strategy for single snapshot mode - one snapshot per aggregate.

    Overwrites the existing snapshot on save. More storage efficient
    but doesn't support historical version lookups.
    """

    @property
    def indexes(self) -> list[IndexSpec]:
        return [
            IndexSpec(keys=[("aggregate_id", IndexDirection.ASC)], unique=True),
            IndexSpec(keys=[("aggregate_type", IndexDirection.ASC)]),
        ]

    async def save(
        self,
        collection: IndexedCollection,
        aggregate: Aggregate,
    ) -> None:
        doc = SnapshotDocument.from_value(aggregate).model_dump(mode="json")
        await collection.replace_one(
            {"aggregate_id": str(aggregate.id)},
            doc,
            upsert=True,
        )

    async def load(
        self,
        collection: IndexedCollection,
        aggregate_id: UUID,
        intended_version: int | None,
    ) -> dict[str, Any] | None:
        doc = await collection.find_one({"aggregate_id": str(aggregate_id)})
        if doc is None:
            return None

        # In single mode, check if stored version is usable
        if intended_version is not None and doc["version"] > intended_version:
            return None

        return doc


class MultipleSnapshotStrategy(SnapshotStrategy):
    """Strategy for multiple snapshot mode - keeps version history.

    Appends new snapshots without overwriting. Supports historical
    version lookups via intended_version parameter.
    """

    @property
    def indexes(self) -> list[IndexSpec]:
        return [
            IndexSpec(
                keys=[
                    ("aggregate_id", IndexDirection.ASC),
                    ("version", IndexDirection.DESC),
                ],
                unique=True,
            ),
            IndexSpec(keys=[("aggregate_type", IndexDirection.ASC)]),
        ]

    async def save(
        self,
        collection: IndexedCollection,
        aggregate: Aggregate,
    ) -> None:
        doc = SnapshotDocument.from_value(aggregate).model_dump(mode="json")
        await collection.insert_one(doc)

    async def load(
        self,
        collection: IndexedCollection,
        aggregate_id: UUID,
        intended_version: int | None,
    ) -> dict[str, Any] | None:
        filter_query: dict[str, Any] = {"aggregate_id": str(aggregate_id)}
        if intended_version is not None:
            filter_query["version"] = {"$lte": intended_version}

        return await collection.find_latest(filter_query, sort_field="version")


class MongoSnapshotStorage(AggregateSnapshotStorageBackend):
    """MongoDB-backed aggregate snapshot storage.

    Supports two storage modes controlled by the `snapshot_mode` config:

    - **single**: One snapshot per aggregate (overwrites on save).
      Lower storage requirements, simpler queries.
    - **multiple**: Multiple versions per aggregate (appends).
      Supports historical lookups via `intended_version`.

    Document schema:
        {
            "_id": ObjectId (or aggregate_id in single mode),
            "aggregate_id": "UUID string",
            "aggregate_type": "module.ClassName",
            "version": int,
            "snapshot": { ... serialized aggregate ... }
        }

    Aggregate types are automatically resolved via dynamic import from
    the stored qualified type name - no manual registration required.

    Example:
        >>> from interlock.integrations.mongodb import (
        ...     MongoConfiguration, MongoSnapshotStorage
        ... )
        >>>
        >>> # Single mode (default) - one snapshot per aggregate
        >>> config = MongoConfiguration(snapshot_mode="single")
        >>> storage = MongoSnapshotStorage(config)
        >>>
        >>> # Multiple mode - keeps version history
        >>> config = MongoConfiguration(snapshot_mode="multiple")
        >>> storage = MongoSnapshotStorage(config)
        >>>
        >>> # Save a snapshot
        >>> await storage.save_snapshot(my_aggregate)
        >>>
        >>> # Load latest snapshot
        >>> aggregate = await storage.load_snapshot(aggregate_id)
        >>>
        >>> # Load snapshot at specific version (multiple mode)
        >>> aggregate = await storage.load_snapshot(aggregate_id, intended_version=5)
    """

    def __init__(self, config: MongoConfiguration) -> None:
        """Initialize the MongoDB snapshot storage.

        Args:
            config: MongoDB configuration providing connection and snapshot_mode.
        """
        self._strategy: SnapshotStrategy = (
            SingleSnapshotStrategy()
            if config.snapshot_mode == "single"
            else MultipleSnapshotStrategy()
        )
        self._collection = IndexedCollection(
            config.snapshots,
            indexes=self._strategy.indexes,
        )

    async def save_snapshot(self, aggregate: Aggregate) -> None:
        """Save a snapshot of the aggregate.

        In single mode, overwrites any existing snapshot.
        In multiple mode, appends a new version.

        Args:
            aggregate: The aggregate to save.
        """
        await self._strategy.save(self._collection, aggregate)

    async def load_snapshot(
        self,
        aggregate_id: UUID,
        intended_version: int | None = None,
    ) -> Aggregate | None:
        """Load a snapshot of the aggregate.

        In single mode:
            - Returns the snapshot if intended_version is None or >= stored version
            - Returns None if intended_version < stored version

        In multiple mode:
            - Returns the latest snapshot with version <= intended_version
            - Returns the latest snapshot if intended_version is None

        Args:
            aggregate_id: The ID of the aggregate to load.
            intended_version: Optional maximum version to load.

        Returns:
            The aggregate snapshot if found and valid, None otherwise.
        """
        doc = await self._strategy.load(self._collection, aggregate_id, intended_version)
        if doc is None:
            return None

        snapshot_doc = SnapshotDocument.model_validate(doc)
        return snapshot_doc.to_value()

    async def list_aggregate_ids_by_type(self, aggregate_type: type[Aggregate]) -> list[UUID]:
        """Get all aggregate IDs of a given type that have snapshots.

        Uses an aggregation pipeline to avoid the 16MB limit of distinct().

        Args:
            aggregate_type: The aggregate class type to filter by.

        Returns:
            List of aggregate IDs with snapshots of this type.
        """
        aggregate_type_name = get_qualified_name(aggregate_type)

        aggregate_ids: list[UUID] = []
        async for value in self._collection.distinct_values(
            "aggregate_id",
            filter={"aggregate_type": aggregate_type_name},
        ):
            aggregate_ids.append(UUID(value))

        return aggregate_ids
