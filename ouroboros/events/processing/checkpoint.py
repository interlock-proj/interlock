"""Checkpoint backend for tracking catchup progress and resumability."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from ulid import ULID


@dataclass
class Checkpoint:
    """Checkpoint data for tracking catchup progress.

    Used by catchup strategies to track which aggregates have been processed
    and resume from the correct position after crashes or restarts.

    Attributes:
        processor_name: Name of the processor (typically class name)
        processed_aggregate_ids: Set of aggregate IDs that have been fully processed
        max_timestamp: Latest event timestamp seen across all processed aggregates
        events_processed: Total number of events processed (for metrics/logging)

    Example:
        >>> checkpoint = Checkpoint(
        ...     processor_name="UserProfileProcessor",
        ...     processed_aggregate_ids={uuid1, uuid2, uuid3},
        ...     max_timestamp=datetime(2025, 1, 1),
        ...     events_processed=1500
        ... )
    """

    processor_name: str
    processed_aggregate_ids: set[ULID]
    max_timestamp: datetime
    events_processed: int


class CheckpointBackend(ABC):
    """Abstract interface for persisting catchup checkpoints.

    Checkpoints enable catchup strategies to be resumable - if a catchup
    operation crashes or is interrupted, it can resume from where it left off
    rather than starting over.

    Implementations should handle:
    - Atomic updates (checkpoint saves should be all-or-nothing)
    - Concurrency (multiple processors may checkpoint independently)
    - Persistence (checkpoints survive process restarts)
    """

    @abstractmethod
    async def load_checkpoint(self, processor_name: str) -> Checkpoint | None:
        """Load the latest checkpoint for a processor.

        Args:
            processor_name: Name of the processor to load checkpoint for

        Returns:
            The checkpoint if it exists, None if this is the first run
        """
        ...

    @abstractmethod
    async def save_checkpoint(self, checkpoint: Checkpoint) -> None:
        """Save a checkpoint for a processor.

        This should atomically replace any existing checkpoint for the
        same processor.

        Args:
            checkpoint: The checkpoint data to persist
        """
        ...


class InMemoryCheckpointBackend(CheckpointBackend):
    """In-memory checkpoint storage for testing.

    Stores checkpoints in a dictionary keyed by processor name.
    Not suitable for production use as checkpoints are lost on restart.
    """

    def __init__(self) -> None:
        """Initialize an empty in-memory checkpoint store."""
        self._checkpoints: dict[str, Checkpoint] = {}

    async def load_checkpoint(self, processor_name: str) -> Checkpoint | None:
        """Load checkpoint from in-memory dictionary.

        Args:
            processor_name: Name of the processor

        Returns:
            The checkpoint if it exists, None otherwise
        """
        return self._checkpoints.get(processor_name)

    async def save_checkpoint(self, checkpoint: Checkpoint) -> None:
        """Save checkpoint to in-memory dictionary.

        Args:
            checkpoint: The checkpoint to save
        """
        self._checkpoints[checkpoint.processor_name] = checkpoint
