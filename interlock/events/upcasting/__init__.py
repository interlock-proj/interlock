"""Event upcasting infrastructure for schema evolution.

This package provides:
- EventUpcaster: Base class for transforming events between schema versions
- UpcastingPipeline: Pipeline for applying upcasting transformations
- UpcastingStrategy: Strategies for when to apply upcasting
"""

from .pipeline import EventUpcaster, UpcastingPipeline, UpcasterMap
from .strategies import EagerUpcastingStrategy, LazyUpcastingStrategy, UpcastingStrategy

__all__ = [
    # Upcaster base class and utilities
    "EventUpcaster",
    "UpcastingPipeline",
    # Upcasting strategies
    "UpcastingStrategy",
    "LazyUpcastingStrategy",
    "EagerUpcastingStrategy",
    "UpcasterMap",
]
