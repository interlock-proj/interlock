"""Application bootstrapping and dependency injection for interlock.

This package contains the framework infrastructure for building event-sourced
applications. It includes command handling, event processing, repository management,
and application lifecycle management.
"""

from .application import Application, ApplicationBuilder
from .configurators import ApplicationProfile, ApplicationProfileSet

__all__ = [
    "Application",
    "ApplicationBuilder",
    "ApplicationProfile",
    "ApplicationProfileSet",
]
