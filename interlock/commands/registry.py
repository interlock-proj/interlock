"""Registry for command types."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .command import Command


class CommandTypeRegistry:
    """Registry for command types.

    Tracks all command types registered with the application.
    Used by CommandBus factory to map commands to repositories.

    Examples:
        >>> registry = CommandTypeRegistry()
        >>> registry.register(DepositMoney)
        >>> registry.register(WithdrawMoney)
        >>> commands = registry.get_all()
    """

    def __init__(self):
        self._commands: set[type[Command]] = set()

    def register(self, command_type: type["Command"]) -> None:
        """Register a command type.

        Args:
            command_type: Command type to register
        """
        self._commands.add(command_type)

    def get_all(self) -> set[type["Command"]]:
        """Get all registered command types.

        Returns:
            Set of registered command types

        Examples:
            >>> commands = registry.get_all()
            >>> for cmd in commands:
            ...     print(f"Registered: {cmd.__name__}")
        """
        return self._commands
