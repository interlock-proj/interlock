from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Generic, TypeVar

from ..aggregates import AggregateRepository, AggregateRepositoryRegistry
from .command import Command
from .registry import CommandTypeRegistry

if TYPE_CHECKING:
    from .middleware import CommandMiddlewareRegistry

T = TypeVar("T", bound=Command)


class CommandHandler(ABC, Generic[T]):
    """Abstract base class for command handlers.

    Command handlers contain the business logic for processing commands. Each handler
    is responsible for a specific command type and implements the handle method.

    Type Parameters:
        T: The type of command this handler processes (must inherit from Command).
    """

    @abstractmethod
    async def handle(self, command: T) -> None:
        """Process the given command.

        Args:
            command: The command to process.
        """
        ...


class CommandMiddleware(ABC, Generic[T]):
    """Abstract base class for command middleware.

    Middleware components wrap command handlers to provide cross-cutting concerns
    like logging, validation, authentication, or transaction management. They follow
    the chain of responsibility pattern.

    Type Parameters:
        T: The type of command this middleware processes (must inherit from Command).
    """

    @abstractmethod
    async def handle(self, command: T, next: CommandHandler[T]) -> None:
        """Process the command and optionally invoke the next handler in the chain.

        Args:
            command: The command to process.
            next: The next handler in the middleware chain.
        """
        ...


class HandleWithMiddleware(CommandHandler[T]):
    """Command handler decorator that applies middleware to an inner handler.

    Wraps an existing command handler with middleware functionality, allowing
    cross-cutting concerns to be applied to command processing.

    Attributes:
        inner: The wrapped command handler.
        middleware: The middleware to apply to the handler.
    """

    __slots__ = ("inner", "middleware")

    def __init__(self, inner: CommandHandler[T], middleware: CommandMiddleware[T]):
        """Initialize the middleware-wrapped handler.

        Args:
            inner: The command handler to wrap.
            middleware: The middleware to apply.
        """
        self.inner = inner
        self.middleware = middleware

    async def handle(self, command: T) -> None:
        """Handle the command by passing it through the middleware chain.

        Args:
            command: The command to process.

        Returns:
            The result of the middleware and handler execution.
        """
        await self.middleware.handle(command, self.inner)


class DelegateToAggregate(CommandHandler[T]):
    """Command handler that delegates command processing to domain aggregates.

    Retrieves the appropriate aggregate instance from the repository and
    delegates the command handling to the aggregate's handle method. Uses
    the aggregate repository's context manager to ensure proper lifecycle
    management and persistence.

    Attributes:
        aggregate_repository: Repository for retrieving and persisting aggregates.
    """

    __slots__ = ("aggregate_repository",)

    def __init__(self, aggregate_repository: AggregateRepository) -> None:  # type: ignore[type-arg]
        """Initialize the delegating handler.

        Args:
            aggregate_repository: The repository for managing aggregates.
        """
        self.aggregate_repository = aggregate_repository

    async def handle(self, command: T) -> None:
        """Retrieve the aggregate and delegate command handling to it.

        Args:
            command: The command to process. The command's aggregate_id is used
                     to retrieve the correct aggregate instance.
        """
        async with self.aggregate_repository.acquire(command.aggregate_id) as aggregate:
            aggregate.handle(command)  # type: ignore[arg-type]


class CommandBus:
    """Central dispatcher for routing commands to their handlers.

    The command bus provides a single point of entry for dispatching commands
    in the system. It maps command types to their corresponding handlers and
    executes them.
    """

    def __init__(self, handlers: dict[type[Command], CommandHandler[Command]]):
        """Initialize the CommandBus with a handler mapping.

        Args:
            handlers: Mapping of command types to their handlers.
        """
        self.handlers = handlers

    @classmethod
    def create(
        cls,
        command_repositories: dict[type[Command], AggregateRepository],  # type: ignore[type-arg]
        middlewares: list[tuple[CommandMiddleware[Command], type[Command]]],
    ) -> "CommandBus":
        """Create a CommandBus with handlers for each command type.

        For each command type, creates a DelegateToAggregate handler and wraps it
        with all applicable middlewares. Middlewares are applied if the command type
        is a subclass of (or exactly matches) the middleware's target command type.

        Args:
            command_repositories: Mapping of command types to their aggregate repositories.
            middlewares: List of (middleware_instance, target_command_type) tuples.

        Returns:
            A configured CommandBus instance.
        """
        handlers: dict[type[Command], CommandHandler[Command]] = {}

        for command_type, repository in command_repositories.items():
            applicable_middlewares = (
                middleware
                for middleware, target_type in middlewares
                if issubclass(command_type, target_type)
            )

            handler: CommandHandler[Command] = DelegateToAggregate(repository)  # type: ignore[arg-type]
            for middleware in applicable_middlewares:
                handler = HandleWithMiddleware(handler, middleware)  # type: ignore[arg-type]

            handlers[command_type] = handler

        return cls(handlers)

    @classmethod
    def create_from_registries(
        cls,
        middleware_registry: "CommandMiddlewareRegistry",
        repository_registry: AggregateRepositoryRegistry,
        command_registry: CommandTypeRegistry,
    ) -> "CommandBus":
        """Factory method for creating CommandBus from registries.

        Creates CommandBus with middleware and command→repository mappings.
        All dependencies are injected by the DI container.

        Args:
            middleware_registry: Registry containing registered middleware
            repository_registry: Registry containing aggregate repositories
            command_registry: Registry containing command types

        Returns:
            Configured CommandBus instance

        Examples:
            This method is registered with the DI container and called automatically:

            >>> container.register(CommandBus, CommandBus.create_from_registries)
            >>> command_bus = container.resolve(CommandBus)
        """
        # Resolve all middleware from registry (types resolved via DI)
        resolved_middlewares = middleware_registry.resolve_all()

        # Map commands to repositories via introspection
        command_types = command_registry.get_all()
        command_repositories = repository_registry.get_all_for_commands(command_types)

        return cls.create(
            command_repositories=command_repositories, middlewares=resolved_middlewares
        )

    async def dispatch(self, command: Command) -> None:
        """Dispatch a command to its registered handler.

        Looks up the appropriate handler for the command's type and
        executes it.

        Args:
            command: The command to dispatch.

        Returns:
            The result of the command handler execution.
        """
        await self.handlers[type(command)].handle(command)
