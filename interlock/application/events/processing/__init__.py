"""Event processing infrastructure for CQRS read side."""

from .conditions import (
    AfterNAge,
    AfterNEvents,
    AllOf,
    AnyOf,
    CatchupCondition,
    Never,
)
from .executor import EventProcessorExecutor
from .processor import EventProcessor
from .saga import InMemorySagaStateStore, Saga, SagaStateStore, saga_step
from .strategies import (
    CatchupResult,
    CatchupStrategy,
    NoCatchup,
)

__all__ = [
    "EventProcessor",
    "EventProcessorExecutor",
    "CatchupStrategy",
    "CatchupResult",
    "NoCatchup",
    "CatchupCondition",
    "Never",
    "AfterNEvents",
    "AfterNAge",
    "AnyOf",
    "AllOf",
    "Saga",
    "saga_step",
    "SagaStateStore",
    "InMemorySagaStateStore",
]
