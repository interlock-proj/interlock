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
    AggregateProjector,
    AllOf,
    AnyOf,
    CatchupCondition,
    CatchupResult,
    CatchupStrategy,
    Checkpoint,
    CheckpointBackend,
    EventProcessor,
    EventProcessorExecutor,
    FromAggregateSnapshot,
    FromReplayingEvents,
    InMemoryCheckpointBackend,
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
    "InMemoryCheckpointBackend",
    "InMemorySagaStateStore",
    # Event processors
    "EventProcessor",
    "EventProcessorExecutor",
    "CatchupStrategy",
    "CatchupResult",
    "NoCatchup",
    "FromReplayingEvents",
    "FromAggregateSnapshot",
    "CatchupCondition",
    "Never",
    "AfterNEvents",
    "AfterNAge",
    "AnyOf",
    "AllOf",
    # Checkpoint infrastructure
    "Checkpoint",
    "CheckpointBackend",
    # Projector infrastructure
    "AggregateProjector",
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

