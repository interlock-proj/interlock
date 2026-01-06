"""Projection infrastructure for building read models.

This package provides:
- Projection: Base class combining event handling with query serving
- QueryBus: Routes queries through middleware to projections
- QueryToProjectionMap: Maps query types to projection types
- ProjectionRegistry: Registry of projection instances
- DelegateToProjection: Root handler for query dispatch
"""

from .bus import (
    DelegateToProjection,
    ProjectionRegistry,
    QueryBus,
    QueryHandler,
    QueryToProjectionMap,
)
from .projection import Projection

__all__ = [
    "DelegateToProjection",
    "Projection",
    "ProjectionRegistry",
    "QueryBus",
    "QueryHandler",
    "QueryToProjectionMap",
]
