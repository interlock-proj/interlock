from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Mapping
from types import TracebackType
from typing import (
    Any,
    Generic,
    TypeVar,
    cast,
)

from pydantic import BaseModel
from typing_extensions import Self

from interlock.domain import Event

TState = TypeVar("TState", bound=BaseModel)


class Result(Generic[TState]):
    def __init__(
        self,
        events: list[BaseModel],
        errors: list[Exception],
        states: Mapping[Any, TState | None] | None = None,
    ):
        self.events = events
        self.errors = errors
        self.states = states if states is not None else {}

    def _get_event_data(self, event: BaseModel) -> BaseModel:
        """Extract event data from Event wrapper or return the event itself."""
        if isinstance(event, Event):
            # Event.data is the payload which is a BaseModel
            return cast("BaseModel", event.data)
        return event

    def contains_event_of_type(self, event_type: type[BaseModel]) -> bool:
        return any(isinstance(self._get_event_data(event), event_type) for event in self.events)

    def contains_event(self, payload: BaseModel) -> bool:
        return any(self._get_event_data(event) == payload for event in self.events)

    def contains_error_of_type(self, error_type: type[Exception]) -> bool:
        return any(isinstance(error, error_type) for error in self.errors)

    def state_matches(self, state_key: Any, predicate: Callable[[TState | None], bool]) -> bool:
        if state_key in self.states:
            state = self.states[state_key]
            return predicate(state)
        return False


class Expectation(ABC):
    @abstractmethod
    def was_met(self, result: Result) -> bool:
        pass

    @abstractmethod
    def describe(self) -> str:
        pass

    def requires_state(self) -> Iterable[Any]:
        return []

    def assert_met(self, result: Result) -> None:
        if not self.was_met(result):
            raise AssertionError(f"Expectation not met: {self.describe()}")


class ContainsEventOfExactPayload(Expectation):
    def __init__(self, payload: BaseModel):
        self.payload = payload

    def was_met(self, result: Result) -> bool:
        return result.contains_event(self.payload)

    def describe(self) -> str:
        return f"should contain event with payload {self.payload}"


class ContainsEventOfExactType(Expectation):
    def __init__(self, event_type: type[BaseModel]):
        self.event_type = event_type

    def was_met(self, result: Result) -> bool:
        return result.contains_event_of_type(self.event_type)

    def describe(self) -> str:
        return f"should contain event of type {self.event_type.__name__}"


class ContainsErrorOfExactType(Expectation):
    def __init__(self, error_type: type[Exception]):
        self.error_type = error_type

    def was_met(self, result: Result) -> bool:
        return result.contains_error_of_type(self.error_type)

    def describe(self) -> str:
        return f"should contain error of type {self.error_type.__name__}"


class DoesNotHaveEvents(Expectation):
    def was_met(self, result: Result) -> bool:
        return len(result.events) == 0

    def describe(self) -> str:
        return "should not emit any events"


class StateMatches(Expectation):
    def __init__(self, state_key: Any, predicate: Callable[[TState | None], bool]):
        self.state_key = state_key
        self.predicate = predicate

    def was_met(self, result: Result) -> bool:
        return result.state_matches(self.state_key, self.predicate)

    def describe(self) -> str:
        return f"should match state {self.state_key} with predicate"

    def requires_state(self) -> Iterable[Any]:
        return [self.state_key]


class Scenario(ABC, Generic[TState]):
    def __init__(self):
        self.event_payloads: list[BaseModel] = []
        self.expectations: list[Expectation] = []
        self.errors: list[Exception] = []

    async def get_state(self, state_key: Any) -> TState | None:
        pass

    async def build_result(self) -> Result[TState]:
        states = {
            state_key: await self.get_state(state_key)
            for expectation in self.expectations
            for state_key in expectation.requires_state()
        }
        return Result(
            events=self.event_payloads,
            errors=self.errors,
            states=states,
        )

    def assert_expectations(self, result: Result[TState]) -> None:
        for expectation in self.expectations:
            expectation.assert_met(result)

    def given(self, *events: BaseModel) -> Self:
        self.event_payloads.extend(events)
        return self

    def given_no_events(self) -> Self:
        self.event_payloads = []
        return self

    def should_raise(self, error_type: type[Exception]) -> Self:
        self.expectations.append(ContainsErrorOfExactType(error_type))
        return self

    @abstractmethod
    async def perform_actions(self) -> None:
        pass

    async def execute_scenario(self) -> None:
        await self.perform_actions()
        result = await self.build_result()
        self.assert_expectations(result)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc_type is not None and exc_value is not None:
            raise exc_value
        else:
            await self.execute_scenario()
