from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

from ulid import ULID

if TYPE_CHECKING:
    from ....domain import Aggregate


class AggregateCacheBackend(ABC):
    """Mechanism for caching aggregates.

    A cache backend is resposible for store and retrieve aggregates from a cache and
    can
    """

    @staticmethod
    def null() -> "AggregateCacheBackend":
        return NullAggregateCacheBackend()

    @abstractmethod
    def get_aggregate(self, aggregate_id: ULID) -> Optional["Aggregate"]:
        pass

    @abstractmethod
    def set_aggregate(self, aggregate: "Aggregate") -> None:
        pass

    @abstractmethod
    def remove_aggregate(self, aggregate_id: ULID) -> None:
        pass


class CacheStrategy(ABC):
    @staticmethod
    def never() -> "CacheStrategy":
        return NeverCache()

    @abstractmethod
    def should_cache(self, aggregate: "Aggregate") -> bool:
        pass


class NullAggregateCacheBackend(AggregateCacheBackend):
    def get_aggregate(self, _: ULID) -> Optional["Aggregate"]:
        return None

    def set_aggregate(self, _: "Aggregate") -> None:
        pass

    def remove_aggregate(self, _: ULID) -> None:
        pass


class AlwaysCache(CacheStrategy):
    def should_cache(self, _: "Aggregate") -> bool:
        return True


class NeverCache(CacheStrategy):
    def should_cache(self, _: "Aggregate") -> bool:
        return False
