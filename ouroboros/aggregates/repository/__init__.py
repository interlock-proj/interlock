"""Repository infrastructure for aggregate persistence and caching.

This package provides:
- AggregateRepository: Core repository for loading/saving aggregates
- AggregateRepositoryRegistry: Registry mapping aggregates to repositories
- Cache strategies and backends for aggregate caching
- Snapshot strategies and backends for aggregate snapshots
- Repository configuration and registry
"""

from .cache import AggregateCacheBackend, AlwaysCache, CacheStrategy, NeverCache
from .config import RepositoryConfig, RepositoryConfigRegistry
from .registry import AggregateRepositoryRegistry
from .repository import AggregateRepository
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
    "AggregateRepositoryRegistry",
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
    # Configuration
    "RepositoryConfig",
    "RepositoryConfigRegistry",
]
