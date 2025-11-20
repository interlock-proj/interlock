"""Aggregate pattern implementation for event sourcing."""

from .aggregate import Aggregate
from .exceptions import ConcurrencyError
from .repository import (
    AggregateCacheBackend,
    AggregateRepository,
    AggregateRepositoryRegistry,
    AggregateSnapshotStorageBackend,
    AggregateSnapshotStrategy,
    CacheStrategy,
    RepositoryConfig,
    RepositoryConfigRegistry,
)

__all__ = [
    "Aggregate",
    "AggregateRepository",
    "AggregateRepositoryRegistry",
    "AggregateCacheBackend",
    "CacheStrategy",
    "AggregateSnapshotStorageBackend",
    "AggregateSnapshotStrategy",
    "ConcurrencyError",
    "RepositoryConfig",
    "RepositoryConfigRegistry",
]
