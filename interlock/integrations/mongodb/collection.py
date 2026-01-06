"""MongoDB collection wrapper with index management and query helpers.

This module provides an IndexedCollection class that wraps a MongoDB
AsyncCollection with automatic index management and helper methods for
common query patterns.
"""

from collections.abc import AsyncIterator
from enum import IntEnum
from typing import Any

from pydantic import BaseModel
from pymongo import ASCENDING, DESCENDING
from pymongo.asynchronous.collection import AsyncCollection


class IndexDirection(IntEnum):
    """Sort direction for MongoDB index fields."""

    ASC = ASCENDING
    """Ascending order (1)."""

    DESC = DESCENDING
    """Descending order (-1)."""


class IndexSpec(BaseModel):
    """Specification for a MongoDB index.

    Example:
        >>> # Simple index
        >>> IndexSpec(keys=[("aggregate_id", IndexDirection.ASC)])
        >>>
        >>> # Compound unique index
        >>> IndexSpec(
        ...     keys=[
        ...         ("aggregate_id", IndexDirection.ASC),
        ...         ("version", IndexDirection.DESC),
        ...     ],
        ...     unique=True,
        ... )
        >>>
        >>> # TTL index
        >>> IndexSpec(
        ...     keys=[("created_at", IndexDirection.ASC)],
        ...     expire_after_seconds=86400,
        ... )
    """

    model_config = {"arbitrary_types_allowed": True}

    keys: list[tuple[str, IndexDirection]]
    """(field_name, direction) tuples."""

    unique: bool = False
    """If True, enforce uniqueness."""

    expire_after_seconds: int | None = None
    """If set, create a TTL index."""

    async def apply(self, collection: AsyncCollection[dict[str, Any]]) -> None:
        """Apply this index specification to a collection.

        Args:
            collection: The MongoDB collection to create the index on.
        """
        kwargs: dict[str, Any] = {}
        if self.unique:
            kwargs["unique"] = True
        if self.expire_after_seconds is not None:
            kwargs["expireAfterSeconds"] = self.expire_after_seconds

        await collection.create_index(self.keys, **kwargs)


class UpdateResult(BaseModel):
    """Result of an update operation."""

    modified_count: int
    """Number of documents modified."""

    upserted_id: Any | None = None
    """ID of upserted document, if any."""


