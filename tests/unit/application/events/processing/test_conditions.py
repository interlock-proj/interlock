"""Tests for catchup conditions and lag metrics."""

import pytest
from datetime import timedelta

from interlock.application.events.processing.conditions import (
    AfterNAge,
    AfterNEvents,
    AllOf,
    AnyOf,
    Lag,
    Never,
)


# Fixtures


@pytest.fixture
def zero_lag():
    """Lag with no backlog or age."""
    return Lag(unprocessed_events=0, average_event_age=timedelta())


@pytest.fixture
def moderate_lag():
    """Lag with moderate backlog and age."""
    return Lag(unprocessed_events=100, average_event_age=timedelta(minutes=5))


@pytest.fixture
def high_lag():
    """Lag with high backlog and age."""
    return Lag(
        unprocessed_events=10_000, average_event_age=timedelta(minutes=30)
    )


# Lag Tests


def test_lag_creation():
    """Test Lag dataclass creation."""
    lag = Lag(unprocessed_events=500, average_event_age=timedelta(minutes=2))
    assert lag.unprocessed_events == 500
    assert lag.average_event_age == timedelta(minutes=2)


def test_lag_is_frozen():
    """Test Lag is immutable (frozen dataclass)."""
    lag = Lag(unprocessed_events=100, average_event_age=timedelta(minutes=1))
    with pytest.raises(AttributeError):
        lag.unprocessed_events = 200


def test_lag_average_age_comparison(moderate_lag):
    """Test Lag.average_age_is_older_than method."""
    assert moderate_lag.average_age_is_older_than(timedelta(minutes=4))
    assert not moderate_lag.average_age_is_older_than(timedelta(minutes=5))
    assert not moderate_lag.average_age_is_older_than(timedelta(minutes=10))


def test_lag_unprocessed_events_comparison(moderate_lag):
    """Test Lag.unprocessed_events_is_greater_than method."""
    assert moderate_lag.unprocessed_events_is_greater_than(99)
    assert not moderate_lag.unprocessed_events_is_greater_than(100)
    assert not moderate_lag.unprocessed_events_is_greater_than(1000)


def test_lag_zero_values():
    """Test Lag with zero values."""
    lag = Lag(unprocessed_events=0, average_event_age=timedelta())
    assert not lag.average_age_is_older_than(timedelta())
    assert not lag.unprocessed_events_is_greater_than(0)


# Never Condition Tests


def test_never_always_returns_false(zero_lag, moderate_lag, high_lag):
    """Test Never condition always returns False."""
    condition = Never()
    assert not condition.should_catchup(zero_lag)
    assert not condition.should_catchup(moderate_lag)
    assert not condition.should_catchup(high_lag)


# AfterNEvents Tests


def test_after_n_events_creation():
    """Test AfterNEvents condition creation."""
    condition = AfterNEvents(1000)
    assert condition.n == 1000


def test_after_n_events_validation_zero():
    """Test AfterNEvents rejects zero threshold."""
    with pytest.raises(ValueError, match="Threshold must be positive"):
        AfterNEvents(0)


def test_after_n_events_validation_negative():
    """Test AfterNEvents rejects negative threshold."""
    with pytest.raises(ValueError, match="Threshold must be positive"):
        AfterNEvents(-10)


def test_after_n_events_triggers_when_exceeded():
    """Test AfterNEvents triggers when threshold exceeded."""
    condition = AfterNEvents(100)

    # Below threshold
    lag_below = Lag(unprocessed_events=50, average_event_age=timedelta())
    assert not condition.should_catchup(lag_below)

    # At threshold
    lag_at = Lag(unprocessed_events=100, average_event_age=timedelta())
    assert not condition.should_catchup(lag_at)

    # Above threshold
    lag_above = Lag(unprocessed_events=101, average_event_age=timedelta())
    assert condition.should_catchup(lag_above)


def test_after_n_events_with_large_backlog():
    """Test AfterNEvents with very large backlog."""
    condition = AfterNEvents(1_000_000)
    lag = Lag(unprocessed_events=2_000_000, average_event_age=timedelta())
    assert condition.should_catchup(lag)


