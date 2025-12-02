from abc import ABC, abstractmethod
from asyncio import gather
from typing import Any, Generic, TypeVar, get_args

from pydantic import BaseModel

from ....domain import Event
from .strategies import UpcastingStrategy

T = TypeVar("T", bound=BaseModel)
U = TypeVar("U", bound=BaseModel)


def extract_upcaster_types(
    upcaster_class: type,
) -> tuple[type[BaseModel], type[BaseModel]]:
    """Extract source and target event types from an EventUpcaster subclass.

    Introspects the generic type parameters of EventUpcaster[T, U] to determine
    which event types this upcaster transforms.

    Args:
        upcaster_class: The EventUpcaster subclass to introspect

    Returns:
        Tuple of (source_type, target_type)

    Raises:
        ValueError: If type parameters cannot be extracted

    Example:
        >>> class MyUpcaster(EventUpcaster[OldEvent, NewEvent]):
        ...     pass
        >>> extract_upcaster_types(MyUpcaster)
        (<class 'OldEvent'>, <class 'NewEvent'>)
    """
    # Look for __orig_bases__ which contains the generic parent with type parameters
    if not hasattr(upcaster_class, "__orig_bases__"):
        raise ValueError(
            f"Cannot extract types from {upcaster_class.__name__}: no __orig_bases__ found"
        )

    for base in upcaster_class.__orig_bases__:
        # Check if this base is EventUpcaster or a subclass of it
        origin = getattr(base, "__origin__", None)
        if origin is not None:
            # It's a generic type - check if it's EventUpcaster
            try:
                if issubclass(origin, EventUpcaster):
                    args = get_args(base)
                    if len(args) == 2:
                        return (args[0], args[1])
            except TypeError:
                # origin is not a class
                continue

    raise ValueError(
        f"Cannot extract types from {upcaster_class.__name__}: "
        f"must inherit from EventUpcaster[SourceType, TargetType]"
    )


class EventUpcaster(Generic[T, U], ABC):
    """Base class for transforming events from one schema version to another.

    Event upcasters handle schema evolution by transforming old event data models
    into new ones. Each upcaster is typed with source and target event types.

    The framework automatically extracts these types via introspection, so you
    only need to implement the upcast_payload method.

    Example:
        >>> class OrderPlacedV1(BaseModel):
        ...     product: str
        ...     price: float
        ...
        >>> class OrderPlacedV2(BaseModel):
        ...     product_id: str
        ...     price_cents: int
        ...
        >>> class OrderPlacedV1ToV2(EventUpcaster[OrderPlacedV1, OrderPlacedV2]):
        ...     def upcast_payload(self, data: OrderPlacedV1) -> OrderPlacedV2:
        ...         return OrderPlacedV2(
        ...             product_id=data.product,
        ...             price_cents=int(data.price * 100)
        ...         )
    """

    async def upcast_event(self, event: Event[T]) -> Event[U]:
        """Transform an entire event from old schema to new schema.

        This method preserves event metadata (id, aggregate_id, sequence_number,
        timestamp) while transforming the event data payload.

        Args:
            event: The event with old schema data

        Returns:
            A new event with transformed data
        """
        return Event(
            id=event.id,
            aggregate_id=event.aggregate_id,
            sequence_number=event.sequence_number,
            timestamp=event.timestamp,
            data=await self.upcast_payload(event.data),
        )

    async def can_upcast(self, event: Event[T]) -> bool:
        """Check if this upcaster can handle the given event.

        Override this method if you need conditional upcasting logic
        (e.g., only upcast events before a certain date).

        Args:
            event: The event to check

        Returns:
            True if this upcaster can transform the event
        """
        return True

    @abstractmethod
    async def upcast_payload(self, data: T) -> U:
        """Transform event data from old schema to new schema.

        This is the core transformation logic that subclasses must implement.

        Args:
            data: The old event data

        Returns:
            The transformed event data with new schema
        """
        ...


class UpcasterMap:
    @staticmethod
    def from_upcasters(upcasters: list[EventUpcaster[Any, Any]]) -> "UpcasterMap":
        map = UpcasterMap()
        for upcaster in upcasters:
            # Skip abstract base classes or types without proper generic info
            if type(upcaster).__name__ in ('ABCMeta', 'type'):
                continue
            map.register_upcaster(upcaster)
        return map

    def __init__(self):
        self.upcasters: dict[type[BaseModel], list[EventUpcaster[Any, Any]]] = {}

    def register_upcaster(self, upcaster: EventUpcaster[Any, Any]):
        source_type, _ = extract_upcaster_types(type(upcaster))
        if source_type not in self.upcasters:
            self.upcasters[source_type] = []
        self.upcasters[source_type].append(upcaster)

    def get_upcasters(
        self, source_type: type[BaseModel]
    ) -> list[EventUpcaster[Any, Any]]:
        return self.upcasters.get(source_type, [])


class UpcastingPipeline:
    """Pipeline for applying event upcasting transformations.

    The pipeline manages a mapping of upcasters and applies them to events
    based on the configured strategy. It supports multi-step upcasting chains
    where events can be transformed through multiple versions (V1→V2→V3).
    """

    def __init__(
        self, upcasting_strategy: UpcastingStrategy, upcaster_map: UpcasterMap
    ):
        self.upcasting_strategy = upcasting_strategy
        self.upcaster_map = upcaster_map

    async def upcast(self, event: Event[Any]) -> Event[Any]:
        """Apply upcasting transformations to a single event.

        Looks up upcasters registered for the event's data type and applies
        the first matching upcaster. For multi-step chains, call repeatedly.

        Args:
            event: The event to upcast

        Returns:
            The upcasted event, or the original if no upcaster found
        """
        event_data_type = type(event.data)

        # Find upcasters for this event type
        for upcaster in self.upcaster_map.get_upcasters(event_data_type):
            if await upcaster.can_upcast(event):
                return await upcaster.upcast_event(event)

        # No upcaster found - return unchanged
        return event

    async def upcast_chain(self, event: Event[Any], max_steps: int = 10) -> Event[Any]:
        """Apply upcasting transformations repeatedly until no more upcasters match.

        This enables multi-step chains like V1→V2→V3 by repeatedly applying
        upcasters until the event reaches its final form.

        Args:
            event: The event to upcast
            max_steps: Maximum number of upcasting steps (prevents infinite loops)

        Returns:
            The fully upcasted event

        Raises:
            RuntimeError: If max_steps is exceeded
        """
        for _step in range(max_steps):
            event_data_type = type(event.data)
            upcasted = await self.upcast(event)

            # If type didn't change, we're done
            if type(upcasted.data) is event_data_type:
                return upcasted

            event = upcasted

        raise RuntimeError(
            f"Upcasting exceeded max steps ({max_steps}). "
            f"Possible circular upcasting chain for {type(event.data).__name__}"
        )

    async def read_upcast(self, events: list[Event[Any]]) -> list[Event[Any]]:
        """Upcast events loaded from the event store according to the strategy.

        Args:
            events: Events loaded from storage

        Returns:
            Upcasted events if strategy permits, otherwise original events
        """
        if self.upcasting_strategy.should_upcast_on_read():
            return list(await gather(*[self.upcast_chain(event) for event in events]))
        return events

    async def write_upcast(self, events: list[Event[Any]]) -> list[Event[Any]]:
        """Upcast events being saved to the event store according to the strategy.

        Args:
            events: Events being saved to storage

        Returns:
            Upcasted events if strategy permits, otherwise original events
        """
        if self.upcasting_strategy.should_upcast_on_write():
            return list(await gather(*[self.upcast_chain(event) for event in events]))
        return events
