"""Registry for command middleware."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...application.container import DependencyContainer
    from ..bus import CommandMiddleware
    from ..command import Command


class CommandMiddlewareRegistry:
    """Registry for command middleware.

    Manages middleware registration and handles type resolution via DI container.
    Middleware is applied to commands based on type hierarchy matching.

    Examples:
        >>> registry = CommandMiddlewareRegistry(container)
        >>> registry.register(LoggingMiddleware, Command)
        >>> registry.register(AuditMiddleware(), DepositMoney)
        >>> middlewares = registry.resolve_all()
    """

    def __init__(self, container: "DependencyContainer"):
        """Initialize registry with DI container.

        Args:
            container: Container for resolving middleware types
        """
        self._container = container
        self._middlewares: list[
            tuple[CommandMiddleware | type[CommandMiddleware], type[Command]]
        ] = []

    def register(
        self,
        middleware: "CommandMiddleware | type[CommandMiddleware]",
        command_type: type["Command"],
    ) -> None:
        """Register middleware for a command type.

        Args:
            middleware: Middleware instance or class (types resolved via DI)
            command_type: Command type this middleware applies to
        """
        self._middlewares.append((middleware, command_type))

    def resolve_all(self) -> list[tuple["CommandMiddleware", type["Command"]]]:
        """Resolve all middleware types to instances.

        Uses DI container to resolve middleware types, returning fully
        instantiated middleware with dependencies injected.

        Returns:
            List of (middleware_instance, command_type) tuples

        Examples:
            >>> middlewares = registry.resolve_all()
            >>> for middleware, cmd_type in middlewares:
            ...     print(f"{middleware} applies to {cmd_type}")
        """
        resolved = []
        for middleware, cmd_type in self._middlewares:
            if isinstance(middleware, type):
                # Resolve type via DI - dependencies injected
                instance = self._container.resolve(middleware)
                resolved.append((instance, cmd_type))
            else:
                # Already an instance
                resolved.append((middleware, cmd_type))
        return resolved
