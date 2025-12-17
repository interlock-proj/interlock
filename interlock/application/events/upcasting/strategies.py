from abc import ABC, abstractmethod


class UpcastingStrategy(ABC):
    """Strategy for when to apply upcasting transformations.

    Strategies control whether upcasting happens when events are read from
    storage, written to storage, or both. They also control whether upcasted
    events should be rewritten to the store for gradual migration.
    """

    @abstractmethod
    def should_upcast_on_read(self) -> bool:
        """Should events be upcasted when loaded from the event store?"""
        ...

    @abstractmethod
    def should_upcast_on_write(self) -> bool:
        """Should events be upcasted when saved to the event store?"""
        ...

    @abstractmethod
    def should_rewrite_on_load(self) -> bool:
        """Should upcasted events be persisted back to the event store?

        When True, events that are upcasted during load will be rewritten
        to the store with their new schema. This enables gradual migration
        of historical events as aggregates are accessed.

        Returns:
            True to rewrite upcasted events, False to leave them unchanged.
        """
        ...


class LazyUpcastingStrategy(UpcastingStrategy):
    """Lazy upcasting: transform events only when reading from storage.

    This is the recommended default strategy. Old events remain in storage
    with their original schema, and are transformed on-the-fly when loaded.

    Advantages:
    - No need to rewrite event store
    - Supports multiple concurrent versions
    - Can evolve upcasting logic over time
    - Preserves event immutability

    Disadvantages:
    - Slight performance cost on reads
    - Old schemas must remain in codebase forever
    """

    def should_upcast_on_read(self) -> bool:
        return True

    def should_upcast_on_write(self) -> bool:
        return False

    def should_rewrite_on_load(self) -> bool:
        return False


class EagerUpcastingStrategy(UpcastingStrategy):
    """Eager upcasting: transform and rewrite events for gradual migration.

    This strategy applies transformations when events are loaded AND when
    new events are saved. Crucially, it also rewrites upcasted events back
    to the store, enabling gradual migration as aggregates are accessed.

    Advantages:
    - Event store migrates to new schema over time
    - Eventually can remove old event types from codebase
    - No separate migration job needed

    Disadvantages:
    - Modifies historical events (breaks strict immutability)
    - Rarely-accessed aggregates may retain old events indefinitely
    - Slightly more I/O on reads (for rewriting)

    Use this when you have a clear migration timeline and want to eventually
    remove old event types from your codebase.
    """

    def should_upcast_on_read(self) -> bool:
        return True

    def should_upcast_on_write(self) -> bool:
        return True

    def should_rewrite_on_load(self) -> bool:
        return True
