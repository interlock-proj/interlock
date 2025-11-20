from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...application.container import DependencyContainer
    from .pipeline import EventUpcaster


class UpcastingRegistry:
    """Registry for event upcasters.

    Manages upcaster registration and handles type resolution via DI container.

    Examples:
        >>> registry = UpcastingRegistry(container)
        >>> registry.register(AccountCreatedV1ToV2)
        >>> registry.register(OrderPlacedV1ToV2())
        >>> upcasters = registry.resolve_all()
    """

    def __init__(self, container: "DependencyContainer"):
        """Initialize registry with DI container.

        Args:
            container: Container for resolving upcaster types
        """
        self._container = container
        self._upcasters: list[EventUpcaster | type[EventUpcaster]] = []

    def register(self, upcaster: "EventUpcaster | type[EventUpcaster]") -> None:
        """Register an upcaster.

        Args:
            upcaster: Upcaster instance or class (types resolved via DI)
        """
        self._upcasters.append(upcaster)

    def resolve_all(self) -> list["EventUpcaster"]:
        """Resolve all upcaster types to instances.

        Uses DI container to resolve upcaster types, returning fully
        instantiated upcasters with dependencies injected.

        Returns:
            List of upcaster instances

        Examples:
            >>> upcasters = registry.resolve_all()
            >>> for upcaster in upcasters:
            ...     print(f"Registered: {type(upcaster).__name__}")
        """
        resolved = []
        for upcaster in self._upcasters:
            if isinstance(upcaster, type):
                # Resolve type via DI - dependencies injected
                instance = self._container.resolve(upcaster)
                resolved.append(instance)
            else:
                # Already an instance
                resolved.append(upcaster)
        return resolved
