"""Tests for core testing components."""

from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import BaseModel

from interlock.domain import Event
from interlock.testing.core import (
    ContainsErrorOfExactType,
    ContainsEventOfExactPayload,
    ContainsEventOfExactType,
    DoesNotHaveEvents,
    Result,
    StateMatches,
)


def create_event(payload: BaseModel) -> Event:
    """Helper to create Event objects for testing."""
    return Event(
        aggregate_id=uuid4(),
        data=payload,
        sequence_number=1,
    )


# Test event models
class Event1(BaseModel):
    value: str


class Event2(BaseModel):
    amount: Decimal


class Event3(BaseModel):
    count: int


# Test state model
class State(BaseModel):
    counter: int
    active: bool


class TestResult:
    """Tests for Result class."""

    def test_result_initialization(self):
        """Test Result initialization."""
        events = [create_event(Event1(value="test"))]
        errors = [ValueError("test error")]
        states = {"key1": State(counter=1, active=True)}

        result = Result(events=events, errors=errors, states=states)

        assert result.events == events
        assert result.errors == errors
        assert result.states == states

    def test_result_initialization_without_states(self):
        """Test Result initialization without states."""
        events = []
        errors = []

        result = Result(events=events, errors=errors)

        assert result.events == []
        assert result.errors == []
        assert result.states == {}

    def test_contains_event_of_type_true(self):
        """Test contains_event_of_type returns True when event exists."""
        event = create_event(Event1(value="test"))
        result = Result(events=[event], errors=[])

        assert result.contains_event_of_type(Event1)

    def test_contains_event_of_type_false(self):
        """Test contains_event_of_type returns False when event doesn't exist."""
        event = create_event(Event1(value="test"))
        result = Result(events=[event], errors=[])

        assert not result.contains_event_of_type(Event2)

    def test_contains_event_of_type_multiple_events(self):
        """Test contains_event_of_type with multiple events."""
        events = [
            create_event(Event1(value="test1")),
            create_event(Event2(amount=Decimal("100.00"))),
            create_event(Event3(count=5)),
        ]
        result = Result(events=events, errors=[])

        assert result.contains_event_of_type(Event1)
        assert result.contains_event_of_type(Event2)
        assert result.contains_event_of_type(Event3)

    def test_contains_event_true(self):
        """Test contains_event returns True when exact payload exists."""
        payload = Event1(value="test")
        event = create_event(payload)
        result = Result(events=[event], errors=[])

        assert result.contains_event(payload)

    def test_contains_event_false(self):
        """Test contains_event returns False when exact payload doesn't exist."""
        event = create_event(Event1(value="test"))
        result = Result(events=[event], errors=[])

        assert not result.contains_event(Event1(value="different"))

    def test_contains_event_exact_match(self):
        """Test contains_event requires exact payload match."""
        events = [
            create_event(Event2(amount=Decimal("100.00"))),
            create_event(Event2(amount=Decimal("200.00"))),
        ]
        result = Result(events=events, errors=[])

        assert result.contains_event(Event2(amount=Decimal("100.00")))
        assert result.contains_event(Event2(amount=Decimal("200.00")))
        assert not result.contains_event(Event2(amount=Decimal("150.00")))

    def test_contains_error_of_type_true(self):
        """Test contains_error_of_type returns True when error exists."""
        error = ValueError("test error")
        result = Result(events=[], errors=[error])

        assert result.contains_error_of_type(ValueError)

    def test_contains_error_of_type_false(self):
        """Test contains_error_of_type returns False when error doesn't exist."""
        error = ValueError("test error")
        result = Result(events=[], errors=[error])

        assert not result.contains_error_of_type(TypeError)

    def test_contains_error_of_type_multiple_errors(self):
        """Test contains_error_of_type with multiple errors."""
        errors = [ValueError("error1"), TypeError("error2"), RuntimeError("error3")]
        result = Result(events=[], errors=errors)

        assert result.contains_error_of_type(ValueError)
        assert result.contains_error_of_type(TypeError)
        assert result.contains_error_of_type(RuntimeError)

    def test_state_matches_true(self):
        """Test state_matches returns True when predicate matches."""
        state = State(counter=5, active=True)
        result = Result(events=[], errors=[], states={"key1": state})

        assert result.state_matches("key1", lambda s: s.counter == 5)

    def test_state_matches_false(self):
        """Test state_matches returns False when predicate doesn't match."""
        state = State(counter=5, active=True)
        result = Result(events=[], errors=[], states={"key1": state})

        assert not result.state_matches("key1", lambda s: s.counter == 10)

    def test_state_matches_missing_key(self):
        """Test state_matches returns False when state key doesn't exist."""
        result = Result(events=[], errors=[], states={})

        assert not result.state_matches("missing_key", lambda s: True)

    def test_state_matches_complex_predicate(self):
        """Test state_matches with complex predicate."""
        state = State(counter=10, active=True)
        result = Result(events=[], errors=[], states={"key1": state})

        assert result.state_matches("key1", lambda s: s.counter > 5 and s.counter < 15 and s.active)


