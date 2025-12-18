"""Middleware infrastructure for commands and queries.

Middleware components wrap handlers to provide cross-cutting concerns
like logging, validation, authentication, or transaction management.
They follow the chain of responsibility pattern and can intercept
both commands (write side) and queries (read side).
"""

from .base import Handler, Middleware
from .concurrency import ConcurrencyRetryMiddleware
from .context import ContextPropagationMiddleware
from .idempotency import (
    HasIdempotencyKey,
    IdempotencyMiddleware,
    IdempotencyStorageBackend,
    IdempotencyTrackedCommand,
    InMemoryIdempotencyStorageBackend,
    NullIdempotencyStorageBackend,
)
from .logging import LoggingMiddleware

__all__ = [
    # Base classes
    "Handler",
    "Middleware",
    # Middleware implementations
    "ConcurrencyRetryMiddleware",
    "ContextPropagationMiddleware",
    "HasIdempotencyKey",
    "IdempotencyMiddleware",
    "IdempotencyStorageBackend",
    "IdempotencyTrackedCommand",
    "InMemoryIdempotencyStorageBackend",
    "NullIdempotencyStorageBackend",
    "LoggingMiddleware",
]
