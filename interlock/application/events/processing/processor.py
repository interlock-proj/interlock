"""Event processors for building read models and handling side effects.

This module provides the infrastructure for implementing the read side of CQRS:
- EventProcessor: Base class for handling events and building read models
- CatchupStrategy: Strategies for catching up with the event store
- CatchupCondition: Conditions for triggering catchup operations
- EventProcessorExecutor: Runtime execution engine for processors
"""

import inspect
from typing import TYPE_CHECKING, ClassVar

from pydantic import BaseModel

from ....routing import setup_event_handling

if TYPE_CHECKING:
    from ....routing import MessageRouter


class EventProcessor:
    """Base class for building read models and handling events (CQRS read side).

    EventProcessors consume events from the event bus and use them to:
    1. **Build read models** - Denormalized views optimized for queries
    2. **Execute side effects** - Send emails, update search indexes, etc.
    3. **Coordinate sagas** - Multi-step business processes

    In CQRS, processors are the read side that react to events published
    by the write side (aggregates). They ensure eventual consistency between
    the write model and read models.

    **How it works:**
    Subclass EventProcessor and use the @handles_event decorator to declare
    which events the processor is interested in. interlock automatically:
    - Sets up event routing based on type annotations
    - Dispatches events to the appropriate handler methods
    - Manages subscriptions and delivery

    **Event Routing:**
    The @handles_event decorator uses type annotations to determine routing:
    - Handler parameter type declares which event to handle
    - Multiple handlers can be defined for different event types
    - Routing is set up automatically during class definition

    **Execution:**
    Processors run via EventProcessorExecutor, which:
    - Subscribes to the event stream
    - Batches events for efficiency
    - Monitors lag and triggers catchup when needed
    - Handles errors and retries

    Attributes:
        _event_router: Class-level routing table (set by __init_subclass__)

    Example:
        >>> from interlock.routing import handles_event
        >>>
        >>> class OrderPlaced(BaseModel):
        ...     order_id: str
        ...     customer_email: str
        ...     total_amount: float
        >>>
        >>> class OrderCancelled(BaseModel):
        ...     order_id: str
        ...     reason: str
        >>>
        >>> class EmailNotificationProcessor(EventProcessor):
        ...     '''Send emails when orders are placed or cancelled.'''
        ...
        ...     @handles_event
        ...     async def on_order_placed(self, event: OrderPlaced) -> None:
        ...         await self.send_email(
        ...             event.customer_email,
        ...             f"Order confirmed! Total: ${event.total_amount}"
        ...         )
        ...
        ...     @handles_event
        ...     async def on_order_cancelled(self, event: OrderCancelled) -> None:
        ...         await self.send_email(
        ...             event.customer_email,
        ...             f"Order cancelled: {event.reason}"
        ...         )
        ...
        ...     async def send_email(self, to: str, message: str) -> None:
        ...         # Email sending implementation
        ...         pass

        >>> # Run the processor
        >>> executor = EventProcessorExecutor(
        ...     subscription=event_bus.subscribe("orders"),
        ...     processor=EmailNotificationProcessor(),
        ...     condition=Never(),
        ...     strategy=NoCatchup(),
        ...     batch_size=10
        ... )
        >>> await executor.run()  # Process events continuously

    See Also:
        - EventProcessorExecutor: Runtime execution engine
        - @handles_event: Decorator for registering event handlers
        - CatchupStrategy: Strategies for initializing processor state
        - CatchupCondition: Triggers for catchup operations
    """

    # Class-level routing table (set during __init_subclass__)
    _event_router: ClassVar["MessageRouter"]

    def __init_subclass__(cls, **kwargs: object) -> None:
        """Set up event routing table when subclass is defined.

        This is called automatically when a class inherits from EventProcessor.
        It scans the class for @handles_event decorated methods and builds
        a routing table based on their type annotations.

        Args:
            **kwargs: Additional keyword arguments passed to super().__init_subclass__
        """
        super().__init_subclass__(**kwargs)
        cls._event_router = setup_event_handling(cls)

    async def handle(self, event: BaseModel) -> object:
        """Route an event to its registered handler method.

        This is called by EventProcessorExecutor for each event. It uses
        the routing table to find the appropriate handler method based on
        the event type and invokes it.

        This method is async to support async event handler methods. If the
        handler method returns a coroutine, it will be properly awaited.

        Args:
            event: The event data to handle (typically from Event.data)

        Returns:
            The return value of the handler method (typically None)

        Raises:
            KeyError: If no handler is registered for the event type
        """
        result = self._event_router.route(self, event)
        # If the handler is async, await the coroutine
        if inspect.iscoroutine(result):
            return await result
        return result