class IndexedCollection:
    """A MongoDB collection wrapper with automatic index management.

    IndexedCollection wraps an AsyncCollection and handles:
    - Lazy index creation (indexes created on first use)
    - Common query patterns (find one, find many, aggregation)
    - Insert/update/delete operations

    This class is used by storage backends to separate concerns:
    - The backend handles type conversion (via representations)
    - IndexedCollection handles MongoDB operations and indexing

    Example:
        >>> collection = IndexedCollection(
        ...     config.events,
        ...     indexes=[
        ...         IndexSpec(
        ...             keys=[("aggregate_id", 1), ("sequence_number", 1)],
        ...             unique=True,
        ...         ),
        ...         IndexSpec(keys=[("aggregate_id", 1)]),
        ...     ]
        ... )
        >>>
        >>> # Indexes are created on first operation
        >>> await collection.insert_one(doc)
        >>> async for doc in collection.find({"aggregate_id": "..."}):
        ...     print(doc)
    """

    def __init__(
        self,
        collection: AsyncCollection[dict[str, Any]],
        indexes: list["IndexSpec"] | None = None,
    ) -> None:
        """Initialize the indexed collection.

        Args:
            collection: The underlying MongoDB AsyncCollection.
            indexes: List of index specifications to create.
        """
        self._collection = collection
        self._indexes = indexes or []
        self._indexes_created = False

    async def ensure_indexes(self) -> None:
        """Create indexes if not already created.

        Called automatically by other methods, but can be called
        explicitly for eager initialization.
        """
        if self._indexes_created:
            return

        for spec in self._indexes:
            await spec.apply(self._collection)

        self._indexes_created = True

    # ========== Find Operations ==========

    async def find_one(
        self,
        filter: dict[str, Any],
        projection: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Find a single document matching the filter.

        Args:
            filter: MongoDB query filter.
            projection: Optional projection to limit returned fields.

        Returns:
            The matching document or None.
        """
        await self.ensure_indexes()
        result: dict[str, Any] | None = await self._collection.find_one(
            filter, projection=projection
        )
        return result

    async def find(
        self,
        filter: dict[str, Any],
        sort: list[tuple[str, int]] | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Find documents matching the filter.

        Args:
            filter: MongoDB query filter.
            sort: Optional list of (field, direction) tuples.
            limit: Optional maximum number of documents to return.

        Yields:
            Matching documents.
        """
        await self.ensure_indexes()

        cursor = self._collection.find(filter)

        if sort:
            cursor = cursor.sort(sort)
        if limit:
            cursor = cursor.limit(limit)

        async for doc in cursor:
            yield doc

    async def find_latest(
        self,
        filter: dict[str, Any],
        sort_field: str,
    ) -> dict[str, Any] | None:
        """Find the latest document by a sort field.

        Args:
            filter: MongoDB query filter.
            sort_field: Field to sort by descending.

        Returns:
            The latest matching document or None.
        """
        await self.ensure_indexes()

        cursor = (
            self._collection.find(filter).sort(sort_field, DESCENDING).limit(1)
        )

        async for doc in cursor:
            result: dict[str, Any] = doc
            return result
        return None

    # ========== Insert Operations ==========

    async def insert_one(self, document: dict[str, Any]) -> None:
        """Insert a single document.

        Args:
            document: The document to insert.
        """
        await self.ensure_indexes()
        await self._collection.insert_one(document)

    async def insert_many(
        self,
        documents: list[dict[str, Any]],
        ordered: bool = True,
    ) -> None:
        """Insert multiple documents.

        Args:
            documents: List of documents to insert.
            ordered: If True, stop on first error. If False, continue.
        """
        await self.ensure_indexes()
        await self._collection.insert_many(documents, ordered=ordered)

    # ========== Update Operations ==========

    async def update_one(
        self,
        filter: dict[str, Any],
        update: dict[str, Any],
        upsert: bool = False,
    ) -> "UpdateResult":
        """Update a single document.

        Args:
            filter: MongoDB query filter.
            update: Update operations (e.g., {"$set": {...}}).
            upsert: If True, insert if no matching document exists.

        Returns:
            UpdateResult with modified_count and upserted_id.
        """
        await self.ensure_indexes()
        result = await self._collection.update_one(
            filter, update, upsert=upsert
        )
        return UpdateResult(
            modified_count=result.modified_count,
            upserted_id=result.upserted_id,
        )

    async def replace_one(
        self,
        filter: dict[str, Any],
        replacement: dict[str, Any],
        upsert: bool = False,
    ) -> None:
        """Replace a single document.

        Args:
            filter: MongoDB query filter.
            replacement: The new document.
            upsert: If True, insert if no matching document exists.
        """
        await self.ensure_indexes()
        await self._collection.replace_one(filter, replacement, upsert=upsert)

    # ========== Delete Operations ==========

    async def delete_one(self, filter: dict[str, Any]) -> None:
        """Delete a single document.

        Args:
            filter: MongoDB query filter.
        """
        await self.ensure_indexes()
        await self._collection.delete_one(filter)

    # ========== Aggregation Operations ==========

    async def distinct_values(
        self,
        field: str,
        filter: dict[str, Any] | None = None,
    ) -> AsyncIterator[Any]:
        """Get distinct values for a field using aggregation pipeline.

        Uses aggregation instead of distinct() to avoid the 16MB size limit.

        Args:
            field: The field to get distinct values for.
            filter: Optional query filter.

        Yields:
            Distinct values.
        """
        await self.ensure_indexes()

        pipeline: list[dict[str, Any]] = []
        if filter:
            pipeline.append({"$match": filter})
        pipeline.append({"$group": {"_id": f"${field}"}})

        cursor = await self._collection.aggregate(pipeline)
        async for doc in cursor:
            yield doc["_id"]
