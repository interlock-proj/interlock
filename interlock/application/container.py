import inspect
from abc import ABC, abstractmethod
from collections import OrderedDict
from collections.abc import Callable
from itertools import chain
from typing import Any, Generic, Optional, TypeVar, cast, get_origin

T = TypeVar("T")


class DependencyNotFoundError(Exception):
    @classmethod
    def from_type(cls, dependency_type: type[T]) -> "DependencyNotFoundError":
        if hasattr(dependency_type, "__name__"):
            return cls(f"Dependency {dependency_type.__name__} not found")
        else:
            return cls(f"Dependency {dependency_type} not found")


class DependencyCircularReferenceError(Exception):
    @classmethod
    def from_container(cls, container: "DependencyContainer") -> "DependencyCircularReferenceError":
        return cls(f"Circular reference detected while resolving {container.all_resolving()}")


class Dependency(ABC, Generic[T]):
    @abstractmethod
    def resolve(self, container: "DependencyContainer") -> T:
        pass


class FactoryDependency(Dependency[T]):
    def __init__(self, factory: Callable[..., T]):
        self.factory = factory

    def resolve(self, container: "DependencyContainer") -> T:
        return self.factory(**self.get_dependencies(container))

    def get_dependencies(self, container: "DependencyContainer") -> dict[str, Any]:
        return {
            k: container.resolve(v.annotation)
            for k, v in inspect.signature(self.factory).parameters.items()
            if v.annotation is not inspect.Parameter.empty and v.default is inspect.Parameter.empty
        }


class SingletonDependency(Dependency[T]):
    def __init__(self, factory: FactoryDependency[T]):
        self.factory = factory
        self.instance: T | None = None
        self._resolving: bool = False

    def resolve(self, container: "DependencyContainer") -> T:
        if self._resolving:
            raise DependencyCircularReferenceError.from_container(container)

        if self.instance is None:
            self._resolving = True
            self.instance = self.factory.resolve(container)
            self._resolving = False
        return self.instance


class DependencyContainer:
    def __init__(self, parent: Optional["DependencyContainer"] = None):
        self.dependencies: dict[type, Dependency[Any]] = {}
        self.parent = parent

    def child(self) -> "DependencyContainer":
        return DependencyContainer(self)

    def all_resolving(self) -> list[type]:
        return [
            k for k in self.dependencies if getattr(self.dependencies[k], "_resolving", False)
        ] + (self.parent.all_resolving() if self.parent else [])

    def resolve(self, dependency_type: type[T]) -> T:
        # First check ourselves for the dependency and then fall back to the
        # parent container if it exists.
        if dependency_type in self.dependencies:
            return cast("T", self.dependencies[dependency_type].resolve(self))

        # If the dependency is a generic type (e.g., AggregateFactory[A]),
        # try to resolve using the origin type (e.g., AggregateFactory)
        origin = get_origin(dependency_type)
        if origin is not None and origin in self.dependencies:
            return cast("T", self.dependencies[origin].resolve(self))

        if self.parent is not None:
            return self.parent.resolve(dependency_type)

        # If we get here, the dependency was not found in this container or
        # any parent containers so we raise an error because we cannot
        # resolve it.
        raise DependencyNotFoundError.from_type(dependency_type)

    def register(
        self,
        dependency_type: type[T],
        dependency: Dependency[T],
    ) -> None:
        self.dependencies[dependency_type] = dependency

    def register_factory(
        self,
        dependency_type: type[T],
        factory: Callable[..., T],
    ) -> None:
        self.register(dependency_type, FactoryDependency(factory))

    def register_singleton(
        self, dependency_type: type[T], factory: Callable[..., T] | None = None
    ) -> None:
        factory_dependency = FactoryDependency(factory or dependency_type)
        self.register(dependency_type, SingletonDependency(factory_dependency))


class ContextualBinding:
    def __init__(self, container: "DependencyContainer"):
        self.container = container
        self.type_to_child_container: dict[type | None, DependencyContainer] = OrderedDict()

    def container_for(self, context: type | None = None) -> "DependencyContainer":
        if context not in self.type_to_child_container:
            self.type_to_child_container[context] = self.container.child()
        return self.type_to_child_container[context]

    def resolve(self, type_to_resolve: type[T], context: type | None = None) -> T:
        context = context or type_to_resolve
        return self.container_for(context).resolve(type_to_resolve)

    def resolve_all_of_type(self, base: type[T]) -> list[T]:
        return [self.resolve(t) for t in self.all_of_type(base)]

    def all_of_type(self, base: type[T]) -> list[type[T]]:
        return [
            c
            for c in chain(self.type_to_child_container.keys(), self.container.dependencies.keys())
            if c is not None and issubclass(c, base)
        ]

    def resolve_all(self) -> list[T]:
        # Resolve all dependencies registered in the root container
        return [dep.resolve(self.container) for dep in self.container.dependencies.values()]
