"""Command bus and routing infrastructure."""

from collections.abc import Callable, Coroutine
from typing import Any, TypeVar, cast

from ...domain import Aggregate, Command
from ..aggregates import AggregateRepository
from ..middleware import Handler, Middleware

T = TypeVar("T")

CommandHandler = Callable[[Command[Any]], Coroutine[Any, Any, Any]]

# Backward compatibility alias
CommandMiddleware = Middleware


class CommandToAggregateMap:
    @staticmethod
    def from_aggregates(
        aggregates: list[type[Aggregate]],
    ) -> "CommandToAggregateMap":
        map = CommandToAggregateMap()
        for aggregate in aggregates:
            map.add(aggregate)
        return map

    def __init__(self) -> None:
        self.command_to_aggregate_map: dict[type[Command[Any]], type[Aggregate]] = {}

    def add(self, aggregate_type: type[Aggregate]) -> None:
        for value in aggregate_type.__dict__.values():
            if hasattr(value, "_handles_command_type"):
                command_type = value._handles_command_type
                self.command_to_aggregate_map[command_type] = aggregate_type

    def get(self, command_type: type[Command[Any]]) -> type[Aggregate]:
        return self.command_to_aggregate_map[command_type]


class AggregateToRepositoryMap:
    @staticmethod
    def from_repositories(
        repositories: list[AggregateRepository[Any]],
    ) -> "AggregateToRepositoryMap":
        map = AggregateToRepositoryMap()
        for repository in repositories:
            map.add(repository)
        return map

    def __init__(self) -> None:
        self.aggregate_to_repository_map: dict[type[Aggregate], AggregateRepository[Any]] = {}

    def add(self, repository: AggregateRepository[Any]) -> None:
        self.aggregate_to_repository_map[repository.aggregate_type] = repository

    def get(self, aggregate_type: type[Aggregate]) -> AggregateRepository[Any]:
        return self.aggregate_to_repository_map[aggregate_type]


class DelegateToAggregate:
    def __init__(
        self,
        command_to_aggregate_map: CommandToAggregateMap,
        aggregate_to_repository_map: AggregateToRepositoryMap,
    ):
        self.command_to_aggregate_map = command_to_aggregate_map
        self.aggregate_to_repository_map = aggregate_to_repository_map

    async def handle(self, command: Command[T]) -> T:
        aggregate_type = self.command_to_aggregate_map.get(type(command))
        repository = self.aggregate_to_repository_map.get(aggregate_type)
        async with repository.acquire(command.aggregate_id) as aggregate:
            result: T = aggregate.handle(command)
            return result


class CommandBus:
    """Command bus for dispatching commands through middleware.

    The CommandBus manages the middleware chain and delegates commands
    to the appropriate aggregate for handling. Middleware is applied in
    registration order, with each middleware deciding via annotation-
    based routing whether to intercept a command.

    Args:
        root_handler: The final handler that delegates to aggregates.
        middleware: List of middleware to apply (in order).
    """

    def __init__(
        self,
        root_handler: DelegateToAggregate,
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

    async def dispatch(self, command: Command[T]) -> T:
        """Dispatch command through the middleware chain to handler.

        Args:
            command: The command to dispatch.

        Returns:
            The result from the command handler.
        """
        result: T = await self.chain(command)
        return result
