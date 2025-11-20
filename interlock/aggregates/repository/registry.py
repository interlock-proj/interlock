"""Registry for aggregate repositories."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...commands import Command
    from ..aggregate import Aggregate
    from .repository import AggregateRepository


class AggregateRepositoryRegistry:
    """Registry for aggregate repositories.

    Stores created repositories and provides command→repository mapping
    via introspection of command types.

    Examples:
        >>> registry = AggregateRepositoryRegistry()
        >>> registry.register(BankAccount, account_repository)
        >>> repo = registry.get(BankAccount)
        >>> repo = registry.get_for_command(DepositMoney)
    """

    def __init__(self):
        self._repositories: dict[type[Aggregate], AggregateRepository] = {}

    def register(
        self, aggregate_type: type["Aggregate"], repository: "AggregateRepository"
    ) -> None:
        """Register a repository for an aggregate type.

        Args:
            aggregate_type: The aggregate type
            repository: The repository instance for this aggregate
        """
        self._repositories[aggregate_type] = repository

    def get(self, aggregate_type: type["Aggregate"]) -> "AggregateRepository":
        """Get repository for an aggregate type.

        Args:
            aggregate_type: The aggregate type

        Returns:
            The repository for this aggregate

        Raises:
            KeyError: If aggregate type not registered
        """
        return self._repositories[aggregate_type]

    def _build_command_to_aggregate_map(
        self,
    ) -> dict[type["Command"], type["Aggregate"]]:
        """Build mapping of command types to aggregate types by introspecting registered aggregates.

        Scans all registered aggregate types for methods decorated with @handles_command
        and builds a reverse mapping from command type to aggregate type.

        Returns:
            Dictionary mapping command types to their handling aggregate types

        Examples:
            >>> mapping = registry._build_command_to_aggregate_map()
            >>> mapping[DepositMoney]  # Returns BankAccount
        """
        command_to_aggregate: dict[type[Command], type[Aggregate]] = {}

        # Iterate through all registered aggregates
        for aggregate_type in self._repositories:
            # Scan all methods in the aggregate class hierarchy
            for klass in aggregate_type.__mro__:
                for value in klass.__dict__.values():
                    # Check if method has the @handles_command marker
                    if hasattr(value, "_handles_command_type"):
                        command_type = value._handles_command_type
                        command_to_aggregate[command_type] = aggregate_type

        return command_to_aggregate

    def get_for_command(self, command_type: type["Command"]) -> "AggregateRepository":
        """Get repository for a command type by introspecting registered aggregates.

        Scans all registered aggregates to find which one handles the given command type,
        then returns that aggregate's repository.

        Args:
            command_type: Command type to find repository for

        Returns:
            Repository for the command's target aggregate

        Raises:
            KeyError: If command's aggregate type not registered or no aggregate
                handles this command

        Examples:
            >>> repo = registry.get_for_command(DepositMoney)
        """
        command_to_aggregate = self._build_command_to_aggregate_map()
        aggregate_type = command_to_aggregate[command_type]
        return self._repositories[aggregate_type]

    def get_all_for_commands(
        self, command_types: set[type["Command"]]
    ) -> dict[type["Command"], "AggregateRepository"]:
        """Map all command types to their repositories.

        Args:
            command_types: Set of command types to map

        Returns:
            Dictionary mapping command types to repositories

        Examples:
            >>> mappings = registry.get_all_for_commands({DepositMoney, WithdrawMoney})
        """
        # Build the mapping once for all commands
        command_to_aggregate = self._build_command_to_aggregate_map()

        # Map requested command types to their repositories
        return {
            cmd_type: self._repositories[command_to_aggregate[cmd_type]]
            for cmd_type in command_types
        }
