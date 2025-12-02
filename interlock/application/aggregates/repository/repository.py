from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Generic, TypeVar

from ulid import ULID

from ....domain.exceptions import ConcurrencyError
from ...events import EventBus
from .cache import AggregateCacheBackend, CacheStrategy
from .snapshot import AggregateSnapshotStorageBackend, AggregateSnapshotStrategy

if TYPE_CHECKING:
    from ....domain import Aggregate

A = TypeVar("A", bound="Aggregate")


class AggregateFactory(Generic[A]):
    """Factory for creating aggregate instances of a specific type."""
    
    def __init__(self, aggregate_type: type[A]):
        self._aggregate_type = aggregate_type
    
    def get_type(self) -> type[A]:
        """Get the aggregate type this factory produces."""
        return self._aggregate_type
    
    def create(self, aggregate_id: ULID) -> A:
        """Create a new aggregate instance with the given ID."""
        return self._aggregate_type(id=aggregate_id)


class AggregateRepository(Generic[A]):
    """A mechanism for loading and saving aggregates in a consistent way.

    The aggregate repository only has one main public method, `acquire`.
    This encapsulates the entire lifecycle of an aggregate and performs
    the saving and loading of the aggregate from the event store.
    """

    # In practice, AggregateRepository itself contains very few details about the
    # saving and loading of aggregates. The main job of the repository is to act
    # as a mediator between the various strategies and backends that decide what
    # to do and when to do it. This allows for a lot of flexibility in how aggregates
    # are loaded and saved while still providing a consistent interface for working
    # with them.

    __slots__ = (
        "aggregate_type",
        "event_bus",
        "snapshot_strategy",
        "cache_strategy",
        "snapshot_backend",
        "cache_backend",
    )

    def __init__(
        self,
        aggregate_factory: AggregateFactory[A],
        event_bus: EventBus,
        snapshot_strategy: AggregateSnapshotStrategy,
        cache_strategy: CacheStrategy,
        snapshot_backend: AggregateSnapshotStorageBackend,
        cache_backend: AggregateCacheBackend,
    ):
        self.aggregate_type = aggregate_factory.get_type()
        self.event_bus = event_bus
        self.snapshot_strategy = snapshot_strategy
        self.cache_strategy = cache_strategy
        self.cache_backend = cache_backend
        self.snapshot_backend = snapshot_backend

    async def list_all_ids(self) -> list[ULID]:
        """Get all aggregate IDs of this repository's type.

        This queries the snapshot backend for all aggregates of the repository's
        type that have snapshots. It's primarily used by catchup strategies to
        discover which aggregates need to be processed.

        Returns:
            List of aggregate IDs of this repository's type.
            Returns empty list if no snapshots exist.

        Example:
            >>> user_repository = AggregateRepository[User](...)
            >>> user_ids = await user_repository.list_all_ids()
            >>> # [ULID('...'), ULID('...'), ...]
        """
        return await self.snapshot_backend.list_aggregate_ids_by_type(self.aggregate_type)

    @asynccontextmanager
    async def acquire(self, aggregate_id: ULID) -> AsyncIterator[A]:
        aggregate = await self._load_aggregate(aggregate_id)
        original_version = aggregate.version

        try:
            yield aggregate
        except Exception:
            # On error, clear uncommitted events to prevent partial state from being saved
            aggregate.clear_uncommitted_events()
            raise

        # We only need to save the aggregate if it has changed in some way.
        if aggregate.changed_since(original_version):
            await self._save_aggregate(aggregate, original_version)

    async def _load_aggregate(self, aggregate_id: ULID) -> A:
        # (Low Cost) First, we will check the cache to see if the
        # aggregate is already loaded.
        if cached := self.cache_backend.get_aggregate(aggregate_id):
            return cached  # type: ignore[return-value]

        # (Medium Cost) Second, we will check the snapshot store to see if we have a snapshot.
        if snapshot := await self.snapshot_backend.load_snapshot(aggregate_id):
            aggregate: A = snapshot  # type: ignore[assignment]
        else:
            aggregate = self.aggregate_type(id=aggregate_id)

        # (High Cost) Third, we will load all events that have occurred since the snapshot.
        # If there is no snapshot, we will load all events since the aggregate was created.
        full_events = await self.event_bus.load_events(aggregate_id, aggregate.version + 1)

        # Replay events to rebuild state
        aggregate.replay_events([event.data for event in full_events])

        # Update version and last_event_time from the most recent event
        if full_events:
            aggregate.version = full_events[-1].sequence_number
            aggregate.last_event_time = full_events[-1].timestamp

        return aggregate

    async def _save_aggregate(self, aggregate: A, expected_version: int) -> None:
        # If there are no uncommitted events, we likely don't need to do anything.
        # This can happen if the aggregate was loaded from a snapshot and no events
        # were created by the handling of a command.
        # However, we may choose to cache the aggregate in this case as its a
        # high read scenario likely of some form.
        if not (uncommitted_events := aggregate.get_uncommitted_events()):
            if self.cache_strategy.should_cache(aggregate):
                self.cache_backend.set_aggregate(aggregate)
            return

        # Publish the events to the event bus. If the publish fails due to a concurrency
        # exception, the write has failed due to a race on the aggregate.
        # Almost inherently, the cache needs to be invalidated.
        # So we remove cache and then raise the exception. Other exceptions means that
        # the write was not successful so we will throw exceptions out.
        try:
            await self.event_bus.publish_events(uncommitted_events, expected_version)
            aggregate.clear_uncommitted_events()
        except ConcurrencyError:
            self.cache_backend.remove_aggregate(aggregate.id)
            raise

        # If we have succeeded in snapshotting and publishing the events, we can
        # snapshot the aggregate if the snapshot strategy indicates we should.
        # We also update the last snapshot time.
        if self.snapshot_strategy.should_snapshot(aggregate):
            aggregate.mark_snapshot()
            await self.snapshot_backend.save_snapshot(aggregate)
