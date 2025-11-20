from abc import ABC, abstractmethod


class UpcastingStrategy(ABC):
    """Strategy for when to apply upcasting transformations.

    Strategies control whether upcasting happens when events are read from
    storage, written to storage, or both.
    """

    @abstractmethod
    def should_upcast_on_read(self) -> bool:
        """Should events be upcasted when loaded from the event store?"""
        ...

    @abstractmethod
    def should_upcast_on_write(self) -> bool:
        """Should events be upcasted when saved to the event store?"""
        ...


class LazyUpcastingStrategy(UpcastingStrategy):
    """Lazy upcasting: transform events only when reading from storage.

    This is the recommended default strategy. Old events remain in storage
    with their original schema, and are transformed on-the-fly when loaded.

    Advantages:
    - No need to rewrite event store
    - Supports multiple concurrent versions
    - Can evolve upcasting logic over time

    Disadvantages:
    - Slight performance cost on reads
    - Old schemas must remain in codebase
    """

    def should_upcast_on_read(self) -> bool:
        return True

    def should_upcast_on_write(self) -> bool:
        return False


class EagerUpcastingStrategy(UpcastingStrategy):
    """Eager upcasting: transform events on both read and write.

    This strategy applies transformations when events are loaded AND when
    new events are saved, gradually migrating the event store to new schemas.

    Advantages:
    - Event store migrates to new schema over time
    - Eventually can remove old event types

    Disadvantages:
    - Modifies historical events
    - May conflict with event immutability principles
    - Requires careful handling of sequence numbers
    """

    def should_upcast_on_read(self) -> bool:
        return True

    def should_upcast_on_write(self) -> bool:
        return True
