from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...application.container import DependencyContainer
    from .processor import EventProcessor


class EventProcessorRegistry:
    """Registry for event processors.

    Manages processor registration and handles type resolution via DI container.

    Examples:
        >>> registry = EventProcessorRegistry(container)
        >>> registry.register(AccountBalanceProjection)
        >>> registry.register(EmailNotificationProcessor)
        >>> processors = registry.resolve_all()
    """

    def __init__(self, container: "DependencyContainer"):
        """Initialize registry with DI container.

        Args:
            container: Container for resolving processor types
        """
        self._container = container
        self._processor_types: set[type[EventProcessor]] = set()

    def register(self, processor_type: type["EventProcessor"]) -> None:
        """Register an event processor type.

        Args:
            processor_type: Processor type to register
        """
        self._processor_types.add(processor_type)

    def resolve_all(self) -> list["EventProcessor"]:
        """Resolve all processor types to instances.

        Uses DI container to resolve processor types, returning fully
        instantiated processors with dependencies injected.

        Returns:
            List of processor instances

        Examples:
            >>> processors = registry.resolve_all()
            >>> for processor in processors:
            ...     print(f"Registered: {type(processor).__name__}")
        """
        return [self._container.resolve(proc_type) for proc_type in self._processor_types]
