"""Domain primitives for event sourcing and CQRS.

This module contains the core building blocks that users extend to create
their domain models:

- Aggregate: Base class for domain aggregates that emit events
- Command: Base class for command messages
- Event: Base class for event messages  
- ConcurrencyError: Exception for optimistic concurrency conflicts
"""

from .aggregate import Aggregate
from .command import Command
from .event import Event, utc_now
from .exceptions import ConcurrencyError

__all__ = [
    "Aggregate",
    "Command",
    "Event",
    "utc_now",
    "ConcurrencyError",
]

