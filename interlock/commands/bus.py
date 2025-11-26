from abc import ABC, abstractmethod
from functools import reduce
from typing import Any, Callable, Coroutine, Generic, TypeVar

from ..aggregates import Aggregate, AggregateRepository
from .command import Command

T = TypeVar("T", bound=Command)


CommandHandler = Callable[[Command], Coroutine[Any, Any, None]]


class CommandMiddleware(ABC, Generic[T]):
    """Abstract base class for command middleware.

    Middleware components wrap command handlers to provide cross-cutting
    concerns like logging, validation, authentication, or transaction
    management. They follow the chain of responsibility pattern.
    """

    @abstractmethod
    async def handle(self, command: T, next: CommandHandler) -> None:
        """Process the command and optionally invoke the next handler.

        Args:
            command: The command to process.
            next: The next handler in the middleware chain.
        """
        ...


class MiddlewareTypeFilter(ABC):
    """Abstract base class for middleware type filters."""

    @staticmethod
    def all() -> "MiddlewareTypeFilter":
        return AllMiddlewareTypeFilter()

    @staticmethod
    def of_types(*command_types: type[Command]) -> "MiddlewareTypeFilter":
        return OfTypesMiddlewareTypeFilter(command_types)

    @staticmethod
    def not_of_types(*command_types: type[Command]) -> "MiddlewareTypeFilter":
        return NotMiddlewareTypeFilter(command_types)

    @abstractmethod
    def should_apply(self, command: type[Command]) -> bool: ...


class AllMiddlewareTypeFilter(MiddlewareTypeFilter):
    def should_apply(self, command: type[Command]) -> bool:
        return True


class OfTypesMiddlewareTypeFilter(MiddlewareTypeFilter):
    def __init__(self, *command_types: type[Command]):
        self.command_types = set(command_types)

    def should_apply(self, command: type[Command]) -> bool:
        return any(
            issubclass(command, command_type) for command_type in self.command_types
        )


class NotMiddlewareTypeFilter(MiddlewareTypeFilter):
    def __init__(self, *command_types: type[Command]):
        self.command_types = set(command_types)

    def should_apply(self, command: type[Command]) -> bool:
        return not any(
            issubclass(command, command_type) for command_type in self.command_types
        )


class HandleWithMiddleware:
    """Command handler that wraps another command handler with middleware.

    This handler is responsible for wrapping another command handler
    with middleware. It will use the middleware type filter to determine
    if a middleware should be applied to the command.
    """

    def __init__(self, middleware: CommandMiddleware, filter: MiddlewareTypeFilter):
        self.middleware = middleware
        self.filter = filter

    async def handle(self, command: Command, next: CommandHandler) -> None:
        if self.filter.should_apply(type(command)):
            await self.middleware.handle(command, next)
        else:
            await next(command)


class CommandToAggregateMap:
    @staticmethod
    def from_aggregates(aggregates: list[Aggregate]) -> "CommandToAggregateMap":
        map = CommandToAggregateMap()
        for aggregate in aggregates:
            map.add(aggregate)
        return map

    def __init__(self):
        self.command_to_aggregate_map = {}

    def add(self, aggregate_type: type[Aggregate]):
        for value in aggregate_type.__dict__.values():
            if hasattr(value, "_handles_command_type"):
                command_type = value._handles_command_type
                self.command_to_aggregate_map[command_type] = aggregate_type

    def get(self, command_type: type[Command]) -> type[Aggregate]:
        return self.command_to_aggregate_map[command_type]


class AggregateToRepositoryMap:

    @staticmethod
    def from_repositories(
        repositories: list[AggregateRepository],
    ) -> "AggregateToRepositoryMap":
        map = AggregateToRepositoryMap()
        for repository in repositories:
            map.add(repository)
        return map

    def __init__(self):
        self.aggregate_to_repository_map = {}

    def add(self, repository: AggregateRepository):
        self.aggregate_to_repository_map[repository.aggregate_type] = repository

    def get(self, aggregate_type: type[Aggregate]) -> AggregateRepository:
        return self.aggregate_to_repository_map[aggregate_type]


class DelegateToAggregate:
    def __init__(
        self,
        command_to_aggregate_map: CommandToAggregateMap,
        aggregate_to_repository_map: AggregateToRepositoryMap,
    ):
        self.command_to_aggregate_map = command_to_aggregate_map
        self.aggregate_to_repository_map = aggregate_to_repository_map

    async def handle(self, command: Command) -> None:
        aggregate_type = self.command_to_aggregate_map.get(type(command))
        repository = self.aggregate_to_repository_map.get(aggregate_type)
        async with repository.acquire(command.aggregate_id) as aggregate:
            aggregate.handle(command)


class CommandBus:
    def __init__(
        self,
        root_handler: DelegateToAggregate,
        middleware_handlers: list[HandleWithMiddleware],
    ):
        self.root_handler = root_handler
        self.middleware_handlers = middleware_handlers
        self.chain = reduce(
            lambda next, handler: lambda cmd: handler.handle(cmd, next),
            self.middleware_handlers,
            self.root_handler.handle,
        )

    async def dispatch(self, command: Command) -> None:
        await self.chain(command)