class TestContainsEventOfExactPayload:
    """Tests for ContainsEventOfExactPayload expectation."""

    def test_was_met_true(self):
        """Test was_met returns True when payload exists."""
        payload = Event1(value="test")
        expectation = ContainsEventOfExactPayload(payload)
        event = create_event(payload)
        result = Result(events=[event], errors=[])

        assert expectation.was_met(result)

    def test_was_met_false(self):
        """Test was_met returns False when payload doesn't exist."""
        expectation = ContainsEventOfExactPayload(Event1(value="test"))
        event = create_event(Event1(value="different"))
        result = Result(events=[event], errors=[])

        assert not expectation.was_met(result)

    def test_describe(self):
        """Test describe returns appropriate message."""
        payload = Event1(value="test")
        expectation = ContainsEventOfExactPayload(payload)

        description = expectation.describe()

        assert "should contain event with payload" in description
        assert str(payload) in description

    def test_assert_met_success(self):
        """Test assert_met doesn't raise when expectation is met."""
        payload = Event1(value="test")
        expectation = ContainsEventOfExactPayload(payload)
        event = create_event(payload)
        result = Result(events=[event], errors=[])

        expectation.assert_met(result)  # Should not raise

    def test_assert_met_failure(self):
        """Test assert_met raises AssertionError when expectation not met."""
        expectation = ContainsEventOfExactPayload(Event1(value="test"))
        result = Result(events=[], errors=[])

        with pytest.raises(AssertionError, match="Expectation not met"):
            expectation.assert_met(result)

    def test_requires_state(self):
        """Test requires_state returns empty list."""
        expectation = ContainsEventOfExactPayload(Event1(value="test"))

        assert list(expectation.requires_state()) == []


class TestContainsEventOfExactType:
    """Tests for ContainsEventOfExactType expectation."""

    def test_was_met_true(self):
        """Test was_met returns True when event type exists."""
        expectation = ContainsEventOfExactType(Event1)
        event = create_event(Event1(value="test"))
        result = Result(events=[event], errors=[])

        assert expectation.was_met(result)

    def test_was_met_false(self):
        """Test was_met returns False when event type doesn't exist."""
        expectation = ContainsEventOfExactType(Event2)
        event = create_event(Event1(value="test"))
        result = Result(events=[event], errors=[])

        assert not expectation.was_met(result)

    def test_was_met_ignores_payload_differences(self):
        """Test was_met matches on type regardless of payload."""
        expectation = ContainsEventOfExactType(Event1)
        events = [
            create_event(Event1(value="value1")),
            create_event(Event1(value="value2")),
        ]
        result = Result(events=events, errors=[])

        assert expectation.was_met(result)

    def test_describe(self):
        """Test describe returns appropriate message."""
        expectation = ContainsEventOfExactType(Event1)

        description = expectation.describe()

        assert "should contain event of type" in description
        assert "Event1" in description

    def test_assert_met_success(self):
        """Test assert_met doesn't raise when expectation is met."""
        expectation = ContainsEventOfExactType(Event1)
        event = create_event(Event1(value="test"))
        result = Result(events=[event], errors=[])

        expectation.assert_met(result)  # Should not raise

    def test_assert_met_failure(self):
        """Test assert_met raises AssertionError when expectation not met."""
        expectation = ContainsEventOfExactType(Event1)
        result = Result(events=[], errors=[])

        with pytest.raises(AssertionError, match="Expectation not met"):
            expectation.assert_met(result)

    def test_requires_state(self):
        """Test requires_state returns empty list."""
        expectation = ContainsEventOfExactType(Event1)

        assert list(expectation.requires_state()) == []