# AfterNAge Tests


def test_after_n_age_creation():
    """Test AfterNAge condition creation."""
    age = timedelta(minutes=10)
    condition = AfterNAge(age)
    assert condition.age == age


def test_after_n_age_validation_zero():
    """Test AfterNAge rejects zero threshold."""
    with pytest.raises(ValueError, match="Age threshold must be positive"):
        AfterNAge(timedelta())


def test_after_n_age_validation_negative():
    """Test AfterNAge rejects negative threshold."""
    with pytest.raises(ValueError, match="Age threshold must be positive"):
        AfterNAge(timedelta(seconds=-1))


def test_after_n_age_triggers_when_exceeded():
    """Test AfterNAge triggers when threshold exceeded."""
    condition = AfterNAge(timedelta(minutes=5))

    # Below threshold
    lag_below = Lag(
        unprocessed_events=0, average_event_age=timedelta(minutes=3)
    )
    assert not condition.should_catchup(lag_below)

    # At threshold
    lag_at = Lag(unprocessed_events=0, average_event_age=timedelta(minutes=5))
    assert not condition.should_catchup(lag_at)

    # Above threshold
    lag_above = Lag(
        unprocessed_events=0, average_event_age=timedelta(minutes=6)
    )
    assert condition.should_catchup(lag_above)


def test_after_n_age_with_very_old_events():
    """Test AfterNAge with very old events."""
    condition = AfterNAge(timedelta(hours=1))
    lag = Lag(unprocessed_events=0, average_event_age=timedelta(days=7))
    assert condition.should_catchup(lag)


# AnyOf Tests


def test_any_of_creation():
    """Test AnyOf condition creation."""
    cond1 = Never()
    cond2 = AfterNEvents(100)
    condition = AnyOf(cond1, cond2)
    assert len(condition.conditions) == 2


def test_any_of_validation_empty():
    """Test AnyOf rejects empty conditions list."""
    with pytest.raises(
        ValueError, match="Must provide at least one condition"
    ):
        AnyOf()


def test_any_of_triggers_when_any_met():
    """Test AnyOf triggers when any condition is met."""
    condition = AnyOf(
        AfterNEvents(1000),  # Will trigger
        AfterNAge(timedelta(hours=1)),  # Will not trigger
    )

    lag = Lag(unprocessed_events=2000, average_event_age=timedelta(minutes=5))
    assert condition.should_catchup(lag)


def test_any_of_does_not_trigger_when_none_met():
    """Test AnyOf doesn't trigger when no conditions met."""
    condition = AnyOf(
        AfterNEvents(1000),
        AfterNAge(timedelta(hours=1)),
    )

    lag = Lag(unprocessed_events=100, average_event_age=timedelta(minutes=5))
    assert not condition.should_catchup(lag)


def test_any_of_triggers_when_all_met():
    """Test AnyOf triggers when all conditions met."""
    condition = AnyOf(
        AfterNEvents(100),
        AfterNAge(timedelta(minutes=5)),
    )

    lag = Lag(unprocessed_events=200, average_event_age=timedelta(minutes=10))
    assert condition.should_catchup(lag)


def test_any_of_with_single_condition():
    """Test AnyOf with single condition."""
    condition = AnyOf(AfterNEvents(100))

    lag_below = Lag(unprocessed_events=50, average_event_age=timedelta())
    lag_above = Lag(unprocessed_events=150, average_event_age=timedelta())

    assert not condition.should_catchup(lag_below)
    assert condition.should_catchup(lag_above)


def test_any_of_with_never():
    """Test AnyOf containing Never condition."""
    condition = AnyOf(Never(), AfterNEvents(100))

    lag = Lag(unprocessed_events=200, average_event_age=timedelta())
    assert condition.should_catchup(lag)  # AfterNEvents triggers


# AllOf Tests


def test_all_of_creation():
    """Test AllOf condition creation."""
    cond1 = AfterNEvents(100)
    cond2 = AfterNAge(timedelta(minutes=5))
    condition = AllOf(cond1, cond2)
    assert len(condition.conditions) == 2


