"""Event processing infrastructure for CQRS read models.

This package provides:
- EventProcessor: Base class for building read models and handling side effects
- Saga: Base class for stateful sagas with automatic state management
- SagaStateStore: Abstract storage backend for saga state
- CatchupStrategy: Strategies for catching up with the event store
- CatchupCondition: Conditions for triggering catchup operations
- EventProcessorExecutor: Runtime execution engine for processors
- CheckpointBackend: Checkpoint storage for resumable catchup
- AggregateProjector: Projector for snapshot-based catchup
"""

from .checkpoint import Checkpoint, CheckpointBackend, InMemoryCheckpointBackend
from .conditions import AfterNAge, AfterNEvents, AllOf, AnyOf, CatchupCondition, Never
from .executor import EventProcessorExecutor
from .processor import EventProcessor
from .projectors import AggregateProjector
from .saga import Saga, saga_step
from .saga_state_store import InMemorySagaStateStore, SagaStateStore
from .strategies import (
    CatchupResult,
    CatchupStrategy,
    FromAggregateSnapshot,
    FromReplayingEvents,
    NoCatchup,
)

__all__ = [
    # Processor base class
    "EventProcessor",
    "EventProcessorExecutor",
    # Saga infrastructure
    "Saga",
    "saga_step",
    "SagaStateStore",
    "InMemorySagaStateStore",
    # Catchup strategies
    "CatchupStrategy",
    "CatchupResult",
    "NoCatchup",
    "FromReplayingEvents",
    "FromAggregateSnapshot",
    # Catchup conditions
    "CatchupCondition",
    "Never",
    "AfterNEvents",
    "AfterNAge",
    "AnyOf",
    "AllOf",
    # Checkpoint infrastructure
    "Checkpoint",
    "CheckpointBackend",
    "InMemoryCheckpointBackend",
    # Projector infrastructure
    "AggregateProjector",
]