class TestContainsErrorOfExactType:
    """Tests for ContainsErrorOfExactType expectation."""

    def test_was_met_true(self):
        """Test was_met returns True when error type exists."""
        expectation = ContainsErrorOfExactType(ValueError)
        result = Result(events=[], errors=[ValueError("test")])

        assert expectation.was_met(result)

    def test_was_met_false(self):
        """Test was_met returns False when error type doesn't exist."""
        expectation = ContainsErrorOfExactType(TypeError)
        result = Result(events=[], errors=[ValueError("test")])

        assert not expectation.was_met(result)

    def test_describe(self):
        """Test describe returns appropriate message."""
        expectation = ContainsErrorOfExactType(ValueError)

        description = expectation.describe()

        assert "should contain error of type" in description
        assert "ValueError" in description

    def test_assert_met_success(self):
        """Test assert_met doesn't raise when expectation is met."""
        expectation = ContainsErrorOfExactType(ValueError)
        result = Result(events=[], errors=[ValueError("test")])

        expectation.assert_met(result)  # Should not raise

    def test_assert_met_failure(self):
        """Test assert_met raises AssertionError when expectation not met."""
        expectation = ContainsErrorOfExactType(ValueError)
        result = Result(events=[], errors=[])

        with pytest.raises(AssertionError, match="Expectation not met"):
            expectation.assert_met(result)

    def test_requires_state(self):
        """Test requires_state returns empty list."""
        expectation = ContainsErrorOfExactType(ValueError)

        assert list(expectation.requires_state()) == []


class TestDoesNotHaveEvents:
    """Tests for DoesNotHaveEvents expectation."""

    def test_was_met_true(self):
        """Test was_met returns True when no events exist."""
        expectation = DoesNotHaveEvents()
        result = Result(events=[], errors=[])

        assert expectation.was_met(result)

    def test_was_met_false(self):
        """Test was_met returns False when events exist."""
        expectation = DoesNotHaveEvents()
        event = create_event(Event1(value="test"))
        result = Result(events=[event], errors=[])

        assert not expectation.was_met(result)

    def test_describe(self):
        """Test describe returns appropriate message."""
        expectation = DoesNotHaveEvents()

        description = expectation.describe()

        assert "should not emit any events" in description

    def test_assert_met_success(self):
        """Test assert_met doesn't raise when expectation is met."""
        expectation = DoesNotHaveEvents()
        result = Result(events=[], errors=[])

        expectation.assert_met(result)  # Should not raise

    def test_assert_met_failure(self):
        """Test assert_met raises AssertionError when expectation not met."""
        expectation = DoesNotHaveEvents()
        event = create_event(Event1(value="test"))
        result = Result(events=[event], errors=[])

        with pytest.raises(AssertionError, match="Expectation not met"):
            expectation.assert_met(result)

    def test_requires_state(self):
        """Test requires_state returns empty list."""
        expectation = DoesNotHaveEvents()

        assert list(expectation.requires_state()) == []


class TestStateMatches:
    """Tests for StateMatches expectation."""

    def test_was_met_true(self):
        """Test was_met returns True when state matches predicate."""
        state = State(counter=5, active=True)
        expectation = StateMatches("key1", lambda s: s.counter == 5)
        result = Result(events=[], errors=[], states={"key1": state})

        assert expectation.was_met(result)

    def test_was_met_false(self):
        """Test was_met returns False when state doesn't match predicate."""
        state = State(counter=5, active=True)
        expectation = StateMatches("key1", lambda s: s.counter == 10)
        result = Result(events=[], errors=[], states={"key1": state})

        assert not expectation.was_met(result)

    def test_was_met_missing_state(self):
        """Test was_met returns False when state doesn't exist."""
        expectation = StateMatches("missing_key", lambda s: True)
        result = Result(events=[], errors=[], states={})

        assert not expectation.was_met(result)

    def test_describe(self):
        """Test describe returns appropriate message."""
        expectation = StateMatches("key1", lambda s: s.counter > 0)

        description = expectation.describe()

        assert "should match state" in description
        assert "key1" in description

    def test_assert_met_success(self):
        """Test assert_met doesn't raise when expectation is met."""
        state = State(counter=5, active=True)
        expectation = StateMatches("key1", lambda s: s.counter == 5)
        result = Result(events=[], errors=[], states={"key1": state})

        expectation.assert_met(result)  # Should not raise

    def test_assert_met_failure(self):
        """Test assert_met raises AssertionError when expectation not met."""
        expectation = StateMatches("key1", lambda s: s.counter == 5)
        result = Result(events=[], errors=[], states={})

        with pytest.raises(AssertionError, match="Expectation not met"):
            expectation.assert_met(result)

    def test_requires_state(self):
        """Test requires_state returns state key."""
        expectation = StateMatches("key1", lambda s: True)

        required = list(expectation.requires_state())

        assert required == ["key1"]

    def test_complex_predicate(self):
        """Test StateMatches with complex predicate."""
        state = State(counter=10, active=True)
        expectation = StateMatches(
            "key1", lambda s: s.counter >= 10 and s.counter <= 20 and s.active
        )
        result = Result(events=[], errors=[], states={"key1": state})

        assert expectation.was_met(result)


