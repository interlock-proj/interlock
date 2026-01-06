import inspect
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from pydantic_settings import BaseSettings

from ..domain import Aggregate, Command
from .application import ApplicationBuilder
from .commands import CommandMiddleware
from .discovery import ClassScanner, ModuleScanner
from .events.processing import EventProcessor
from .events.upcasting import EventUpcaster

if TYPE_CHECKING:
    from collections.abc import Iterable

FRAMEWORK_BASES = (Aggregate, Command, CommandMiddleware, EventProcessor)


class ApplicationProfile(ABC):
    """Base class for application configuration profiles.

    Profiles encapsulate a set of configuration logic that can be applied
    to an ApplicationBuilder. This allows for reusable, composable
    configuration.
    """

    @staticmethod
    def convention_based(package_name: str) -> "Iterable[ApplicationProfile]":
        return [
            AggregatesInPackage(package_name),
            MiddlewareInPackage(package_name),
            EventProcessorsInPackage(package_name),
            UpcastersInPackage(package_name),
            ConfigsInPackage(package_name),
            ServicesInPackage(package_name),
        ]

    @abstractmethod
    def configure(self, builder: ApplicationBuilder) -> None:
        """Apply this profile's configuration to the builder.

        Args:
            builder: ApplicationBuilder to configure
        """
        pass


class AggregatesInPackage(ApplicationProfile):
    def __init__(self, package_name: str):
        self.scanner = ModuleScanner(package_name)

    def configure(self, builder: ApplicationBuilder) -> None:
        for module in self.scanner.find_modules("aggregate"):
            for cls in ClassScanner.find_subclasses(module, Aggregate):
                builder.register_aggregate(cls)


class MiddlewareInPackage(ApplicationProfile):
    def __init__(self, package_name: str):
        self.scanner = ModuleScanner(package_name)

    def configure(self, builder: ApplicationBuilder) -> None:
        for module in self.scanner.find_modules("middleware"):
            for cls in ClassScanner.find_subclasses(module, CommandMiddleware):
                builder.register_middleware(cls)


class EventProcessorsInPackage(ApplicationProfile):
    def __init__(self, package_name: str):
        self.scanner = ModuleScanner(package_name)

    def configure(self, builder: ApplicationBuilder) -> None:
        for name in ["processor", "projection"]:
            for module in self.scanner.find_modules(name):
                for cls in ClassScanner.find_subclasses(module, EventProcessor):
                    builder.register_event_processor(cls)


class ConfigsInPackage(ApplicationProfile):
    def __init__(self, package_name: str):
        self.scanner = ModuleScanner(package_name)

    def configure(self, builder: ApplicationBuilder) -> None:
        for module in self.scanner.find_modules("config"):
            for cls in ClassScanner.find_subclasses(module, BaseSettings):
                builder.register_dependency(cls)


class ServicesInPackage(ApplicationProfile):
    def __init__(self, package_name: str):
        self.scanner = ModuleScanner(package_name)

    def configure(self, builder: ApplicationBuilder) -> None:
        for module in self.scanner.find_modules("service"):
            for cls in ClassScanner.find_all_classes(module):
                if self._is_framework_type(cls) or inspect.isabstract(cls):
                    continue

                registration_type = ClassScanner.get_registration_type(cls)
                builder.register_dependency(registration_type, cls)

    @staticmethod
    def _is_framework_type(cls: type) -> bool:
        try:
            return issubclass(cls, FRAMEWORK_BASES)
        except TypeError:
            return False


class UpcastersInPackage(ApplicationProfile):
    def __init__(self, package_name: str):
        self.scanner = ModuleScanner(package_name)

    def configure(self, builder: ApplicationBuilder) -> None:
        for module in self.scanner.find_modules("upcaster"):
            for cls in ClassScanner.find_subclasses(module, EventUpcaster):  # type: ignore[type-abstract]
                builder.register_upcaster(cls)
