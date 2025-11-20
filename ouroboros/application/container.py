"""Dependency injection container for Ouroboros applications.

This module provides a simple dependency injection container that supports
constructor injection by inspecting type annotations.
"""

import inspect
from collections.abc import Callable
from typing import Any, TypeVar, get_type_hints

T = TypeVar("T")


class DependencyContainer:
    """Simple dependency injection container with constructor injection.

    All dependencies are singletons - created once and reused throughout
    the application lifetime.

    The container inspects constructor signatures and automatically resolves
    dependencies based on type annotations.

    Examples:
        >>> container = DependencyContainer()
        >>> container.register(Config, Config(url="..."))
        >>> container.register(Database, PostgresDatabase)  # Will inject Config
        >>> db = container.resolve(Database)
    """

    def __init__(self) -> None:
        self._factories: dict[type, Callable[..., Any]] = {}
        self._instances: dict[type, Any] = {}

    def register(
        self,
        dependency_type: type[T],
        implementation: type[T] | T | Callable[..., T],
    ) -> None:
        """Register a dependency with the container.

        Registering a new implementation will override any previous registration
        for the same dependency type, allowing defaults to be overridden.

        Args:
            dependency_type: The type to register (interface or class)
            implementation: Can be:
                - An instance: Will be stored as-is (singleton)
                - A class: Will inspect __init__ and auto-wire dependencies
                - A factory function: Will inspect params and auto-wire dependencies

        Examples:
            Register an instance:

            >>> config = Neo4jConfig(uri="bolt://localhost:7687")
            >>> container.register(Neo4jConfig, config)

            Register a class with dependencies:

            >>> class EventStore:
            ...     def __init__(self, config: Neo4jConfig): ...
            >>> container.register(EventStore, Neo4jEventStore)

            Register a factory function:

            >>> def create_db(config: Config) -> Database:
            ...     return Database(config.url)
            >>> container.register(Database, create_db)

            Override a default:

            >>> container.register(EventDelivery, AsynchronousDelivery)  # Default
            >>> # Override with factory
            >>> container.register(EventDelivery, SynchronousDelivery.create_from_registry)
        """
        # Clear any existing registration to allow overriding
        if dependency_type in self._instances:
            del self._instances[dependency_type]
        if dependency_type in self._factories:
            del self._factories[dependency_type]

        if not callable(implementation):
            # It's an instance - store directly
            self._instances[dependency_type] = implementation
        else:
            # It's a class or factory - store for lazy resolution
            self._factories[dependency_type] = implementation

    def resolve(self, dependency_type: type[T]) -> T:
        """Resolve a dependency by type with recursive dependency resolution.

        Dependencies are resolved lazily on first access and cached for subsequent calls.

        Args:
            dependency_type: The type to resolve

        Returns:
            The resolved instance

        Raises:
            ValueError: If dependency not registered or cannot be resolved

        Examples:
            >>> event_store = container.resolve(EventStore)
        """
        # Check if already instantiated
        if dependency_type in self._instances:
            return self._instances[dependency_type]  # type: ignore[no-any-return]

        # Check if factory registered
        if dependency_type not in self._factories:
            available = ", ".join(t.__name__ for t in {**self._factories, **self._instances})
            raise ValueError(
                f"Dependency {dependency_type.__name__} not registered. Available: {available}"
            )

        # Resolve and cache
        factory = self._factories[dependency_type]
        instance = self._build_from_factory(factory)
        self._instances[dependency_type] = instance
        return instance  # type: ignore[no-any-return]

    def try_resolve(self, dependency_type: type[T]) -> T | None:
        """Try to resolve a dependency, return None if not registered.

        Args:
            dependency_type: The type to resolve

        Returns:
            The resolved instance or None

        Examples:
            >>> transport = container.try_resolve(EventTransport)
            >>> if transport is None:
            ...     transport = InMemoryEventTransport()
        """
        try:
            return self.resolve(dependency_type)
        except ValueError:
            return None

    def resolve_all(self) -> dict[type, Any]:
        """Resolve entire dependency graph with topological sort.

        Resolves all registered factories in dependency order, ensuring
        that dependencies are built before dependents.

        Returns:
            Dictionary mapping types to resolved instances

        Raises:
            ValueError: If there are circular dependencies or missing dependencies

        Examples:
            >>> container.register(Config, Config())
            >>> container.register(Database, PostgresDatabase)
            >>> container.register(EventStore, Neo4jEventStore)
            >>> resolved = container.resolve_all()
            >>> assert Config in resolved
            >>> assert Database in resolved
            >>> assert EventStore in resolved
        """
        # Topologically resolve all factories
        remaining = set(self._factories.keys())
        max_iterations = len(remaining) + 1
        iteration = 0

        while remaining and iteration < max_iterations:
            made_progress = False
            iteration += 1

            for dep_type in list(remaining):
                factory = self._factories[dep_type]
                required_deps = self._get_required_dependencies(factory)

                # Check if all dependencies are resolved
                if all(dep in self._instances for dep in required_deps):
                    # Resolve this dependency
                    self.resolve(dep_type)
                    remaining.remove(dep_type)
                    made_progress = True

            if not made_progress:
                break

        # Check for unresolved dependencies
        if remaining:
            self._raise_dependency_resolution_error(remaining)

        return dict(self._instances)

    def _build_from_factory(self, factory: Callable[..., Any]) -> Any:
        """Build instance from factory by resolving its dependencies.

        Args:
            factory: The factory function or class to build from

        Returns:
            The built instance
        """
        required_deps = self._get_required_dependencies(factory)
        kwargs: dict[str, Any] = {}

        # Get parameter info
        if inspect.isclass(factory):
            sig = inspect.signature(factory.__init__)
            params = list(sig.parameters.items())[1:]  # Skip 'self'
        else:
            sig = inspect.signature(factory)
            params = list(sig.parameters.items())

        # Filter to only required parameters (skip *args, **kwargs, defaults)
        required_params = []
        for param_name, param in params:
            if param.kind in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            ):
                continue
            if param.default is not inspect.Parameter.empty:
                continue
            required_params.append(param_name)

        # Resolve each dependency
        for param_name, dep_type in zip(required_params, required_deps, strict=True):
            kwargs[param_name] = self.resolve(dep_type)

        return factory(**kwargs)

    def _get_required_dependencies(self, factory: Callable[..., Any]) -> list[type]:
        """Extract dependency types from factory signature.

        Args:
            factory: The factory function or class to inspect

        Returns:
            List of required dependency types

        Raises:
            ValueError: If required parameters lack type annotations
        """
        if inspect.isclass(factory):
            sig = inspect.signature(factory.__init__)
            params = list(sig.parameters.items())[1:]  # Skip 'self'
            # Use get_type_hints to resolve forward references (string annotations)
            # Pass all registered types as globalns to help resolve forward references
            try:
                globalns = dict(factory.__init__.__globals__)
                # Add all registered types to help resolve forward references
                for dep_type in {**self._factories, **self._instances}:
                    globalns[dep_type.__name__] = dep_type
                type_hints = get_type_hints(factory.__init__, globalns=globalns)
            except Exception:
                # Fallback if get_type_hints fails
                type_hints = {}
        else:
            sig = inspect.signature(factory)
            params = list(sig.parameters.items())
            try:
                globalns = dict(factory.__globals__)
                # Add all registered types to help resolve forward references
                for dep_type in {**self._factories, **self._instances}:
                    globalns[dep_type.__name__] = dep_type
                type_hints = get_type_hints(factory, globalns=globalns)
            except Exception:
                type_hints = {}

        required_deps = []
        for param_name, param in params:
            # Skip *args, **kwargs, and parameters with defaults
            if param.kind in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            ):
                continue
            if param.default is not inspect.Parameter.empty:
                continue

            # Get resolved type hint (resolves forward references)
            if param_name in type_hints:
                param_type = type_hints[param_name]
            elif param.annotation is not inspect.Parameter.empty:
                # Fallback to raw annotation if get_type_hints failed
                param_type = param.annotation
            else:
                factory_name = factory.__name__ if hasattr(factory, "__name__") else str(factory)
                raise ValueError(
                    f"Parameter '{param_name}' in {factory_name} must have a type annotation "
                    "for dependency injection"
                )
            required_deps.append(param_type)

        return required_deps

    def _raise_dependency_resolution_error(self, unresolved: set[type]) -> None:
        """Raise detailed error about unresolved dependencies.

        Args:
            unresolved: Set of types that could not be resolved

        Raises:
            ValueError: With detailed information about what couldn't be resolved
        """
        error_details = []

        for dep_type in unresolved:
            factory = self._factories[dep_type]
            required_deps = self._get_required_dependencies(factory)
            missing_deps = [d for d in required_deps if d not in self._instances]

            if missing_deps:
                # Handle both type objects and string annotations (from forward references)
                missing_names = ", ".join(
                    d.__name__ if hasattr(d, "__name__") else str(d) for d in missing_deps
                )
                error_details.append(
                    f"  {dep_type.__name__} requires: {missing_names} (not registered)"
                )
            else:
                error_details.append(f"  {dep_type.__name__} (circular dependency detected)")

        raise ValueError("Cannot resolve dependencies:\n" + "\n".join(error_details))