class TestExpectationInterface:
    """Tests for Expectation abstract interface."""

    def test_assert_met_calls_was_met_and_describe(self):
        """Test that assert_met uses was_met and describe correctly."""

        class CustomExpectation(ContainsEventOfExactType):
            def __init__(self):
                super().__init__(Event1)

        expectation = CustomExpectation()
        result = Result(events=[], errors=[])

        with pytest.raises(AssertionError) as exc_info:
            expectation.assert_met(result)

        assert "Expectation not met" in str(exc_info.value)
        assert "should contain event of type Event1" in str(exc_info.value)


class TestResultWithMultipleStates:
    """Tests for Result with multiple states."""

    def test_multiple_states(self):
        """Test Result can handle multiple states."""
        states = {
            "state1": State(counter=1, active=True),
            "state2": State(counter=2, active=False),
            "state3": State(counter=3, active=True),
        }
        result = Result(events=[], errors=[], states=states)

        assert result.state_matches("state1", lambda s: s.counter == 1)
        assert result.state_matches("state2", lambda s: not s.active)
        assert result.state_matches("state3", lambda s: s.counter == 3 and s.active)

    def test_state_isolation(self):
        """Test that states are isolated from each other."""
        states = {
            "state1": State(counter=1, active=True),
            "state2": State(counter=1, active=False),
        }
        result = Result(events=[], errors=[], states=states)

        # Same counter value but different active flags
        assert result.state_matches("state1", lambda s: s.active)
        assert result.state_matches("state2", lambda s: not s.active)


class TestResultEdgeCases:
    """Edge case tests for Result."""

    def test_empty_result(self):
        """Test Result with no events, errors, or states."""
        result = Result(events=[], errors=[])

        assert len(result.events) == 0
        assert len(result.errors) == 0
        assert len(result.states) == 0

    def test_result_with_many_events(self):
        """Test Result with large number of events."""
        events = [create_event(Event3(count=i)) for i in range(100)]
        result = Result(events=events, errors=[])

        assert len(result.events) == 100
        assert result.contains_event_of_type(Event3)
        assert result.contains_event(Event3(count=50))

    def test_result_with_many_errors(self):
        """Test Result with multiple errors."""
        errors = [ValueError(f"error{i}") for i in range(10)]
        result = Result(events=[], errors=errors)

        assert len(result.errors) == 10
        assert result.contains_error_of_type(ValueError)


class TestExpectationCombinations:
    """Tests for combinations of expectations."""

    def test_multiple_expectations_all_met(self):
        """Test multiple expectations that are all met."""
        event = create_event(Event1(value="test"))
        state = State(counter=5, active=True)
        result = Result(events=[event], errors=[], states={"key1": state})

        exp1 = ContainsEventOfExactType(Event1)
        exp2 = StateMatches("key1", lambda s: s.counter == 5)

        assert exp1.was_met(result)
        assert exp2.was_met(result)

    def test_multiple_expectations_some_not_met(self):
        """Test multiple expectations where some fail."""
        event = create_event(Event1(value="test"))
        result = Result(events=[event], errors=[])

        exp1 = ContainsEventOfExactType(Event1)  # Should pass
        exp2 = ContainsEventOfExactType(Event2)  # Should fail

        assert exp1.was_met(result)
        assert not exp2.was_met(result)
