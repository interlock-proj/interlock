"""Query bus and routing infrastructure for projections."""

from collections.abc import Callable, Coroutine
from typing import Any, TypeVar, cast

from ...domain import Query
from ..middleware import Handler, Middleware
from .projection import Projection

T = TypeVar("T")

QueryHandler = Callable[[Query[Any]], Coroutine[Any, Any, Any]]


class QueryToProjectionMap:
    """Maps query types to projection types.

    This is the query-side equivalent of CommandToAggregateMap. It scans
    projection classes for @handles_query decorated methods and builds
    a routing table.
    """

    @staticmethod
    def from_projections(
        projections: list[type[Projection]],
    ) -> "QueryToProjectionMap":
        """Build a map from a list of projection types.

        Args:
            projections: List of projection classes to scan.

        Returns:
            A configured QueryToProjectionMap.
        """
        map = QueryToProjectionMap()
        for projection in projections:
            map.add(projection)
        return map

    def __init__(self) -> None:
        self.query_to_projection_map: dict[type[Query[Any]], type[Projection]] = {}

    def add(self, projection_type: type[Projection]) -> None:
        """Register a projection's query handlers.

        Args:
            projection_type: The projection class to scan for handlers.
        """
        for value in projection_type.__dict__.values():
            if hasattr(value, "_handles_query_type"):
                query_type = value._handles_query_type
                self.query_to_projection_map[query_type] = projection_type

    def get(self, query_type: type[Query[Any]]) -> type[Projection]:
        """Get the projection type that handles a query type.

        Args:
            query_type: The query class to look up.

        Returns:
            The projection type that handles this query.

        Raises:
            KeyError: If no projection handles this query type.
        """
        return self.query_to_projection_map[query_type]


class ProjectionRegistry:
    """Registry of projection instances for query dispatch.

    This is the query-side equivalent of AggregateToRepositoryMap.
    Unlike aggregates which are loaded per-request, projections are
    typically long-lived singletons that maintain read model state.
    """

    @staticmethod
    def from_projections(
        projections: list[Projection],
    ) -> "ProjectionRegistry":
        """Build a registry from a list of projection instances.

        Args:
            projections: List of projection instances to register.

        Returns:
            A configured ProjectionRegistry.
        """
        registry = ProjectionRegistry()
        for projection in projections:
            registry.add(projection)
        return registry

    def __init__(self) -> None:
        self.projections: dict[type[Projection], Projection] = {}

    def add(self, projection: Projection) -> None:
        """Register a projection instance.

        Args:
            projection: The projection instance to register.
        """
        self.projections[type(projection)] = projection

    def get(self, projection_type: type[Projection]) -> Projection:
        """Get a projection instance by type.

        Args:
            projection_type: The projection class to look up.

        Returns:
            The registered projection instance.

        Raises:
            KeyError: If no projection of this type is registered.
        """
        return self.projections[projection_type]


class DelegateToProjection:
    """Root handler that delegates queries to the appropriate projection."""

    def __init__(
        self,
        query_to_projection_map: QueryToProjectionMap,
        projection_registry: ProjectionRegistry,
    ):
        self.query_to_projection_map = query_to_projection_map
        self.projection_registry = projection_registry

    async def handle(self, query: Query[T]) -> T:
        """Dispatch a query to its projection handler.

        Args:
            query: The query to dispatch.

        Returns:
            The query result.
        """
        projection_type = self.query_to_projection_map.get(type(query))
        projection = self.projection_registry.get(projection_type)
        return await projection.query(query)


class QueryBus:
    """Routes queries through middleware to projections.

    The QueryBus manages the middleware chain and delegates queries
    to the appropriate projection for handling. Middleware is applied
    in registration order, with each middleware deciding via annotation-
    based routing whether to intercept a query.

    Args:
        root_handler: The final handler that delegates to projections.
        middleware: List of middleware to apply (in order).
    """

    def __init__(
        self,
        root_handler: DelegateToProjection,
        middleware: list[Middleware],
    ):
        self.root_handler = root_handler
        self.middleware = middleware
        # Build the middleware chain by reducing from right to left
        # Use Handler type (BaseModel -> Coroutine) for middleware compatibility
        chain: Handler = cast("Handler", self.root_handler.handle)
        for mw in reversed(middleware):
            prev_chain = chain

            def make_chain(m: Middleware, n: Handler) -> Handler:
                return lambda msg: m.intercept(msg, n)

            chain = make_chain(mw, prev_chain)
        self.chain = chain

    async def dispatch(self, query: Query[T]) -> T:
        """Dispatch query through the middleware chain to handler.

        Args:
            query: The query to dispatch.

        Returns:
            The result from the query handler.
        """
        result: T = await self.chain(query)
        return result
