"""MongoDB implementation of IdempotencyStorageBackend."""

import contextlib
from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError

from interlock.application.middleware.idempotency import IdempotencyStorageBackend
from interlock.integrations.mongodb.collection import (
    IndexDirection,
    IndexedCollection,
    IndexSpec,
)
from interlock.integrations.mongodb.config import MongoConfiguration


def idempotency_ttl_index(ttl_seconds: int) -> IndexSpec:
    """Create a TTL index specification for idempotency keys.

    Args:
        ttl_seconds: Time-to-live in seconds for idempotency keys.

    Returns:
        IndexSpec configured with the TTL.
    """
    return IndexSpec(
        keys=[("created_at", IndexDirection.ASC)],
        expire_after_seconds=ttl_seconds,
    )


class MongoIdempotencyStorage(IdempotencyStorageBackend):
    """MongoDB-backed idempotency storage with TTL-based cleanup.

    Stores idempotency keys in MongoDB with a TTL index for automatic
    expiration. This prevents the collection from growing indefinitely
    while ensuring commands are not processed twice within the TTL window.

    Document schema:
        {
            "_id": "idempotency_key",
            "created_at": datetime
        }

    The TTL index on `created_at` automatically removes documents after
    the configured `idempotency_ttl_seconds` (default: 24 hours).

    Example:
        >>> from interlock.integrations.mongodb import (
        ...     MongoConfiguration, MongoIdempotencyStorage
        ... )
        >>>
        >>> # Configure with 1 hour TTL
        >>> config = MongoConfiguration(idempotency_ttl_seconds=3600)
        >>> storage = MongoIdempotencyStorage(config)
        >>>
        >>> # Check if command was already processed
        >>> if await storage.has_idempotency_key("cmd-123"):
        ...     print("Already processed")
        ... else:
        ...     # Process command...
        ...     await storage.store_idempotency_key("cmd-123")
    """

    def __init__(self, config: MongoConfiguration) -> None:
        """Initialize the MongoDB idempotency storage.

        Args:
            config: MongoDB configuration providing connection and TTL setting.
        """
        self._collection = IndexedCollection(
            config.idempotency_keys,
            indexes=[idempotency_ttl_index(config.idempotency_ttl_seconds)],
        )

    async def store_idempotency_key(self, key: str) -> None:
        """Store an idempotency key as processed.

        If the key already exists, this is a no-op (idempotent).

        Args:
            key: The idempotency key to store.
        """
        with contextlib.suppress(DuplicateKeyError):
            await self._collection.insert_one(
                {
                    "_id": key,
                    "created_at": datetime.now(tz=timezone.utc),
                }
            )

    async def has_idempotency_key(self, key: str) -> bool:
        """Check if an idempotency key has been processed.

        Args:
            key: The idempotency key to check.

        Returns:
            True if the key exists (command was processed), False otherwise.
        """
        doc = await self._collection.find_one({"_id": key}, projection={"_id": 1})
        return doc is not None
