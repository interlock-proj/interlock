"""MongoDB implementation of CheckpointBackend for resumable catchup operations.

This module provides a MongoDB-backed checkpoint store implementation using
PyMongo's async API for persisting event processor catchup progress.
"""

from datetime import datetime

from ulid import ULID

from ouroboros.events.processing.checkpoint import Checkpoint, CheckpointBackend

from .connection import MongoDBConnectionManager


class MongoDBCheckpointBackend(CheckpointBackend):
    """MongoDB implementation of the CheckpointBackend interface.

    This implementation uses MongoDB to store catchup checkpoints with:
    - Unique index on processor_name for fast lookup
    - Atomic replace_one with upsert for checkpoint updates
    - Array storage for processed_aggregate_ids

    Collections:
        - checkpoints: Stores event processor checkpoint documents

    Document structure:
        {
            "_id": ObjectId(),
            "processor_name": "ProcessorClassName",
            "processed_aggregate_ids": ["uuid1", "uuid2", ...],
            "max_timestamp": ISODate(...),
            "events_processed": 1000,
            "updated_at": ISODate(...)
        }

    Examples:
        >>> config = MongoDBConfig(uri="mongodb://localhost:27017")
        >>> manager = MongoDBConnectionManager(config)
        >>> backend = MongoDBCheckpointBackend(manager)
        >>> await backend.initialize_schema()
        >>>
        >>> # Load checkpoint
        >>> checkpoint = await backend.load_checkpoint("MyProcessor")
        >>>
        >>> # Save checkpoint
        >>> checkpoint.events_processed += 100
        >>> await backend.save_checkpoint(checkpoint)
    """

    def __init__(self, connection_manager: MongoDBConnectionManager):
        """Initialize the MongoDB checkpoint backend.

        Args:
            connection_manager: MongoDB connection manager
        """
        self.connection_manager = connection_manager

    @property
    def _checkpoints_collection(self):
        """Get the checkpoints collection."""
        return self.connection_manager.database["checkpoints"]

    async def initialize_schema(self) -> None:
        """Create necessary indexes for checkpoint storage.

        Creates:
            - Unique index on processor_name for fast lookup and uniqueness

        Examples:
            >>> await backend.initialize_schema()
        """
        await self._checkpoints_collection.create_index([("processor_name", 1)], unique=True)

    async def load_checkpoint(self, processor_name: str) -> Checkpoint | None:
        """Load the latest checkpoint for a processor.

        Args:
            processor_name: Name of the processor to load checkpoint for

        Returns:
            The checkpoint if it exists, None if this is the first run

        Examples:
            >>> checkpoint = await backend.load_checkpoint("OrderProjector")
            >>> if checkpoint:
            ...     print(f"Processed {checkpoint.events_processed} events")
        """
        doc = await self._checkpoints_collection.find_one({"processor_name": processor_name})

        if not doc:
            return None

        # Convert ULID strings back to ULID objects
        processed_aggregate_ids = {
            ULID.from_str(agg_id) for agg_id in doc["processed_aggregate_ids"]
        }

        return Checkpoint(
            processor_name=doc["processor_name"],
            processed_aggregate_ids=processed_aggregate_ids,
            max_timestamp=doc["max_timestamp"],
            events_processed=doc["events_processed"],
        )

    async def save_checkpoint(self, checkpoint: Checkpoint) -> None:
        """Save a checkpoint for a processor.

        This atomically replaces any existing checkpoint for the same processor.

        Args:
            checkpoint: The checkpoint data to persist

        Examples:
            >>> checkpoint = Checkpoint(
            ...     processor_name="OrderProjector",
            ...     processed_aggregate_ids={uuid1, uuid2},
            ...     max_timestamp=datetime.now(),
            ...     events_processed=500
            ... )
            >>> await backend.save_checkpoint(checkpoint)
        """
        # Convert UUID objects to strings for storage
        processed_aggregate_ids_str = [str(agg_id) for agg_id in checkpoint.processed_aggregate_ids]

        doc = {
            "processor_name": checkpoint.processor_name,
            "processed_aggregate_ids": processed_aggregate_ids_str,
            "max_timestamp": checkpoint.max_timestamp,
            "events_processed": checkpoint.events_processed,
            "updated_at": datetime.utcnow(),
        }

        # Atomically replace existing checkpoint
        await self._checkpoints_collection.replace_one(
            {"processor_name": checkpoint.processor_name}, doc, upsert=True
        )
