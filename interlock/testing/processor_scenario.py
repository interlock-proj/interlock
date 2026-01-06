from collections.abc import Callable
from typing import Any, Generic, TypeVar, cast
from uuid import uuid4

from pydantic import BaseModel

from interlock.application.events import EventProcessor, Saga
from interlock.application.projections import Projection
from interlock.domain import Event, Query

from .core import Scenario, StateMatches

# Type alias for predicates that can receive None
NullablePredicate = Callable[[Any | None], bool]

TProcessor = TypeVar("TProcessor", bound=EventProcessor)
TProjection = TypeVar("TProjection", bound=Projection)
TSagaState = TypeVar("TSagaState", bound=BaseModel)
TSaga = TypeVar("TSaga", bound="Saga[Any]")
TResponse = TypeVar("TResponse")

PROCESSOR_STATE_KEY = "processor_state"


class ProcessorScenario(Scenario[Any], Generic[TProcessor]):
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
        aggregate_id = uuid4()  # Use a consistent aggregate ID for test events
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
        self.expectations.append(
            StateMatches[Any](PROCESSOR_STATE_KEY, cast("NullablePredicate", predicate))
        )
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
        aggregate_id = uuid4()  # Use a consistent aggregate ID for test events
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
    ) -> "SagaScenario[TSaga, TSagaState]":
        self.expectations.append(
            StateMatches[TSagaState](saga_id, cast("NullablePredicate", predicate))
        )
        return self

    async def get_state(self, state_key: Any) -> TSagaState | None:
        result = await self.state_store.load(state_key)
        return cast("TSagaState | None", result)


PROJECTION_STATE_KEY = "projection_state"


class ProjectionScenario(Scenario[Any], Generic[TProjection]):
    """A scenario for testing a projection.

    Projections combine event handling with query handling. This scenario
    allows you to test both capabilities:
    - Given: Process events to build read model state
    - When: Execute queries against the projection
    - Then: Assert on query results or projection state

    Use via Application.projection_scenario() for automatic DI:

        >>> async with app.projection_scenario(UserProjection) as scenario:
        ...     scenario.given(UserCreated(user_id=id, name="Alice"))
        ...     result = await scenario.when(GetUserById(user_id=id))
        ...     assert result.name == "Alice"

    Or instantiate directly:

        >>> async with ProjectionScenario(UserProjection()) as scenario:
        ...     scenario.given(UserCreated(user_id=id, name="Alice"))
        ...     scenario.should_have_state(lambda p: len(p.users) == 1)
    """

    def __init__(self, projection: TProjection):
        super().__init__()
        self.projection = projection
        self.query_results: list[Any] = []

    async def perform_actions(self) -> None:
        # Wrap payloads in Event objects for handlers with Event[T] annotations
        aggregate_id = uuid4()
        for i, event_payload in enumerate(self.event_payloads, start=1):
            event = Event(
                aggregate_id=aggregate_id,
                data=event_payload,
                sequence_number=i,
            )
            try:
                await self.projection.handle(event)
            except Exception as e:
                self.errors.append(e)

    async def when(self, query: Query[TResponse]) -> TResponse:
        """Execute a query against the projection.

        This method processes any pending events first, then executes
        the query and returns the result.

        Args:
            query: The query to execute.

        Returns:
            The query result.
        """
        # Process any pending events first
        await self.perform_actions()
        self.event_payloads = []  # Clear processed events

        # Execute the query
        result = await self.projection.query(query)
        self.query_results.append(result)
        return result

    def should_have_state(
        self, predicate: Callable[[TProjection], bool]
    ) -> "ProjectionScenario[TProjection]":
        """Assert that the projection state matches a predicate.

        Args:
            predicate: A function that receives the projection and returns
                True if the state is valid.

        Returns:
            Self for chaining.
        """
        self.expectations.append(
            StateMatches[Any](PROJECTION_STATE_KEY, cast("NullablePredicate", predicate))
        )
        return self

    async def get_state(self, state_key: Any) -> TProjection | None:
        if state_key == PROJECTION_STATE_KEY:
            return self.projection
        return None
