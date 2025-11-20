from abc import ABC, abstractmethod
from asyncio import gather
from collections import defaultdict
from typing import Any, Generic, TypeVar, get_args

from pydantic import BaseModel

from ..event import Event
from .config import UpcastingConfig
from .registry import UpcastingRegistry
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


class UpcastingPipeline:
    """Pipeline for applying event upcasting transformations.

    The pipeline manages a registry of upcasters and applies them to events
    based on the configured strategy. It supports multi-step upcasting chains
    where events can be transformed through multiple versions (V1→V2→V3).
    """

    def __init__(self, upcasting_strategy: UpcastingStrategy):
        """Initialize the upcasting pipeline.

        Args:
            upcasting_strategy: Strategy controlling when to apply upcasting
        """
        self.upcasting_strategy = upcasting_strategy
        # Map from source event type to list of upcasters that can transform it
        self.upcasters: dict[type[BaseModel], list[EventUpcaster[Any, Any]]] = defaultdict(list)

    def register_upcaster(
        self,
        upcaster: EventUpcaster[T, U] | type[EventUpcaster[T, U]],
        source_type: type[T] | None = None,
        target_type: type[U] | None = None,
    ) -> None:
        """Register an upcaster with the pipeline.

        The source and target types are automatically extracted from the upcaster's
        generic type parameters if not provided explicitly.

        Args:
            upcaster: The upcaster instance or class to register
            source_type: Optional explicit source type (auto-detected if None)
            target_type: Optional explicit target type (auto-detected if None)

        Raises:
            ValueError: If types cannot be extracted from the upcaster

        Example:
            >>> pipeline.register_upcaster(MyUpcaster())  # Types auto-detected
            >>> pipeline.register_upcaster(MyUpcaster, OldEvent, NewEvent)  # Explicit
        """
        # Instantiate if we got a class
        if isinstance(upcaster, type):
            upcaster = upcaster()

        # Extract types if not provided
        if source_type is None or target_type is None:
            detected_source, detected_target = extract_upcaster_types(type(upcaster))
            source_type = source_type or detected_source
            target_type = target_type or detected_target

        # Register keyed by source type
        self.upcasters[source_type].append(upcaster)

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
        for upcaster in self.upcasters.get(event_data_type, []):
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

    @classmethod
    def create_from_registry(
        cls, config: UpcastingConfig, registry: UpcastingRegistry
    ) -> "UpcastingPipeline":
        """Factory method for creating UpcastingPipeline from registry.

        Creates pipeline with configured strategy and registers all upcasters
        from the registry. Dependencies are injected by the DI container.

        Args:
            config: Upcasting configuration (contains strategy)
            registry: Registry containing registered upcasters

        Returns:
            Configured UpcastingPipeline instance

        Examples:
            This method is registered with the DI container and called automatically:

            >>> container.register(UpcastingPipeline, UpcastingPipeline.create_from_registry)
            >>> pipeline = container.resolve(UpcastingPipeline)
        """
        # Create pipeline with configured strategy
        pipeline = cls(config.strategy)

        # Register all upcasters from registry (types resolved via DI)
        for upcaster in registry.resolve_all():
            pipeline.register_upcaster(upcaster)

        return pipeline
