"""Projection base class for building read models with query support.

Projections combine event handling (from EventProcessor) with query handling,
providing a unified abstraction for the read side of CQRS.
"""

import inspect
from typing import TYPE_CHECKING, ClassVar, TypeVar

from ...domain import Query
from ...routing import setup_query_routing
from ..events.processing import EventProcessor

if TYPE_CHECKING:
    from ...routing import MessageRouter

T = TypeVar("T")


class Projection(EventProcessor):
    """Base class for read models that handle events and serve queries.

    Projections are the read side of CQRS. They:
    1. Subscribe to events and update their internal state (read model)
    2. Serve queries by returning data from their read model

    Unlike aggregates which enforce invariants and emit events, projections
    are optimized for reads. They maintain denormalized views that can be
    queried efficiently.

    **Event Handling:**
    Use @handles_event to mark methods that process events:

    ```python
    @handles_event
    async def on_user_created(self, event: UserCreated) -> None:
        self.users[event.user_id] = UserProfile(
            id=event.user_id,
            name=event.name,
            email=event.email
        )
    ```

    **Query Handling:**
    Use @handles_query to mark methods that serve queries:

    ```python
    @handles_query
    async def get_user(self, query: GetUserById) -> UserProfile:
        return self.users[query.user_id]
    ```

    **State Management:**
    Projections are responsible for their own state persistence.
    Inject repositories or database clients via dependency injection:

    ```python
    class UserProjection(Projection):
        def __init__(self, repository: UserRepository):
            super().__init__()
            self.repository = repository

        @handles_event
        async def on_user_created(self, event: UserCreated) -> None:
            await self.repository.save(UserProfile(...))

        @handles_query
        async def get_user(self, query: GetUserById) -> UserProfile:
            return await self.repository.get(query.user_id)
    ```

    Attributes:
        _event_router: Routing table for event handlers (inherited)
        _query_router: Routing table for query handlers

    Example:
        >>> from interlock import Projection, handles_event, handles_query
        >>> from interlock.domain import Query
        >>>
        >>> class GetUserById(Query[UserProfile]):
        ...     user_id: UUID
        >>>
        >>> class GetUserByEmail(Query[UUID | None]):
        ...     email: str
        >>>
        >>> class UserProjection(Projection):
        ...     def __init__(self):
        ...         super().__init__()
        ...         self.users: dict[UUID, UserProfile] = {}
        ...         self.email_index: dict[str, UUID] = {}
        ...
        ...     @handles_event
        ...     async def on_user_created(self, event: UserCreated) -> None:
        ...         profile = UserProfile(
        ...             id=event.user_id,
        ...             name=event.name,
        ...             email=event.email
        ...         )
        ...         self.users[event.user_id] = profile
        ...         self.email_index[event.email] = event.user_id
        ...
        ...     @handles_query
        ...     async def get_user(self, query: GetUserById) -> UserProfile:
        ...         return self.users[query.user_id]
        ...
        ...     @handles_query
        ...     async def find_by_email(self, q: GetUserByEmail) -> UUID | None:
        ...         return self.email_index.get(q.email)
    """

    # Class-level routing tables
    _event_router: ClassVar["MessageRouter"]
    _query_router: ClassVar["MessageRouter"]

    def __init_subclass__(cls, **kwargs: object) -> None:
        """Set up event and query routing when a subclass is defined."""
        super().__init_subclass__(**kwargs)
        # Event routing is set up by EventProcessor.__init_subclass__
        # We need to set up query routing here
        cls._query_router = setup_query_routing(cls)

    async def query(self, query: Query[T]) -> T:
        """Route a query to its registered handler method.

        Args:
            query: The query to handle.

        Returns:
            The query result as declared by the Query's type parameter.

        Raises:
            NotImplementedError: If no handler is registered for the query.
        """
        result = self._query_router.route(self, query)

        # If the handler is async, await the coroutine
        if inspect.iscoroutine(result):
            result = await result
        return result  # type: ignore[return-value]
