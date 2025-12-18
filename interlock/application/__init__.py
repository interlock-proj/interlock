"""Application bootstrapping and dependency injection for interlock.

This package contains the framework infrastructure for building event-sourced
applications. It includes command handling, event processing, repository
management, projection/query handling, and application lifecycle management.
"""

from .application import Application, ApplicationBuilder, HasLifecycle
from .configurators import ApplicationProfile
from .middleware import (
    ConcurrencyRetryMiddleware,
    ContextPropagationMiddleware,
    Handler,
    HasIdempotencyKey,
    IdempotencyMiddleware,
    IdempotencyStorageBackend,
    InMemoryIdempotencyStorageBackend,
    LoggingMiddleware,
    Middleware,
    NullIdempotencyStorageBackend,
)
from .projections import (
    DelegateToProjection,
    Projection,
    ProjectionRegistry,
    QueryBus,
    QueryHandler,
    QueryToProjectionMap,
)

__all__ = [
    # Application
    "Application",
    "ApplicationBuilder",
    "ApplicationProfile",
    "HasLifecycle",
    # Middleware
    "ConcurrencyRetryMiddleware",
    "ContextPropagationMiddleware",
    "Handler",
    "HasIdempotencyKey",
    "IdempotencyMiddleware",
    "IdempotencyStorageBackend",
    "InMemoryIdempotencyStorageBackend",
    "LoggingMiddleware",
    "Middleware",
    "NullIdempotencyStorageBackend",
    # Projections
    "DelegateToProjection",
    "Projection",
    "ProjectionRegistry",
    "QueryBus",
    "QueryHandler",
    "QueryToProjectionMap",
]
