"""Configuration profiles for convention-based application setup.

This module provides ApplicationProfile classes that automatically discover
and register framework components from packages following naming conventions.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterable

from ..domain import Aggregate, Command
from .commands import CommandMiddleware
from .application import ApplicationBuilder
from .discovery import ClassScanner, ModuleScanner


class ApplicationProfile(ABC):
    """Base class for application configuration profiles.

    Profiles encapsulate a set of configuration logic that can be applied
    to an ApplicationBuilder. This allows for reusable, composable configuration.
    """

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
            for aggregate_cls in ClassScanner.find_subclasses(module, Aggregate):
                builder.add_aggregate(aggregate_cls)


class CommandsInPackage(ApplicationProfile):
    """Discover and register all Command subclasses in a package.

    Scans for commands in:
    - myapp/commands.py (direct file)
    - myapp/command.py (singular)
    - myapp/commands/ (package directory)
    - myapp/command/ (singular package)

    Recursively scans all subpackages.
    """

    def __init__(self, package_name: str):
        """Initialize profile for a package.

        Args:
            package_name: Package to scan (e.g., "myapp.domain")
        """
        self.scanner = ModuleScanner(package_name)

    def configure(self, builder: ApplicationBuilder) -> None:
        """Register all discovered commands with the builder.

        Args:
            builder: ApplicationBuilder to configure
        """
        for module in self.scanner.find_modules("command"):
            for command_cls in ClassScanner.find_subclasses(module, Command):
                builder.add_command(command_cls)


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
            for middleware_cls in ClassScanner.find_subclasses(module, CommandMiddleware):  # type: ignore[type-abstract]
                # Register middleware type - builder will resolve with DI
                # Apply to all commands by default
                builder.add_middleware(Command, middleware_cls)


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
        # Import here to avoid circular dependency
        from .events.processing import EventProcessor

        # Try multiple naming conventions
        for name in ["processor", "projection"]:
            for module in self.scanner.find_modules(name):
                for processor_cls in ClassScanner.find_subclasses(module, EventProcessor):
                    builder.add_event_processor(processor_cls)


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
        try:
            from pydantic_settings import BaseSettings  # type: ignore[import-not-found]
        except ImportError:
            # Skip config discovery if pydantic-settings not installed
            return

        for module in self.scanner.find_modules("config"):
            for config_cls in ClassScanner.find_subclasses(module, BaseSettings):
                builder.add_dependency(config_cls)


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
        import inspect

        for module in self.scanner.find_modules("service"):
            for service_cls in ClassScanner.find_all_classes(module):
                # Skip framework types (they're not services)
                if self._is_framework_type(service_cls):
                    continue

                # Skip abstract classes (interfaces) - we'll register their implementations
                if inspect.isabstract(service_cls):
                    continue

                # Register by interface or concrete type
                registration_type = ClassScanner.get_registration_type(service_cls)
                builder.add_dependency(registration_type, service_cls)

    @staticmethod
    def _is_framework_type(cls: type) -> bool:
        """Check if class is a framework type that shouldn't be auto-registered.

        Args:
            cls: Class to check

        Returns:
            True if class is a framework type
        """
        from .events.processing import EventProcessor

        framework_bases = (Aggregate, Command, CommandMiddleware, EventProcessor)
        try:
            return issubclass(cls, framework_bases)
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
        # Import here to avoid circular dependency
        from .events.upcasting import EventUpcaster

        for module in self.scanner.find_modules("upcaster"):
            for upcaster_cls in ClassScanner.find_subclasses(module, EventUpcaster):  # type: ignore[type-abstract]
                # Register upcaster type - builder will handle instantiation
                builder.add_upcaster(upcaster_cls)


class ApplicationProfileSet(ApplicationProfile):
    """Composite profile that runs multiple profiles in sequence.

    This is the main entry point for convention-based configuration.
    """

    @staticmethod
    def convention_based(package_name: str) -> "ApplicationProfileSet":
        """Auto-discover all components from a package using conventions.

        Expected structure (all optional, supports both singular/plural):

            myapp/
            ├── aggregates/     # or aggregate/, or aggregates.py
            ├── commands/       # or command/, or commands.py
            ├── middleware/     # or middlewares/, or middleware.py
            ├── processors/     # or processor/, projections/, etc.
            ├── services/       # or service/, or services.py
            └── config/         # or configs/, or config.py

        All directories are scanned recursively. For example:

            myapp/aggregates/banking/account.py  # Will be discovered

        Args:
            package_name: Package to scan (e.g., "myapp" or "myapp.domain")

        Returns:
            Profile set with all discovered components

        Examples:
            Simple case:

            >>> app = ApplicationBuilder().convention_based("myapp").build()

            Multiple packages:

            >>> app = (
            ...     ApplicationBuilder()
            ...     .convention_based("myapp.domain")
            ...     .convention_based("myapp.infrastructure")
            ...     .build()
            ... )

            Mix convention + manual:

            >>> app = (
            ...     ApplicationBuilder()
            ...     .convention_based("myapp")
            ...     .add_dependency(EventStore, InMemoryEventStore)  # Override
            ...     .build()
            ... )
        """
        profiles = [
            AggregatesInPackage(package_name),
            CommandsInPackage(package_name),
            MiddlewareInPackage(package_name),
            EventProcessorsInPackage(package_name),
            UpcastersInPackage(package_name),
            ConfigsInPackage(package_name),
            ServicesInPackage(package_name),
        ]
        return ApplicationProfileSet(profiles)

    def __init__(self, profiles: Iterable[ApplicationProfile]):
        """Initialize profile set with a list of profiles.

        Args:
            profiles: Profiles to apply
        """
        self.profiles = list(profiles)

    def configure(self, builder: ApplicationBuilder) -> None:
        """Apply all profiles in order.

        Args:
            builder: ApplicationBuilder to configure
        """
        for profile in self.profiles:
            profile.configure(builder)
