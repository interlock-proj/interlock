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


def _should_skip_module(module_name: str) -> bool:
    """Check if a module should be skipped during scanning.

    Args:
        module_name: Base name of the module to check

    Returns:
        True if module should be skipped
    """
    return module_name.startswith("test_") or (
        module_name.startswith("_") and module_name != "__init__"
    )


def _get_module_variants(name: str) -> list[str]:
    """Get singular and plural variants of a module name.

    Args:
        name: Module name to get variants for

    Returns:
        List of name variants to try [original, plural]

    Examples:
        >>> _get_module_variants("aggregate")
        ["aggregate", "aggregates"]
        >>> _get_module_variants("services")
        ["services"]
    """
    if name.endswith("s"):
        return [name]
    return [name, name + "s"]


def _try_import_module(module_name: str) -> ModuleType | None:
    """Try to import a module, returning None if it doesn't exist.

    Args:
        module_name: Fully qualified module name

    Returns:
        Imported module or None if not found
    """
    try:
        return importlib.import_module(module_name)
    except (ImportError, ModuleNotFoundError):
        return None


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

        Supports both singular and plural forms
        (e.g., 'aggregate' and 'aggregates').
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
        for variant in _get_module_variants(subpackage):
            module_path = f"{self.package_name}.{variant}"
            module = _try_import_module(module_path)

            if module is None:
                continue

            # Yield the module itself if it's not skippable
            basename = module.__name__.split(".")[-1]
            if not _should_skip_module(basename):
                yield module

            # If it's a package, recursively scan submodules
            if hasattr(module, "__path__"):
                yield from self._scan_package_recursive(module)

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

    def _scan_package_recursive(
        self, package: ModuleType
    ) -> Iterable[ModuleType]:
        """Recursively scan a package for all submodules.

        Args:
            package: Package module to scan

        Yields:
            ModuleType: Discovered modules
        """
        if not hasattr(package, "__path__"):
            return

        for _importer, modname, is_pkg in pkgutil.iter_modules(
            package.__path__, prefix=f"{package.__name__}."
        ):
            basename = modname.split(".")[-1]
            if _should_skip_module(basename):
                continue

            try:
                module = importlib.import_module(modname)
                yield module

                if is_pkg:
                    yield from self._scan_package_recursive(module)
            except ImportError as e:
                msg = (
                    f"Failed to import module {modname} "
                    f"while scanning {package.__name__}. Error: {e}"
                )
                raise ImportError(msg) from e


class ClassScanner:
    """Extract classes from modules by type."""

    @staticmethod
    def find_subclasses(
        module: ModuleType, base_class: type[T]
    ) -> Iterable[type[T]]:
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
            >>> classes = ClassScanner.find_subclasses(module, Aggregate)
            >>> for cls in classes:
            ...     print(cls.__name__)
            BankAccount
            ShoppingCart
        """
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if _should_include_subclass(obj, name, base_class, module):
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
            if _should_include_class(obj, name, module):
                yield obj

    @staticmethod
    def get_registration_type(cls: type) -> type:
        """Get the type to register a class as for dependency injection.

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
        bases = [
            base for base in inspect.getmro(cls)
            if base not in (cls, object)
        ]

        # Find first ABC or Protocol
        for base in bases:
            if (
                inspect.isabstract(base)
                or getattr(base, "_is_protocol", False)
            ):
                return base

        # No interface found, use concrete type
        return cls


def _should_include_class(cls: type, name: str, module: ModuleType) -> bool:
    """Check if a class should be included in results.

    Args:
        cls: Class to check
        name: Name of the class
        module: Module being scanned

    Returns:
        True if class should be included
    """
    return not name.startswith("_") and cls.__module__ == module.__name__


def _should_include_subclass(
    cls: type, name: str, base_class: type, module: ModuleType
) -> bool:
    """Check if a subclass should be included in results.

    Args:
        cls: Class to check
        name: Name of the class
        base_class: Base class being searched for
        module: Module being scanned

    Returns:
        True if subclass should be included
    """
    return (
        issubclass(cls, base_class)
        and cls is not base_class
        and not name.startswith("_")
        and not inspect.isabstract(cls)
        and cls.__module__ == module.__name__
    )
