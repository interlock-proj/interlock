"""Repository infrastructure for aggregate persistence and caching.

This package provides:
- AggregateRepository: Core repository for loading/saving aggregates
- Cache strategies and backends for aggregate caching
- Snapshot strategies and backends for aggregate snapshots
"""

from .cache import AggregateCacheBackend, AlwaysCache, CacheStrategy, NeverCache
from .repository import AggregateFactory, AggregateRepository
from .snapshot import (
    AggregateSnapshotStorageBackend,
    AggregateSnapshotStrategy,
    InMemoryAggregateSnapshotStorageBackend,
    NeverSnapshot,
    SnapshotAfterN,
    SnapshotAfterTime,
)

__all__ = [
    # Core repository
    "AggregateRepository",
    "AggregateFactory",
    # Cache infrastructure
    "AggregateCacheBackend",
    "CacheStrategy",
    "AlwaysCache",
    "NeverCache",
    # Snapshot infrastructure
    "AggregateSnapshotStorageBackend",
    "AggregateSnapshotStrategy",
    "NeverSnapshot",
    "SnapshotAfterN",
    "SnapshotAfterTime",
    "InMemoryAggregateSnapshotStorageBackend",
]
