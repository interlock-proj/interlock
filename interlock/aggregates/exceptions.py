"""Exceptions for the aggregates module."""


class ConcurrencyError(Exception):
    """Raised when an optimistic concurrency check fails.

    This exception indicates that another process has modified the aggregate
    between when it was loaded and when changes were attempted to be saved.
    """

    pass
