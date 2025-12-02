"""MongoDB implementation of IdempotencyStorageBackend for command deduplication.

This module provides a MongoDB-backed idempotency store implementation using
PyMongo's async API with TTL indexes for automatic key expiration.
"""

from contextlib import suppress
from datetime import datetime

from interlock.application.commands.middleware.idempotency import (
    IdempotencyStorageBackend,
    IdempotencyTrackedCommand,
)

from .connection import MongoDBConnectionManager


class MongoDBIdempotencyBackend(IdempotencyStorageBackend):
    """MongoDB implementation of the IdempotencyStorageBackend interface.

    This implementation uses MongoDB to store idempotency keys with:
    - Unique index on idempotency_key for duplicate detection
    - TTL index on created_at for automatic expiration
    - Simple insert/find operations for high performance

    Collections:
        - idempotency_keys: Stores processed command idempotency keys

    Document structure:
        {
            "_id": ObjectId(),
            "idempotency_key": "unique-key-string",
            "created_at": ISODate(...)
        }

    Examples:
        >>> config = MongoDBConfig(uri="mongodb://localhost:27017")
        >>> manager = MongoDBConnectionManager(config)
        >>> backend = MongoDBIdempotencyBackend(manager, ttl_seconds=86400)
        >>> await backend.initialize_schema()
        >>>
        >>> # Store processed command
        >>> await backend.store_processed_command(command)
        >>>
        >>> # Check if command was processed
        >>> was_processed = await backend.has_processed_command(command)
    """

    def __init__(self, connection_manager: MongoDBConnectionManager, ttl_seconds: int = 86400):
        """Initialize the MongoDB idempotency backend.

        Args:
            connection_manager: MongoDB connection manager
            ttl_seconds: Time-to-live for idempotency keys in seconds (default: 86400 = 24 hours)
        """
        self.connection_manager = connection_manager
        self.ttl_seconds = ttl_seconds

    @property
    def _idempotency_keys_collection(self):
        """Get the idempotency keys collection."""
        return self.connection_manager.database["idempotency_keys"]

    async def initialize_schema(self) -> None:
        """Create necessary indexes for idempotency storage.

        Creates:
            - Unique index on idempotency_key for duplicate detection
            - TTL index on created_at for automatic expiration

        Examples:
            >>> await backend.initialize_schema()
        """
        # Unique index on idempotency_key
        await self._idempotency_keys_collection.create_index([("idempotency_key", 1)], unique=True)

        # TTL index for automatic expiration
        await self._idempotency_keys_collection.create_index(
            [("created_at", 1)], expireAfterSeconds=self.ttl_seconds
        )

    async def store_processed_command(self, command: IdempotencyTrackedCommand) -> None:
        """Store the command as processed.

        Args:
            command: The command that has been processed

        Examples:
            >>> await backend.store_processed_command(my_command)
        """
        doc = {
            "idempotency_key": command.idempotency_key,
            "created_at": datetime.utcnow(),
        }

        # Use insert_one with error handling for duplicate key (idempotent operation)
        # Duplicate key error - command already processed
        # This is acceptable in concurrent scenarios
        with suppress(Exception):
            await self._idempotency_keys_collection.insert_one(doc)

    async def has_processed_command(self, command: IdempotencyTrackedCommand) -> bool:
        """Check if the command has been processed.

        Args:
            command: The command to check

        Returns:
            True if command was processed, False otherwise

        Examples:
            >>> if await backend.has_processed_command(my_command):
            ...     print("Command already processed")
        """
        doc = await self._idempotency_keys_collection.find_one(
            {"idempotency_key": command.idempotency_key}
        )
        return doc is not None
