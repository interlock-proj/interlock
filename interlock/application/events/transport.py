"""Event transport and subscription interfaces and implementations.

This module provides:
- EventSubscription: Abstract interface for consuming events from a stream
- EventTransport: Abstract interface for publishing events to subscribers
- InMemoryEventTransport: Simple in-memory implementation for testing
- InMemoryEventSubscription: Index-based subscription for in-memory transport
"""

from abc import ABC, abstractmethod
from typing import Any

from ...domain import Event


class EventSubscription(ABC):
    """Abstract interface for consuming events from an event stream.

    EventSubscription provides an async iterator-like interface for reading
    events from a specific stream or aggregate. Implementations handle
    backpressure, buffering, and ordering guarantees.

    This is typically used for:
    - Read model projections (updating query databases)
    - Process managers (saga coordination)
    - Event processors (side effects, notifications)
    """

    @abstractmethod
    async def depth(self) -> int:
        """Get the number of unread events available in the subscription.

        Returns:
            The count of events that can be consumed without blocking.
            Returns 0 if no events are currently available.

        Note:
            This is a snapshot value - the depth may change as new events
            are published to the stream.
        """
        ...

    @abstractmethod
    async def next(self) -> Event[Any]:
        """Retrieve the next event from the subscription.

        Returns:
            The next event in the stream, advancing the subscription position.

        Raises:
            StopAsyncIteration: When the subscription has been closed or
                the stream has ended.

        Note:
            This method may block if no events are currently available but
            the subscription is still active. Use depth() to check availability
            before calling if non-blocking behavior is required.
        """
        ...


class EventTransport(ABC):
    """Abstract interface for event messaging and delivery.

    EventTransport handles real-time delivery of events to subscribers
    (projections, process managers, external systems). It's separate from
    EventStore - while the store provides durable persistence for aggregate
    reconstruction, the transport provides ephemeral messaging for live updates.

    Implementations might use:
    - In-memory queues (for testing or single-process apps)
    - Message brokers (RabbitMQ, Kafka, AWS SQS/SNS)
    - Pub/sub systems (Redis, Google Pub/Sub)

    The transport doesn't guarantee delivery - it's EventStore's job to
    persist events durably. The transport is best-effort delivery for
    real-time consumers.
    """

    @abstractmethod
    async def subscribe(self, identifier: str) -> EventSubscription:
        """Create a subscription to an event stream.

        Args:
            identifier: Stream identifier, typically an aggregate ID or
                event type. The semantics depend on the transport implementation.

        Returns:
            An EventSubscription for consuming events from the stream.

        Note:
            The subscription may receive events published after subscription
            creation. Historical events should be loaded from EventStore.
        """
        ...

    @abstractmethod
    async def publish_events(self, events: list[Event[Any]]) -> None:
        """Publish events to subscribers.

        Args:
            events: List of events to publish. These are typically Event[T]
                instances, but the transport may handle raw event data.

        Note:
            This is best-effort delivery. Events are durably stored via
            EventStore.save_events() - the transport is for real-time
            notification only.
        """
        ...


class InMemoryEventTransport(EventTransport):
    """Simple in-memory event transport for testing.

    Stores all published events in a single ordered list. All subscriptions
    share the same global event stream regardless of the identifier.

    This is a minimal implementation for testing - it doesn't support:
    - Per-stream isolation (all subscriptions see all events)
    - Concurrent access (no thread safety)
    - Backpressure or buffering limits
    - Event filtering by aggregate or type
    """

    def __init__(self) -> None:
        """Initialize an empty in-memory transport."""
        self.events_in_order: list[Event[Any]] = []

    async def subscribe(self, identifier: str) -> EventSubscription:
        """Create a subscription to the global event stream.

        Args:
            identifier: Identifier is ignored - all subscriptions share the global stream

        Returns:
            A new InMemoryEventSubscription starting at the beginning of the stream

        Note:
            The identifier parameter is ignored. All subscriptions receive
            all events regardless of aggregate ID or event type.
        """
        return InMemoryEventSubscription(self)

    async def publish_events(self, events: list[Event[Any]]) -> None:
        """Append events to the global event stream.

        Args:
            events: Events to publish to all subscribers

        Note:
            Events are immediately available to all subscriptions.
            No validation or filtering is performed.
        """
        self.events_in_order.extend(events)


class InMemoryEventSubscription(EventSubscription):
    """Index-based subscription to the in-memory event stream.

    Maintains a read position (index) in the transport's global event list.
    Each call to next() advances the index and returns the event at that position.

    Limitations:
    - No thread safety (concurrent access will cause issues)
    - Raises IndexError if reading past end of stream
    - No blocking - fails immediately if no events available
    """

    def __init__(self, transport: InMemoryEventTransport) -> None:
        """Initialize a subscription at the beginning of the stream.

        Args:
            transport: The transport containing the event stream
        """
        self.index = 0
        self.transport = transport

    async def depth(self) -> int:
        """Get the number of unread events.

        Returns:
            Count of events from current position to end of stream
        """
        return len(self.transport.events_in_order) - self.index

    async def next(self) -> Event[Any]:
        """Read the next event and advance the subscription position.

        Returns:
            The event at the current index position

        Raises:
            IndexError: If attempting to read past the end of the stream
        """
        event = self.transport.events_in_order[self.index]
        self.index += 1
        return event
