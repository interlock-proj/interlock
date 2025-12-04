from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

from ulid import ULID

if TYPE_CHECKING:
    from ....domain import Aggregate


class AggregateCacheBackend(ABC):
    """Mechanism for caching aggregates.

    A cache backend is resposible for store and retrieve aggregates from a
    cache. All operations are async to support I/O-bound cache backends like
    Redis or Memcached.
    """

    @staticmethod
    def null() -> "AggregateCacheBackend":
        return NullAggregateCacheBackend()

    @abstractmethod
    async def get_aggregate(
        self, aggregate_id: ULID
    ) -> Optional["Aggregate"]:
        ...

    @abstractmethod
    async def set_aggregate(self, aggregate: "Aggregate") -> None:
        ...

    @abstractmethod
    async def remove_aggregate(self, aggregate_id: ULID) -> None:
        ...


class CacheStrategy(ABC):
    @staticmethod
    def never() -> "CacheStrategy":
        return NeverCache()

    @abstractmethod
    def should_cache(self, aggregate: "Aggregate") -> bool:
        ...


class NullAggregateCacheBackend(AggregateCacheBackend):
    async def get_aggregate(self, _: ULID) -> Optional["Aggregate"]:
        return None

    async def set_aggregate(self, _: "Aggregate") -> None:
        pass

    async def remove_aggregate(self, _: ULID) -> None:
        pass


class AlwaysCache(CacheStrategy):
    def should_cache(self, _: "Aggregate") -> bool:
        return True


class NeverCache(CacheStrategy):
    def should_cache(self, _: "Aggregate") -> bool:
        return False
