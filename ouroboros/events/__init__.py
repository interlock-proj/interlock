"""Event sourcing infrastructure for Ouroboros.

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
    EventProcessorRegistry,
    FromAggregateSnapshot,
    FromReplayingEvents,
    InMemoryCheckpointBackend,
    Never,
    NoCatchup,
    ProcessorConfigRegistry,
    ProcessorExecutionConfig,
)
from .store import EventStore, InMemoryEventStore
from .transport import EventSubscription, EventTransport, InMemoryEventTransport
from .upcasting import (
    EagerUpcastingStrategy,
    EventUpcaster,
    LazyUpcastingStrategy,
    UpcastingConfig,
    UpcastingPipeline,
    UpcastingRegistry,
    UpcastingStrategy,
    extract_upcaster_types,
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
    "ProcessorExecutionConfig",
    "ProcessorConfigRegistry",
    "EventProcessorRegistry",
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
    "UpcastingConfig",
    "UpcastingRegistry",
    "extract_upcaster_types",
]
