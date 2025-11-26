"""Event sourcing infrastructure for interlock.

This package provides the core event sourcing components:
- Event: Immutable record of state changes
- EventStore: Durable event persistence
- EventBus: Coordinates persistence, upcasting, and delivery
- EventTransport: Real-time event delivery to subscribers
- Upcasting: Event schema evolution support
"""

from .bus import EventBus
from .delivery import AsynchronousDelivery, EventDelivery, SynchronousDelivery
from .event import Event, utc_now
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
    Never,
    NoCatchup,
)
from .store import EventStore, InMemoryEventStore
from .transport import EventSubscription, EventTransport, InMemoryEventTransport
from .upcasting import (
    EagerUpcastingStrategy,
    EventUpcaster,
    LazyUpcastingStrategy,
    UpcastingPipeline,
    UpcasterMap,
    UpcastingStrategy,
)

__all__ = [
    # Core event types
    "Event",
    "utc_now",
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
    # Upcasting support
    "EventUpcaster",
    "UpcastingStrategy",
    "LazyUpcastingStrategy",
    "EagerUpcastingStrategy",
    "UpcastingPipeline",
    "UpcasterMap",
]