def test_all_of_validation_empty():
    """Test AllOf rejects empty conditions list."""
    with pytest.raises(
        ValueError, match="Must provide at least one condition"
    ):
        AllOf()


def test_all_of_triggers_when_all_met():
    """Test AllOf triggers only when all conditions met."""
    condition = AllOf(
        AfterNEvents(100),
        AfterNAge(timedelta(minutes=5)),
    )

    lag = Lag(unprocessed_events=200, average_event_age=timedelta(minutes=10))
    assert condition.should_catchup(lag)


def test_all_of_does_not_trigger_when_one_not_met():
    """Test AllOf doesn't trigger when one condition not met."""
    condition = AllOf(
        AfterNEvents(100),  # Met
        AfterNAge(timedelta(hours=1)),  # Not met
    )

    lag = Lag(unprocessed_events=200, average_event_age=timedelta(minutes=5))
    assert not condition.should_catchup(lag)


def test_all_of_does_not_trigger_when_none_met():
    """Test AllOf doesn't trigger when no conditions met."""
    condition = AllOf(
        AfterNEvents(1000),
        AfterNAge(timedelta(hours=1)),
    )

    lag = Lag(unprocessed_events=100, average_event_age=timedelta(minutes=5))
    assert not condition.should_catchup(lag)


def test_all_of_with_single_condition():
    """Test AllOf with single condition."""
    condition = AllOf(AfterNEvents(100))

    lag_below = Lag(unprocessed_events=50, average_event_age=timedelta())
    lag_above = Lag(unprocessed_events=150, average_event_age=timedelta())

    assert not condition.should_catchup(lag_below)
    assert condition.should_catchup(lag_above)


def test_all_of_with_never():
    """Test AllOf containing Never condition."""
    condition = AllOf(Never(), AfterNEvents(100))

    lag = Lag(unprocessed_events=200, average_event_age=timedelta())
    assert not condition.should_catchup(lag)  # Never blocks


# Nested Composition Tests


def test_nested_any_of_all_of():
    """Test nested AnyOf and AllOf conditions."""
    condition = AnyOf(
        AllOf(
            AfterNEvents(100),
            AfterNAge(timedelta(minutes=10)),
        ),
        AfterNEvents(10_000),
    )

    # Both conditions in AllOf met
    lag1 = Lag(unprocessed_events=200, average_event_age=timedelta(minutes=15))
    assert condition.should_catchup(lag1)

    # Only second condition of AnyOf met
    lag2 = Lag(
        unprocessed_events=20_000, average_event_age=timedelta(minutes=1)
    )
    assert condition.should_catchup(lag2)

    # Neither branch met
    lag3 = Lag(unprocessed_events=50, average_event_age=timedelta(minutes=5))
    assert not condition.should_catchup(lag3)


def test_nested_all_of_any_of():
    """Test nested AllOf and AnyOf conditions."""
    condition = AllOf(
        AnyOf(
            AfterNEvents(100),
            AfterNEvents(1000),
        ),
        AfterNAge(timedelta(minutes=5)),
    )

    # Both outer conditions met
    lag1 = Lag(unprocessed_events=200, average_event_age=timedelta(minutes=10))
    assert condition.should_catchup(lag1)

    # Only inner AnyOf met
    lag2 = Lag(unprocessed_events=200, average_event_age=timedelta(minutes=1))
    assert not condition.should_catchup(lag2)

    # Only outer AfterNAge met
    lag3 = Lag(unprocessed_events=50, average_event_age=timedelta(minutes=10))
    assert not condition.should_catchup(lag3)


def test_deeply_nested_conditions():
    """Test deeply nested condition composition."""
    condition = AnyOf(
        AllOf(
            AnyOf(
                AfterNEvents(50),
                AfterNEvents(100),
            ),
            AfterNAge(timedelta(minutes=2)),
        ),
        AfterNEvents(10_000),
    )

    # Innermost AnyOf (50 events) + middle AfterNAge met
    lag = Lag(unprocessed_events=75, average_event_age=timedelta(minutes=5))
    assert condition.should_catchup(lag)
