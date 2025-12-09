from collections.abc import Callable, Coroutine
from functools import reduce
from typing import TYPE_CHECKING, Any, ClassVar

from ...domain import Aggregate, Command
from ..aggregates import AggregateRepository

if TYPE_CHECKING:
    from ..routing import MessageRouter


CommandHandler = Callable[[Command], Coroutine[Any, Any, None]]


class CommandMiddleware:
    """Base class for command middleware with annotation-based routing.

    Middleware components wrap command handlers to provide cross-cutting
    concerns like logging, validation, authentication, or transaction
    management. They follow the chain of responsibility pattern.

    Command interception is automatically routed based on method
    decorators. Use @intercepts to mark interceptor methods. The
    framework will automatically route commands to the appropriate
    methods based on their type annotations.

    By default, if no interceptor matches the command type, the
    middleware forwards to the next handler (pass-through behavior).
    """

    # Class-level routing table
    _command_router: ClassVar["MessageRouter"]

    def __init_subclass__(cls, **kwargs: object) -> None:
        """Set up command routing when a subclass is defined."""
        super().__init_subclass__(**kwargs)
        from ...routing import setup_middleware_routing

        cls._command_router = setup_middleware_routing(cls)

    async def intercept(self, command: Command, next: CommandHandler) -> None:
        """Route command to interceptor method or forward to next.

        This method is called by the CommandBus for each command. It
        uses the routing table to find an appropriate interceptor method
        based on the command type. If no interceptor is registered for
        the command type, it forwards to the next handler.

        Args:
            command: The command to intercept.
            next: The next handler in the middleware chain.
        """
        # Route to interceptor, passing next as an extra argument
        result = self._command_router.route(self, command, next)

        # If router returned None (IgnoreHandler), forward to next
        if result is None:
            await next(command)
        else:
            # Router returned coroutine (async interceptor), await it
            await result


class CommandToAggregateMap:
    @staticmethod
    def from_aggregates(
        aggregates: list[Aggregate],
    ) -> "CommandToAggregateMap":
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
        middleware: list[CommandMiddleware],
    ):
        self.root_handler = root_handler
        self.middleware = middleware
        # Build the middleware chain by reducing from right to left
        self.chain = reduce(
            lambda next, mw: lambda cmd: mw.intercept(cmd, next),
            reversed(middleware),
            self.root_handler.handle,
        )

    async def dispatch(self, command: Command) -> None:
        """Dispatch command through the middleware chain to handler.

        Args:
            command: The command to dispatch.
        """
        await self.chain(command)
