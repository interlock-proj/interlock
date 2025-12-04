"""Configuration profiles for convention-based application setup.

This module provides ApplicationProfile classes that automatically discover
and register framework components from packages following naming conventions.
"""

import inspect
from abc import ABC, abstractmethod
from collections.abc import Iterable

from pydantic_settings import BaseSettings

from ..domain import Aggregate, Command
from .commands import CommandMiddleware
from .application import ApplicationBuilder
from .discovery import ClassScanner, ModuleScanner
from .events.upcasting import EventUpcaster
from .events.processing import EventProcessor

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
    """Discover and register all Aggregate subclasses in a package.

    Scans for aggregates in:
    - myapp/aggregates.py (direct file)
    - myapp/aggregate.py (singular)
    - myapp/aggregates/ (package directory)
    - myapp/aggregate/ (singular package)

    Recursively scans all subpackages.
    """

    def __init__(self, package_name: str):
        """Initialize profile for a package.

        Args:
            package_name: Package to scan (e.g., "myapp.domain")
        """
        self.scanner = ModuleScanner(package_name)

    def configure(self, builder: ApplicationBuilder) -> None:
        """Register all discovered aggregates with the builder.

        Args:
            builder: ApplicationBuilder to configure
        """
        for module in self.scanner.find_modules("aggregate"):
            for cls in ClassScanner.find_subclasses(module, Aggregate):
                builder.register_aggregate(cls)


class MiddlewareInPackage(ApplicationProfile):
    """Discover and register all CommandMiddleware subclasses in a package.

    Scans for middleware in:
    - myapp/middleware.py (direct file)
    - myapp/middlewares.py (plural)
    - myapp/middleware/ (package directory)
    - myapp/middlewares/ (plural package)

    All discovered middleware is registered to apply to all Command types.
    Middleware ordering must be handled manually if needed.

    Recursively scans all subpackages.
    """

    def __init__(self, package_name: str):
        """Initialize profile for a package.

        Args:
            package_name: Package to scan (e.g., "myapp.infrastructure")
        """
        self.scanner = ModuleScanner(package_name)

    def configure(self, builder: ApplicationBuilder) -> None:
        """Register all discovered middleware with the builder.

        Args:
            builder: ApplicationBuilder to configure
        """
        for module in self.scanner.find_modules("middleware"):
            for cls in ClassScanner.find_subclasses(module, CommandMiddleware):
                builder.register_middleware(cls)


class EventProcessorsInPackage(ApplicationProfile):
    """Discover and register all EventProcessor subclasses in a package.

    Scans for processors in:
    - myapp/processors.py / processor.py
    - myapp/projections.py / projection.py
    - myapp/processors/ / processor/ (package directories)
    - myapp/projections/ / projection/ (package directories)

    Recursively scans all subpackages.
    """

    def __init__(self, package_name: str):
        """Initialize profile for a package.

        Args:
            package_name: Package to scan (e.g., "myapp.projections")
        """
        self.scanner = ModuleScanner(package_name)

    def configure(self, builder: ApplicationBuilder) -> None:
        """Register all discovered event processors with the builder.

        Args:
            builder: ApplicationBuilder to configure
        """
        for name in ["processor", "projection"]:
            for module in self.scanner.find_modules(name):
                for cls in ClassScanner.find_subclasses(module, EventProcessor):
                    builder.register_event_processor(cls)


class ConfigsInPackage(ApplicationProfile):
    """Discover and register all BaseSettings subclasses in a package.

    Scans for configs in:
    - myapp/config.py (direct file)
    - myapp/configs.py (plural)
    - myapp/config/ (package directory)
    - myapp/configs/ (plural package)

    Requires pydantic-settings to be installed. Silently skips if not available.

    Recursively scans all subpackages.
    """

    def __init__(self, package_name: str):
        """Initialize profile for a package.

        Args:
            package_name: Package to scan (e.g., "myapp")
        """
        self.scanner = ModuleScanner(package_name)

    def configure(self, builder: ApplicationBuilder) -> None:
        """Register all discovered configs with the builder.

        Args:
            builder: ApplicationBuilder to configure
        """
        for module in self.scanner.find_modules("config"):
            for cls in ClassScanner.find_subclasses(module, BaseSettings):
                builder.register_dependency(cls)


class ServicesInPackage(ApplicationProfile):
    """Discover and register all classes in services/ as dependencies.

    Scans for services in:
    - myapp/services.py (direct file)
    - myapp/service.py (singular)
    - myapp/services/ (package directory)
    - myapp/service/ (singular package)

    All classes found are registered as dependencies, EXCEPT:
    - Framework types (Aggregate, Command, etc.)
    - Private classes (starting with _)

    Services are registered by their interface (ABC/Protocol parent) if available,
    otherwise by their concrete type.

    Recursively scans all subpackages.
    """

    def __init__(self, package_name: str):
        """Initialize profile for a package.

        Args:
            package_name: Package to scan (e.g., "myapp.services")
        """
        self.scanner = ModuleScanner(package_name)

    def configure(self, builder: ApplicationBuilder) -> None:
        """Register all discovered services with the builder.

        Args:
            builder: ApplicationBuilder to configure
        """

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
    """Discover and register all EventUpcaster subclasses in a package.

    Scans for upcasters in:
    - myapp/upcasters.py (direct file)
    - myapp/upcaster.py (singular)
    - myapp/upcasters/ (package directory)
    - myapp/upcaster/ (singular package)

    Upcasters are automatically registered with the UpcastingPipeline.
    Source and target event types are extracted from the generic type
    parameters (EventUpcaster[SourceType, TargetType]).

    Recursively scans all subpackages.
    """

    def __init__(self, package_name: str):
        """Initialize profile for a package.

        Args:
            package_name: Package to scan (e.g., "myapp.events")
        """
        self.scanner = ModuleScanner(package_name)

    def configure(self, builder: ApplicationBuilder) -> None:
        """Register all discovered upcasters with the builder.

        Args:
            builder: ApplicationBuilder to configure
        """
        for module in self.scanner.find_modules("upcaster"):
            for upcaster_cls in ClassScanner.find_subclasses(module, EventUpcaster):
                builder.register_upcaster(upcaster_cls)
