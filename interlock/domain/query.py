"""Query base class for the read side of CQRS.

Queries represent requests for data and are dispatched to projections.
Unlike commands, queries do not mutate state - they return data.
"""

from typing import Generic, TypeVar

from pydantic import BaseModel, Field
from ulid import ULID

TResponse = TypeVar("TResponse")


class Query(BaseModel, Generic[TResponse]):
    """Base class for all queries in the system.

    Queries represent requests for data and are dispatched to projections.
    Each query is generic over its response type, providing type safety
    for query handlers.

    Unlike commands, queries:
    - Do not mutate state
    - Return typed responses
    - Are routed to projections (not aggregates)

    Type Parameters:
        TResponse: The type returned by query handlers for this query

    Attributes:
        query_id: Unique identifier for this query instance.
        correlation_id: Optional correlation ID for distributed tracing.
        causation_id: Optional ID of what caused this query.

    Examples:
        Define a query with a typed response:

        >>> class GetUserById(Query[UserProfile]):
        ...     user_id: ULID
        >>>
        >>> class GetUserByEmail(Query[ULID | None]):
        ...     email: str
        >>>
        >>> # Query handlers must return the declared response type
        >>> class UserProjection(Projection):
        ...     @handles_query
        ...     async def get_user_by_id(self, query: GetUserById) -> UserProfile:
        ...         return self.users[query.user_id]
    """

    query_id: ULID = Field(default_factory=ULID)
    correlation_id: ULID | None = None
    causation_id: ULID | None = None

