from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import timedelta
from typing import TYPE_CHECKING, Optional

from ulid import ULID

if TYPE_CHECKING:
    from ....domain import Aggregate


class AggregateSnapshotStrategy(ABC):
    @staticmethod
    def never() -> "AggregateSnapshotStrategy":
        return NeverSnapshot()

    @abstractmethod
    def should_snapshot(self, aggregate: "Aggregate") -> bool:
        pass


class AggregateSnapshotStorageBackend(ABC):
    @staticmethod
    def null() -> "AggregateSnapshotStorageBackend":
        """A snapshot backend that does not store any snapshots."""
        return NullAggregateSnapshotStorageBackend()

    @abstractmethod
    async def save_snapshot(self, aggregate: "Aggregate") -> None:
        """Save a snapshot of the aggregate.

        Depending on the objectives of the implementer, you may choose to only store
        one copy of the aggregate as opposed to multiple versions. If you only want to
        store one copy, you should overwrite the previous snapshot. If you choose to store
        multiple versions, you should store each snapshot in such a way that the latest
        snapshot can be retrieved quickly as that will be the most common operation.

        Args:
            aggregate (Aggregate): The aggregate to save.

        Returns:
            None
        """
        pass

    @abstractmethod
    async def load_snapshot(
        self,
        aggregate_id: ULID,
        intended_version: int | None = None,
    ) -> Optional["Aggregate"]:
        """Load a snapshot of the aggregate.

        If intended_version is provided, the snapshot must be at most that version.
        Depending on the objectives of the implementer, you may choose to only store
        one copy of the aggregate as opposed to multiple versions. if this is the case,
        you should return the latest snapshot if the intended_version is greater than or equal
        to the version of the snapshot stored. If not, return None. The system is able to
        handle the case where the snapshot is not the intended version by replaying all
        events.

        If you choose to store multiple versions, you should return the latest snapshot
        that is less than or equal to the intended_version. If the intended_version is
        None, return the latest snapshot. If there is no snapshot, return None.

        Args:
            aggregate_id (ULID): The id of the aggregate to load.
            intended_version (Optional[int], optional): The intended version
                of the aggregate that is being loaded.

        Returns:
            Optional[Aggregate]: The aggregate snapshot if it exists, None otherwise.
        """
        pass

    @abstractmethod
    async def list_aggregate_ids_by_type(
        self, aggregate_type: type["Aggregate"]
    ) -> list[ULID]:
        """Get all aggregate IDs of a given type that have snapshots.

        This is used by catchup strategies to discover all aggregates of a
        particular type that need to be processed.

        Args:
            aggregate_type: The aggregate class type (e.g., User, Order)

        Returns:
            List of aggregate IDs that have snapshots for this type.
            Returns empty list if no snapshots exist for this type.

        Example:
            >>> from app.aggregates import User
            >>> user_ids = await snapshot_backend.list_aggregate_ids_by_type(User)
            >>> # [ULID('...'), ULID('...'), ...]
        """
        pass


class NeverSnapshot(AggregateSnapshotStrategy):
    def should_snapshot(self, _: "Aggregate") -> bool:
        return False


class SnapshotAfterN(AggregateSnapshotStrategy):
    def __init__(self, version_increment: int):
        self.version_increment = version_increment

    def should_snapshot(self, aggregate: "Aggregate") -> bool:
        return aggregate.version % self.version_increment == 0


class SnapshotAfterTime(AggregateSnapshotStrategy):
    def __init__(self, time_increment: timedelta):
        self.time_increment = time_increment

    def should_snapshot(self, aggregate: "Aggregate") -> bool:
        ideal_snapshot_time = aggregate.last_snapshot_time + self.time_increment
        return aggregate.last_event_time >= ideal_snapshot_time


class NullAggregateSnapshotStorageBackend(AggregateSnapshotStorageBackend):
    """A snapshot backend that does not store any snapshots."""

    async def save_snapshot(self, _: "Aggregate") -> None:
        pass

    async def load_snapshot(
        self,
        _: ULID,
        version: int | None = None,
    ) -> Optional["Aggregate"]:
        return None

    async def list_aggregate_ids_by_type(
        self, aggregate_type: type["Aggregate"]
    ) -> list[ULID]:
        """No snapshots stored, so return empty list."""
        return []


class InMemoryAggregateSnapshotStorageBackend(AggregateSnapshotStorageBackend):
    """A snapshot backend that stores snapshots in memory.

    This is not intended for production use. It is intended for testing purposes only.
    However, It does support multiple versions of the same aggregate. It goes without
    saying that this is neither or persistent nor performant.
    """

    def __init__(self) -> None:
        self.snapshots: dict[ULID, list[Aggregate]] = defaultdict(list)

    async def save_snapshot(self, aggregate: "Aggregate") -> None:
        self.snapshots[aggregate.id].append(aggregate)

    async def load_snapshot(
        self, aggregate_id: ULID, intended_version: int | None = None
    ) -> Optional["Aggregate"]:
        for snapshot in reversed(self.snapshots[aggregate_id]):
            if intended_version is None or snapshot.version <= intended_version:
                return snapshot
        return None

    async def list_aggregate_ids_by_type(
        self, aggregate_type: type["Aggregate"]
    ) -> list[ULID]:
        """List all aggregate IDs that have snapshots of the given type.

        Args:
            aggregate_type: The aggregate class to filter by

        Returns:
            List of aggregate IDs with snapshots of this type
        """
        result = []
        for aggregate_id, snapshot_list in self.snapshots.items():
            if snapshot_list and isinstance(snapshot_list[0], aggregate_type):
                result.append(aggregate_id)
        return result
