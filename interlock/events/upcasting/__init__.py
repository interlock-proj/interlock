"""Event upcasting infrastructure for schema evolution.

This package provides:
- EventUpcaster: Base class for transforming events between schema versions
- UpcastingPipeline: Pipeline for applying upcasting transformations
- UpcastingStrategy: Strategies for when to apply upcasting
- UpcastingConfig: Configuration for upcasting behavior
"""

from .config import UpcastingConfig
from .pipeline import EventUpcaster, UpcastingPipeline, extract_upcaster_types
from .registry import UpcastingRegistry
from .strategies import EagerUpcastingStrategy, LazyUpcastingStrategy, UpcastingStrategy

__all__ = [
    # Upcaster base class and utilities
    "EventUpcaster",
    "UpcastingPipeline",
    "extract_upcaster_types",
    # Upcasting strategies
    "UpcastingStrategy",
    "LazyUpcastingStrategy",
    "EagerUpcastingStrategy",
    # Configuration and registry
    "UpcastingConfig",
    "UpcastingRegistry",
]
