from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import timedelta


@dataclass(frozen=True, slots=True)
class Lag:
    """Metrics measuring how far behind a processor is from the write model.

    Lag is measured in two dimensions:
    1. **Unprocessed events** - How many events are waiting to be processed
    2. **Average event age** - How old the events being processed are

    Both metrics provide different insights:
    - High unprocessed count indicates backlog (volume problem)
    - High average age indicates slowness (latency problem)

    These metrics are used by CatchupCondition instances to determine
    when catchup strategies should be triggered.

    Attributes:
        unprocessed_events: Number of events queued but not yet processed.
            Calculated as the depth of the event subscription.
        average_event_age: Mean age of recently processed events.
            Calculated by averaging (utc_now - event.timestamp) over
            the most recent batch.

    Example:
        >>> lag = Lag(unprocessed_events=1000, average_event_age=timedelta(minutes=5))
        >>> if lag.average_age_is_older_than(timedelta(minutes=10)):
        ...     print("Events are getting stale!")
        >>> if lag.unprocessed_events_is_greater_than(5000):
        ...     print("Significant backlog detected!")
    """

    unprocessed_events: int
    average_event_age: timedelta

    def average_age_is_older_than(self, age: timedelta) -> bool:
        """Check if average event age exceeds a threshold.

        Args:
            age: Threshold to compare against

        Returns:
            True if average_event_age > age
        """
        return self.average_event_age > age

    def unprocessed_events_is_greater_than(self, n: int) -> bool:
        """Check if unprocessed event count exceeds a threshold.

        Args:
            n: Threshold to compare against

        Returns:
            True if unprocessed_events > n
        """
        return self.unprocessed_events > n


class CatchupCondition(ABC):
    """Condition for triggering catchup operations based on lag metrics.

    CatchupConditions evaluate processor lag to determine when catchup
    strategies should be executed. They can be combined using AnyOf/AllOf
    to create complex triggering logic.

    Common patterns:
    - Never: Disable catchup entirely
    - AfterNEvents: Trigger when backlog exceeds threshold
    - AfterNAge: Trigger when events get too old
    - AnyOf/AllOf: Combine multiple conditions with OR/AND logic
    """

    @abstractmethod
    def should_catchup(self, lag: Lag) -> bool:
        """Evaluate whether catchup should be triggered.

        Args:
            lag: Current lag metrics for the processor

        Returns:
            True if catchup should be initiated, False otherwise
        """
        ...


class Never(CatchupCondition):
    """Never trigger catchup - disable catchup entirely.

    Use this when:
    - Processor only handles new events (no historical state)
    - Catchup is managed manually or externally
    - Testing scenarios where catchup is not needed

    Example:
        >>> executor = EventProcessorExecutor(
        ...     subscription=subscription,
        ...     processor=processor,
        ...     condition=Never(),  # Catchup disabled
        ...     strategy=NoCatchup(),
        ...     batch_size=10
        ... )
    """

    def should_catchup(self, _: Lag) -> bool:
        """Always returns False - catchup never triggered.

        Args:
            _: Lag metrics (ignored)

        Returns:
            False
        """
        return False


class AfterNEvents(CatchupCondition):
    """Trigger catchup when unprocessed event count exceeds threshold.

    This condition triggers based on backlog volume, not event age.
    It's useful for preventing unbounded queue growth.

    Args:
        n: Maximum number of unprocessed events before triggering catchup

    Example:
        >>> # Trigger catchup if more than 10,000 events are queued
        >>> condition = AfterNEvents(10_000)
        >>> if condition.should_catchup(lag):
        ...     await strategy.catchup()
    """

    def __init__(self, n: int):
        """Initialize with event count threshold.

        Args:
            n: Unprocessed event count threshold (must be > 0)
        """
        if n <= 0:
            raise ValueError("Threshold must be positive")
        self.n = n

    def should_catchup(self, lag: Lag) -> bool:
        """Check if unprocessed events exceed threshold.

        Args:
            lag: Current lag metrics

        Returns:
            True if lag.unprocessed_events > n
        """
        return lag.unprocessed_events_is_greater_than(self.n)


class AfterNAge(CatchupCondition):
    """Trigger catchup when average event age exceeds threshold.

    This condition triggers based on event staleness, not backlog size.
    It's useful for ensuring timely processing and data freshness.

    Args:
        age: Maximum acceptable average event age

    Example:
        >>> # Trigger catchup if events are > 5 minutes old on average
        >>> condition = AfterNAge(timedelta(minutes=5))
        >>> if condition.should_catchup(lag):
        ...     await strategy.catchup()
    """

    def __init__(self, age: timedelta):
        """Initialize with age threshold.

        Args:
            age: Maximum average event age before triggering catchup
        """
        if age.total_seconds() <= 0:
            raise ValueError("Age threshold must be positive")
        self.age = age

    def should_catchup(self, lag: Lag) -> bool:
        """Check if average event age exceeds threshold.

        Args:
            lag: Current lag metrics

        Returns:
            True if lag.average_event_age > age
        """
        return lag.average_age_is_older_than(self.age)


class AnyOf(CatchupCondition):
    """Trigger catchup if ANY of the given conditions are met (OR logic).

    This allows combining multiple conditions where any single condition
    being true will trigger catchup.

    Example:
        >>> # Catchup if EITHER queue > 5000 OR events > 10min old
        >>> condition = AnyOf(
        ...     AfterNEvents(5000),
        ...     AfterNAge(timedelta(minutes=10))
        ... )
    """

    def __init__(self, *conditions: CatchupCondition):
        """Initialize with conditions to evaluate.

        Args:
            *conditions: Variable number of CatchupCondition instances
        """
        if not conditions:
            raise ValueError("Must provide at least one condition")
        self.conditions = conditions

    def should_catchup(self, lag: Lag) -> bool:
        """Check if any condition is satisfied.

        Args:
            lag: Current lag metrics

        Returns:
            True if any condition returns True
        """
        return any(c.should_catchup(lag) for c in self.conditions)


class AllOf(CatchupCondition):
    """Trigger catchup only if ALL given conditions are met (AND logic).

    This allows combining multiple conditions where all conditions must
    be true to trigger catchup.

    Example:
        >>> # Catchup only if queue > 1000 AND events > 5min old
        >>> condition = AllOf(
        ...     AfterNEvents(1000),
        ...     AfterNAge(timedelta(minutes=5))
        ... )
    """

    def __init__(self, *conditions: CatchupCondition):
        """Initialize with conditions to evaluate.

        Args:
            *conditions: Variable number of CatchupCondition instances
        """
        if not conditions:
            raise ValueError("Must provide at least one condition")
        self.conditions = conditions

    def should_catchup(self, lag: Lag) -> bool:
        """Check if all conditions are satisfied.

        Args:
            lag: Current lag metrics

        Returns:
            True if all conditions return True
        """
        return all(c.should_catchup(lag) for c in self.conditions)
