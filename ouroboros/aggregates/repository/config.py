"""Configuration for aggregate repositories."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .cache import AggregateCacheBackend, CacheStrategy
from .snapshot import AggregateSnapshotStorageBackend, AggregateSnapshotStrategy

if TYPE_CHECKING:
    from ..aggregate import Aggregate


@dataclass
class RepositoryConfig:
    """Configuration for a single aggregate repository.

    This configuration determines caching and snapshotting behavior for
    an aggregate's repository. Each field has sensible defaults that
    disable caching and snapshotting (safe but not optimized).

    Attributes:
        cache_backend: Backend for caching aggregate instances in memory
        cache_strategy: Strategy determining when to cache aggregates
        snapshot_backend: Backend for storing aggregate snapshots
        snapshot_strategy: Strategy determining when to snapshot aggregates

    Examples:
        Default configuration (no caching, no snapshots):

        >>> config = RepositoryConfig()

        High-frequency read aggregate with caching:

        >>> config = RepositoryConfig(
        ...     cache_strategy=CacheStrategy.always(),
        ...     cache_backend=InMemoryCache()
        ... )

        Long-lived aggregate with periodic snapshots:

        >>> config = RepositoryConfig(
        ...     snapshot_strategy=AggregateSnapshotStrategy.every_n_events(50),
        ...     snapshot_backend=Neo4jSnapshotBackend(connection_manager)
        ... )

        Fully optimized configuration:

        >>> config = RepositoryConfig(
        ...     cache_backend=RedisCache(),
        ...     cache_strategy=CacheStrategy.always(),
        ...     snapshot_backend=Neo4jSnapshotBackend(connection_manager),
        ...     snapshot_strategy=AggregateSnapshotStrategy.every_n_events(10)
        ... )
    """

    cache_backend: AggregateCacheBackend = field(default_factory=AggregateCacheBackend.null)
    cache_strategy: CacheStrategy = field(default_factory=CacheStrategy.never)
    snapshot_backend: AggregateSnapshotStorageBackend = field(
        default_factory=AggregateSnapshotStorageBackend.null
    )
    snapshot_strategy: AggregateSnapshotStrategy = field(
        default_factory=AggregateSnapshotStrategy.never
    )


class RepositoryConfigRegistry:
    """Registry mapping aggregate types to repository configurations.

    This registry provides a centralized place to configure repository
    behavior on a per-aggregate-type basis. It supports:
    - Default configuration for all aggregates
    - Per-type overrides for specific aggregates

    The registry is registered with the DI container and resolved when
    creating repositories during application build.

    Examples:
        Create registry with defaults:

        >>> registry = RepositoryConfigRegistry()
        >>> registry.set_default(RepositoryConfig(
        ...     snapshot_strategy=AggregateSnapshotStrategy.every_n_events(100)
        ... ))

        Register per-type overrides:

        >>> registry.register(
        ...     BankAccount,
        ...     RepositoryConfig(
        ...         cache_strategy=CacheStrategy.always(),
        ...         snapshot_strategy=AggregateSnapshotStrategy.every_n_events(10)
        ...     )
        ... )

        Retrieve configuration:

        >>> config = registry.get(BankAccount)  # Returns override
        >>> config = registry.get(Order)  # Returns default
    """

    def __init__(self, default: RepositoryConfig | None = None):
        """Initialize registry with optional default configuration.

        Args:
            default: Default configuration for aggregates without overrides.
                If None, uses RepositoryConfig with framework defaults.
        """
        self._default = default or RepositoryConfig()
        self._overrides: dict[type[Aggregate], RepositoryConfig] = {}

    def set_default(self, config: RepositoryConfig) -> None:
        """Set the default configuration for all aggregates.

        Args:
            config: Configuration to use as default
        """
        self._default = config

    def register(self, aggregate_type: type["Aggregate"], config: RepositoryConfig) -> None:
        """Register configuration for a specific aggregate type.

        Args:
            aggregate_type: The aggregate type to configure
            config: Configuration specific to this aggregate type

        Examples:
            >>> registry.register(
            ...     BankAccount,
            ...     RepositoryConfig(cache_strategy=CacheStrategy.always())
            ... )
        """
        self._overrides[aggregate_type] = config

    def get(self, aggregate_type: type["Aggregate"]) -> RepositoryConfig:
        """Get configuration for an aggregate type.

        Returns the registered override if available, otherwise the default.

        Args:
            aggregate_type: The aggregate type to get configuration for

        Returns:
            Configuration for the specified aggregate type

        Examples:
            >>> config = registry.get(BankAccount)
        """
        return self._overrides.get(aggregate_type, self._default)
