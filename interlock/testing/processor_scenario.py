from collections.abc import Callable
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from interlock.application.events import EventProcessor, Saga, SagaStateStore

from .core import Scenario, StateMatches

TProcessor = TypeVar("TProcessor", bound=EventProcessor)
TSagaState = TypeVar("TSagaState", bound=BaseModel)
TSaga = TypeVar("TSaga", bound=Saga[TSagaState])

PROCESSOR_STATE_KEY = "processor_state"


class ProcessorScenario(Scenario[TProcessor], Generic[TProcessor]):
    def __init__(
        self,
        processor_type: type[TProcessor],
    ):
        super().__init__()
        self.processor_type = processor_type
        self.processor = processor_type()

    async def perform_actions(self) -> None:
        for event in self.event_payloads:
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
    def __init__(
        self,
        saga_type: type[TSaga],
    ):
        super().__init__()
        self.saga_type = saga_type
        self.state_store = SagaStateStore.in_memory()
        self.saga = saga_type(self.state_store)

    async def perform_actions(self) -> None:
        for event in self.event_payloads:
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
