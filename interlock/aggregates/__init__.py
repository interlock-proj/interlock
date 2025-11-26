"""Aggregate pattern implementation for event sourcing."""

from .aggregate import Aggregate
from .exceptions import ConcurrencyError
from .repository import (
    AggregateCacheBackend,
    AggregateFactory,
    AggregateRepository,
    AggregateSnapshotStorageBackend,
    AggregateSnapshotStrategy,
    CacheStrategy,
)

__all__ = [
    "Aggregate",
    "AggregateRepository",
    "AggregateFactory",
    "AggregateCacheBackend",
    "CacheStrategy",
    "AggregateSnapshotStorageBackend",
    "AggregateSnapshotStrategy",
    "ConcurrencyError",
]
