"""Module and class discovery utilities for convention-based configuration.

This module provides tools to automatically scan Python packages and discover
framework components like aggregates, commands, services, etc.
"""

import importlib
import inspect
import pkgutil
from collections.abc import Iterable
from types import ModuleType
from typing import TypeVar

T = TypeVar("T")


class ModuleScanner:
    """Recursively scan packages for Python modules.

    Handles various package structures:
    - Direct files: myapp/aggregates.py
    - Packages: myapp/aggregates/__init__.py
    - Nested packages: myapp/aggregates/banking/account.py (recursive)

    Automatically skips:
    - Test files (test_*.py)
    - Private modules (_*.py, except __init__.py)
    """

    def __init__(self, package_name: str):
        """Initialize scanner for a package.

        Args:
            package_name: Fully qualified package name (e.g., "myapp.domain")

        Raises:
            ImportError: If the package cannot be imported
        """
        self.package_name = package_name
        self.root_module = importlib.import_module(package_name)

    def find_modules(self, subpackage: str) -> Iterable[ModuleType]:
        """Find all modules in a subpackage.

        Supports both singular and plural forms (e.g., 'aggregate' and 'aggregates').
        Searches recursively through all subpackages.

        Args:
            subpackage: Name of subpackage to scan (e.g., "aggregates")

        Yields:
            ModuleType: Discovered modules

        Examples:
            >>> scanner = ModuleScanner("myapp")
            >>> for module in scanner.find_modules("aggregates"):
            ...     print(module.__name__)
            myapp.aggregates.bank_account
            myapp.aggregates.shopping_cart
        """
        # Try both singular and plural forms
        variants = [subpackage, subpackage + "s"] if not subpackage.endswith("s") else [subpackage]

        for variant in variants:
            # Try as direct module (e.g., myapp/aggregates.py)
            try:
                module_name = f"{self.package_name}.{variant}"
                module = importlib.import_module(module_name)
                if not self._should_skip_module(module):
                    yield module
            except (ImportError, ModuleNotFoundError):
                pass  # Not a module, might be a package

            # Try as package (e.g., myapp/aggregates/__init__.py and children)
            try:
                package_name = f"{self.package_name}.{variant}"
                package = importlib.import_module(package_name)

                # Yield package's __init__.py if it has classes
                if not self._should_skip_module(package):
                    yield package

                # Recursively scan submodules
                yield from self._scan_package_recursive(package)
            except (ImportError, ModuleNotFoundError):
                pass  # Neither module nor package exists

    def scan_all_modules(self) -> Iterable[ModuleType]:
        """Scan all non-private modules in the package recursively.

        Yields:
            ModuleType: All discovered modules

        Examples:
            >>> scanner = ModuleScanner("myapp")
            >>> for module in scanner.scan_all_modules():
            ...     print(module.__name__)
        """
        yield self.root_module
        yield from self._scan_package_recursive(self.root_module)

    def _scan_package_recursive(self, package: ModuleType) -> Iterable[ModuleType]:
        """Recursively scan a package for all submodules.

        Args:
            package: Package module to scan

        Yields:
            ModuleType: Discovered modules
        """
        if not hasattr(package, "__path__"):
            return  # Not a package

        for _importer, modname, is_pkg in pkgutil.iter_modules(
            package.__path__, prefix=f"{package.__name__}."
        ):
            # Skip test and private modules
            basename = modname.split(".")[-1]
            if basename.startswith("test_") or (
                basename.startswith("_") and basename != "__init__"
            ):
                continue

            try:
                module = importlib.import_module(modname)
                yield module

                # Recursively scan if it's a package
                if is_pkg:
                    yield from self._scan_package_recursive(module)
            except ImportError as e:
                # Fail fast on import errors
                raise ImportError(
                    f"Failed to import module {modname} while scanning {package.__name__}. "
                    f"Error: {e}"
                ) from e

    @staticmethod
    def _should_skip_module(module: ModuleType) -> bool:
        """Check if a module should be skipped during scanning.

        Args:
            module: Module to check

        Returns:
            True if module should be skipped
        """
        module_name = module.__name__.split(".")[-1]
        return module_name.startswith("test_") or (
            module_name.startswith("_") and module_name != "__init__"
        )


class ClassScanner:
    """Extract classes from modules by type."""

    @staticmethod
    def find_subclasses(module: ModuleType, base_class: type[T]) -> Iterable[type[T]]:
        """Find all subclasses of base_class in module.

        Filters out:
        - The base class itself
        - Abstract classes (with abstractmethod decorators)
        - Private classes (names starting with _)
        - Classes not defined in the module (imported from elsewhere)

        Args:
            module: Module to scan
            base_class: Base class to find subclasses of

        Yields:
            type[T]: Subclasses of base_class

        Examples:
            >>> module = importlib.import_module("myapp.aggregates")
            >>> for cls in ClassScanner.find_subclasses(module, Aggregate):
            ...     print(cls.__name__)
            BankAccount
            ShoppingCart
        """
        for name, obj in inspect.getmembers(module, inspect.isclass):
            # Skip if not a subclass
            if not issubclass(obj, base_class):
                continue

            # Skip the base class itself
            if obj is base_class:
                continue

            # Skip private classes
            if name.startswith("_"):
                continue

            # Skip abstract classes
            if inspect.isabstract(obj):
                continue

            # Skip classes imported from other modules
            if obj.__module__ != module.__name__:
                continue

            yield obj

    @staticmethod
    def find_all_classes(module: ModuleType) -> Iterable[type]:
        """Find all classes in module.

        Filters out:
        - Private classes (names starting with _)
        - Classes not defined in the module (imported from elsewhere)

        Args:
            module: Module to scan

        Yields:
            type: Classes defined in the module

        Examples:
            >>> module = importlib.import_module("myapp.services")
            >>> for cls in ClassScanner.find_all_classes(module):
            ...     print(cls.__name__)
            AuditService
            EmailService
        """
        for name, obj in inspect.getmembers(module, inspect.isclass):
            # Skip private classes
            if name.startswith("_"):
                continue

            # Skip classes imported from other modules
            if obj.__module__ != module.__name__:
                continue

            yield obj

    @staticmethod
    def get_registration_type(cls: type) -> type:
        """Determine the type to register a class as for dependency injection.

        Strategy:
        1. Find first ABC or Protocol parent class (interface)
        2. If none found, use the class itself (concrete type)

        This allows registering services by their interface rather than
        concrete implementation.

        Args:
            cls: Class to determine registration type for

        Returns:
            Type to use for DI registration

        Examples:
            >>> class IAuditService(ABC):
            ...     pass
            >>> class AuditService(IAuditService):
            ...     pass
            >>> ClassScanner.get_registration_type(AuditService)
            <class 'IAuditService'>

            >>> class ConcreteService:
            ...     pass
            >>> ClassScanner.get_registration_type(ConcreteService)
            <class 'ConcreteService'>
        """
        # Get all base classes (excluding object)
        bases = [base for base in inspect.getmro(cls) if base not in (cls, object)]

        # Find first ABC or Protocol
        for base in bases:
            if inspect.isabstract(base) or getattr(base, "_is_protocol", False):
                return base

        # No interface found, use concrete type
        return cls
