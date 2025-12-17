from collections.abc import Callable
from typing import Any, Generic, TypeVar

from pydantic import BaseModel
from ulid import ULID

from interlock.application.events import EventProcessor, Saga
from interlock.domain import Event

from .core import Scenario, StateMatches

TProcessor = TypeVar("TProcessor", bound=EventProcessor)
TSagaState = TypeVar("TSagaState", bound=BaseModel)
TSaga = TypeVar("TSaga", bound=Saga[TSagaState])

PROCESSOR_STATE_KEY = "processor_state"


class ProcessorScenario(Scenario[TProcessor], Generic[TProcessor]):
    """A scenario for testing an event processor.

    This scenario allows you to test an event processor by:
    - Given a list of events to process
    - Then a list of expectations are met (state assertions)

    Use via Application.processor_scenario() for automatic DI:

        >>> async with app.processor_scenario(AccountBalanceProjection) as scenario:
        ...     scenario.given(MoneyDeposited(...))
        ...     scenario.should_have_state(lambda p: p.repo.get_balance(id) == 100)

    Or instantiate directly for simple processors:

        >>> async with ProcessorScenario(SimpleProcessor()) as scenario:
        ...     scenario.given(SomeEvent()).should_have_state(lambda p: p.count == 1)
    """

    def __init__(self, processor: TProcessor):
        super().__init__()
        self.processor = processor

    async def perform_actions(self) -> None:
        # Wrap payloads in Event objects for handlers with Event[T] annotations
        aggregate_id = ULID()  # Use a consistent aggregate ID for test events
        for i, event_payload in enumerate(self.event_payloads, start=1):
            event = Event(
                aggregate_id=aggregate_id,
                data=event_payload,
                sequence_number=i,
            )
            try:
                await self.processor.handle(event)
            except Exception as e:
                self.errors.append(e)

    def should_have_state(
        self, predicate: Callable[[TProcessor], bool]
    ) -> "ProcessorScenario[TProcessor]":
        self.expectations.append(StateMatches(PROCESSOR_STATE_KEY, predicate))
        return self

    async def get_state(self, state_key: Any) -> TProcessor | None:
        return self.processor if state_key == PROCESSOR_STATE_KEY else None


class SagaScenario(Scenario[TSagaState], Generic[TSaga, TSagaState]):
    """A scenario for testing a saga.

    This scenario allows you to test a saga by:
    - Given a list of events to process
    - Then a list of expectations are met (state assertions)

    Use via Application.saga_scenario() for automatic DI:

        >>> async with app.saga_scenario(OrderSaga) as scenario:
        ...     scenario.given(OrderPlaced(order_id="123"))
        ...     scenario.should_have_state("123", lambda s: s.status == "placed")

    Or instantiate directly:

        >>> saga = OrderSaga(SagaStateStore.in_memory())
        >>> async with SagaScenario(saga) as scenario:
        ...     scenario.given(OrderPlaced(order_id="123"))
        ...     scenario.should_have_state("123", lambda s: s.status == "placed")
    """

    def __init__(self, saga: TSaga):
        super().__init__()
        self.saga = saga
        self.state_store = saga.state_store

    async def perform_actions(self) -> None:
        # Wrap payloads in Event objects for handlers with Event[T] annotations
        aggregate_id = ULID()  # Use a consistent aggregate ID for test events
        for i, event_payload in enumerate(self.event_payloads, start=1):
            event = Event(
                aggregate_id=aggregate_id,
                data=event_payload,
                sequence_number=i,
            )
            try:
                await self.saga.handle(event)
            except Exception as e:
                self.errors.append(e)

    def should_have_state(
        self, saga_id: str, predicate: Callable[[TSagaState], bool]
    ) -> "SagaScenario[TSaga]":
        self.expectations.append(StateMatches(saga_id, predicate))
        return self

    async def get_state(self, state_key: Any) -> TSagaState | None:
        return await self.state_store.load(state_key)
