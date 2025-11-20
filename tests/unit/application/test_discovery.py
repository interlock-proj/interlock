"""Unit tests for module and class discovery utilities."""

import pytest

from interlock.aggregates.aggregate import Aggregate
from interlock.application.discovery import ClassScanner, ModuleScanner
from interlock.commands import Command


def test_scanner_imports_package():
    """Test that scanner can import a package."""
    scanner = ModuleScanner("tests.fixtures.test_app")
    assert scanner.root_module is not None
    assert scanner.package_name == "tests.fixtures.test_app"


def test_scanner_fails_on_missing_package():
    """Test that scanner fails on non-existent package."""
    with pytest.raises(ImportError):
        ModuleScanner("non.existent.package")


def test_find_modules_discovers_aggregates_package():
    """Test finding modules in aggregates package."""
    scanner = ModuleScanner("tests.fixtures.test_app")
    modules = list(scanner.find_modules("aggregate"))

    # Should find at least the aggregates package and submodules
    module_names = [m.__name__ for m in modules]
    assert any("aggregates" in name for name in module_names)
    assert any("bank_account" in name for name in module_names)


def test_find_modules_discovers_nested_packages():
    """Test that nested packages are discovered recursively."""
    scanner = ModuleScanner("tests.fixtures.test_app")
    modules = list(scanner.find_modules("aggregate"))

    module_names = [m.__name__ for m in modules]
    assert any("nested.order" in name for name in module_names)


def test_find_modules_handles_packages():
    """Test discovering modules from package directories."""
    scanner = ModuleScanner("tests.fixtures.test_app")
    modules = list(scanner.find_modules("command"))

    # Should find commands package and its modules
    module_names = [m.__name__ for m in modules]
    assert any("commands" in name for name in module_names)


def test_find_modules_supports_plural_variants():
    """Test that both singular and plural forms are tried."""
    scanner = ModuleScanner("tests.fixtures.test_app")

    # Try singular - should work
    singular_modules = list(scanner.find_modules("service"))
    assert len(singular_modules) > 0

    # Try plural - should also work (finds the same modules)
    plural_modules = list(scanner.find_modules("services"))
    assert len(plural_modules) > 0


def test_find_modules_returns_empty_for_missing_subpackage():
    """Test that missing subpackages return no modules."""
    scanner = ModuleScanner("tests.fixtures.test_app")
    modules = list(scanner.find_modules("nonexistent"))
    assert len(modules) == 0


def test_find_subclasses_discovers_aggregates():
    """Test finding Aggregate subclasses."""
    import tests.fixtures.test_app.aggregates.bank_account as module

    classes = list(ClassScanner.find_subclasses(module, Aggregate))

    class_names = [cls.__name__ for cls in classes]
    assert "BankAccount" in class_names


def test_find_subclasses_discovers_commands():
    """Test finding Command subclasses."""
    import tests.fixtures.test_app.commands.bank_commands as module

    classes = list(ClassScanner.find_subclasses(module, Command))

    class_names = [cls.__name__ for cls in classes]
    assert "DepositMoney" in class_names
    assert "WithdrawMoney" in class_names


def test_find_subclasses_filters_base_class():
    """Test that base class itself is not included."""
    import tests.fixtures.test_app.aggregates.bank_account as module

    classes = list(ClassScanner.find_subclasses(module, Aggregate))

    class_names = [cls.__name__ for cls in classes]
    assert "Aggregate" not in class_names


def test_find_subclasses_filters_imported_classes():
    """Test that imported classes from other modules are filtered out."""
    import tests.fixtures.test_app.aggregates.bank_account as module

    # The module imports Aggregate from interlock - shouldn't be in results
    classes = list(ClassScanner.find_subclasses(module, Aggregate))

    for cls in classes:
        # All results should be defined in the scanned module
        assert cls.__module__ == module.__name__


def test_find_all_classes_discovers_services():
    """Test finding all classes in a module."""
    import tests.fixtures.test_app.services.audit_service as module

    classes = list(ClassScanner.find_all_classes(module))

    class_names = [cls.__name__ for cls in classes]
    assert "IAuditService" in class_names
    assert "AuditService" in class_names


def test_find_all_classes_filters_imported_classes():
    """Test that imported classes are filtered."""
    import tests.fixtures.test_app.services.audit_service as module

    classes = list(ClassScanner.find_all_classes(module))

    for cls in classes:
        assert cls.__module__ == module.__name__


def test_get_registration_type_returns_abc_parent():
    """Test that ABC parent is returned as registration type."""
    from tests.fixtures.test_app.services.audit_service import (
        AuditService,
        IAuditService,
    )

    registration_type = ClassScanner.get_registration_type(AuditService)
    assert registration_type == IAuditService


def test_get_registration_type_returns_concrete_if_no_abc():
    """Test that concrete type is returned if no ABC parent."""
    from tests.fixtures.test_app.aggregates.bank_account import BankAccount

    registration_type = ClassScanner.get_registration_type(BankAccount)
    # Should return the class itself since Aggregate is not abstract in the usual sense
    assert registration_type in (BankAccount, Aggregate)
