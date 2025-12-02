"""Event delivery orchestration for executing processors.

This module provides the EventDelivery abstraction which orchestrates:
- Publishing events to transport infrastructure (Kafka, RabbitMQ, in-memory)
- Executing processors according to synchronous or asynchronous strategy
- Creating subscriptions for asynchronous processor execution

EventDelivery unifies the concepts of EventTransport (infrastructure) and
EventDispatchStrategy (execution policy) into a single cohesive abstraction.
"""

from abc import ABC, abstractmethod
from typing import Any

from ...domain import Event
from .processing import EventProcessor
from .transport import EventSubscription, EventTransport


class EventDelivery(ABC):
    """Abstract strategy for delivering events to processors.

    EventDelivery orchestrates both:
    1. Publishing events to transport infrastructure (for durability and subscriptions)
    2. Executing processors according to synchronous or asynchronous strategy

    Implementations:
    - SynchronousDelivery: Publishes to transport + executes processors immediately
    - AsynchronousDelivery: Publishes to transport only (processors consume via subscriptions)
    """

    @abstractmethod
    async def deliver(self, events: list[Event[Any]]) -> None:
        """Deliver events according to the strategy.

        Args:
            events: Events to deliver to processors

        Note:
            The implementation determines whether processors execute immediately
            (synchronous) or later via subscriptions (asynchronous).
        """
        ...

    @abstractmethod
    async def subscribe(self, identifier: str) -> EventSubscription:
        """Create a subscription for consuming events asynchronously.

        Args:
            identifier: Stream identifier (aggregate ID, event type, or "all")

        Returns:
            EventSubscription for consuming events from the transport

        Note:
            Used by Application.run_event_processors() to consume events
            in a separate process or async task.
        """
        ...


class SynchronousDelivery(EventDelivery):
    """Synchronous event delivery with immediate processor execution.

    This strategy publishes events to the transport (for any subscriptions)
    and immediately executes all registered processors synchronously during
    the publish_events() call.

    Characteristics:
    - Processors execute in the same transaction/process as command handling
    - Command latency includes all processor execution time
    - Processor failures cause command to fail
    - Simple deployment model (single process)
    - Immediate consistency

    Use cases:
    - Simple monolithic applications
    - Prototyping and development
    - When immediate consistency is required
    - When processors are fast and reliable

    Example:
        >>> transport = InMemoryEventTransport()
        >>> processors = [MyProcessor()]
        >>> delivery = SynchronousDelivery(transport, processors)
        >>> await delivery.deliver(events)  # Processors execute immediately
    """

    def __init__(self, transport: EventTransport, processors: list[EventProcessor]):
        """Initialize synchronous delivery.

        Args:
            transport: Event transport for publishing and subscriptions
            processors: List of processors to execute immediately
        """
        self.transport = transport
        self.processors = processors

    async def deliver(self, events: list[Event[Any]]) -> None:
        """Publish events and execute processors immediately.

        Args:
            events: Events to deliver

        Raises:
            Any exceptions raised by processors will propagate to the caller
        """
        # Publish to transport (for any subscriptions)
        await self.transport.publish_events(events)

        # Execute all processors immediately
        for event in events:
            for processor in self.processors:
                await processor.handle(event.data)

    async def subscribe(self, identifier: str) -> EventSubscription:
        """Create subscription to the underlying transport.

        Args:
            identifier: Stream identifier

        Returns:
            EventSubscription from the transport

        Note:
            While synchronous delivery executes processors immediately,
            the transport still supports subscriptions for testing or
            alternative consumption patterns.
        """
        return await self.transport.subscribe(identifier)


class AsynchronousDelivery(EventDelivery):
    """Asynchronous event delivery via transport subscriptions.

    This strategy only publishes events to the transport. Processors run
    separately by consuming events via subscriptions (typically in separate
    processes or async tasks via Application.run_event_processors()).

    Characteristics:
    - Processors execute independently from command handling
    - Command latency is minimal (just publish to transport)
    - Processor failures don't affect command success
    - Scalable deployment (processors can run in separate containers)
    - Eventual consistency

    Use cases:
    - Production microservice architectures
    - High-throughput systems
    - When scaling read and write sides independently
    - When using external message brokers (Kafka, RabbitMQ)

    Example:
        >>> transport = KafkaEventTransport(brokers=["localhost:9092"])
        >>> delivery = AsynchronousDelivery(transport)
        >>> await delivery.deliver(events)  # Just publishes
        >>>
        >>> # Separate process:
        >>> subscription = await delivery.subscribe("all")
        >>> event = await subscription.next()
        >>> await processor.handle(event.data)
    """

    def __init__(self, transport: EventTransport):
        """Initialize asynchronous delivery.

        Args:
            transport: Event transport for publishing and subscriptions
        """
        self.transport = transport

    async def deliver(self, events: list[Event[Any]]) -> None:
        """Publish events to transport without executing processors.

        Args:
            events: Events to deliver

        Note:
            Processors will consume these events via subscriptions
            created through subscribe().
        """
        await self.transport.publish_events(events)

    async def subscribe(self, identifier: str) -> EventSubscription:
        """Create subscription for consuming events asynchronously.

        Args:
            identifier: Stream identifier

        Returns:
            EventSubscription from the transport

        Note:
            This is how processors consume events when using
            Application.run_event_processors().
        """
        return await self.transport.subscribe(identifier)
