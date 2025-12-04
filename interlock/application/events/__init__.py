"""Event sourcing infrastructure for interlock.

This package provides the core event sourcing components:
- EventStore: Durable event persistence
- EventBus: Coordinates persistence, upcasting, and delivery
- EventTransport: Real-time event delivery to subscribers
- EventProcessor: Process events and maintain read models
- Upcasting: Event schema evolution support
"""

from .bus import EventBus
from .delivery import AsynchronousDelivery, EventDelivery, SynchronousDelivery
from .processing import (
    AfterNAge,
    AfterNEvents,
    AllOf,
    AnyOf,
    CatchupCondition,
    CatchupResult,
    CatchupStrategy,
    EventProcessor,
    EventProcessorExecutor,
    FromReplayingEvents,
    InMemorySagaStateStore,
    Never,
    NoCatchup,
    Saga,
    SagaStateStore,
)
from .store import EventStore, InMemoryEventStore
from .transport import EventSubscription, EventTransport, InMemoryEventTransport
from .upcasting import (
    EagerUpcastingStrategy,
    EventUpcaster,
    LazyUpcastingStrategy,
    UpcasterMap,
    UpcastingPipeline,
    UpcastingStrategy,
)

__all__ = [
    # Event bus and infrastructure
    "EventBus",
    "EventStore",
    "EventTransport",
    "EventSubscription",
    # Event delivery strategies
    "EventDelivery",
    "SynchronousDelivery",
    "AsynchronousDelivery",
    # In-memory implementations
    "InMemoryEventStore",
    "InMemoryEventTransport",
    "InMemorySagaStateStore",
    # Event processors
    "EventProcessor",
    "EventProcessorExecutor",
    "CatchupStrategy",
    "CatchupResult",
    "NoCatchup",
    "FromReplayingEvents",
    "CatchupCondition",
    "Never",
    "AfterNEvents",
    "AfterNAge",
    "AnyOf",
    "AllOf",
    # Saga infrastructure
    "Saga",
    "SagaStateStore",
    # Upcasting support
    "EventUpcaster",
    "UpcastingStrategy",
    "LazyUpcastingStrategy",
    "EagerUpcastingStrategy",
    "UpcastingPipeline",
    "UpcasterMap",
]
