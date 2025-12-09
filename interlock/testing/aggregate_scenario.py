from collections.abc import Callable
from typing import Any, Generic, TypeVar

from pydantic import BaseModel
from ulid import ULID

from interlock.domain import Aggregate, Command

from .core import (
    ContainsEventOfExactPayload,
    ContainsEventOfExactType,
    DoesNotHaveEvents,
    Scenario,
    StateMatches,
)

A = TypeVar("A", bound="Aggregate")


class AggregateScenario(Scenario[A], Generic[A]):
    """A scenario for testing an aggregate.

    This scenario allows you to test an aggregate by:
    - Given a list of events that have already been emitted
    - When a list of commands are executed
    - Then a list of expectations are met

    The scenario will execute the commands and assert the expectations.
    If the expectations are not met, an AssertionError will be raised.
    """

    def __init__(self, aggregate: type[A], aggregate_id: ULID | None = None):
        super().__init__()
        self.aggregate_id = aggregate_id or ULID()
        self.aggregate = aggregate(id=self.aggregate_id)
        self.commands: list[Command] = []

    async def perform_actions(self) -> None:
        # We can call _emit_ here since we are directly creating an
        # instance of the aggregate and not using an aggregate repository
        # coupled to an event store. Therefore no events are involved and
        # we have the aggregate handle tracking sequence numbers, etc.
        self._feed_starting_events()
        self._execute_commands()

    def _feed_starting_events(self) -> None:
        for event_payload in self.event_payloads:
            self.aggregate.emit(event_payload)
        # Clear uncommitted events after applying given events so they
        # don't appear in the result (only command-emitted events should)
        self.aggregate.clear_uncommitted_events()
        self.event_payloads.clear()

    def _execute_commands(self):
        for command in self.commands:
            try:
                self.aggregate.handle(command)
            except Exception as e:
                self.errors.append(e)

        self.event_payloads.extend(self.aggregate.uncommitted_events)

    def when(self, *commands: Command) -> "AggregateScenario[A]":
        self.commands.extend(commands)
        return self

    def should_emit(
        self, *event_or_event_types: type[BaseModel] | BaseModel
    ) -> "AggregateScenario[A]":
        for e in event_or_event_types:
            if isinstance(e, BaseModel):
                self.expectations.append(ContainsEventOfExactPayload(e))
            else:
                self.expectations.append(ContainsEventOfExactType(e))
        return self

    def should_emit_nothing(self) -> "AggregateScenario[A]":
        self.expectations.append(DoesNotHaveEvents())
        return self

    def should_have_state(self, predicate: Callable[[A], bool]) -> "AggregateScenario[A]":
        self.expectations.append(StateMatches(self.aggregate_id, predicate))
        return self

    def get_state(self, state_key: Any) -> A | None:
        return self.aggregate if state_key == self.aggregate_id else None
