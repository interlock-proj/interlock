"""Interlock - Event Sourcing and CQRS Framework for Python.

This module provides the public API for building event-sourced applications.
"""

from .application import Application, ApplicationBuilder
from .domain import Aggregate, Command, Event, Query
from .routing import (
    applies_event,
    handles_command,
    handles_event,
    handles_query,
    intercepts,
)

__all__ = [
    # Application
    "Application",
    "ApplicationBuilder",
    # Domain primitives
    "Aggregate",
    "Command",
    "Event",
    "Query",
    # Decorators
    "applies_event",
    "handles_command",
    "handles_event",
    "handles_query",
    "intercepts",
]
