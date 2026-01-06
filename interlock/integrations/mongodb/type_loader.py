"""Type loading utilities for MongoDB documents.

Provides utilities for dynamically loading Python types from their
fully qualified names, used when deserializing documents back to
domain objects.
"""

import importlib
from functools import lru_cache
from typing import Any


def get_qualified_name(cls: type) -> str:
    """Get the fully qualified name of a class.

    Args:
        cls: The class to get the qualified name for.

    Returns:
        The fully qualified name (module.ClassName).

    Example:
        >>> from interlock.domain import Event
        >>> get_qualified_name(Event)
        'interlock.domain.event.Event'
    """
    return f"{cls.__module__}.{cls.__qualname__}"


@lru_cache(maxsize=256)
def load_type(qualified_name: str) -> type[Any]:
    """Load a type from its fully qualified name.

    Uses Python's import machinery to dynamically load the type.
    Results are cached for performance.

    Args:
        qualified_name: The fully qualified name (module.ClassName).

    Returns:
        The loaded type.

    Raises:
        ImportError: If the module cannot be imported or class doesn't exist.

    Example:
        >>> cls = load_type("interlock.domain.event.Event")
        >>> cls.__name__
        'Event'
    """
    module_path, _, class_name = qualified_name.rpartition(".")
    if not module_path:
        raise ImportError(f"Invalid qualified name: {qualified_name}")

    module = importlib.import_module(module_path)
    try:
        return getattr(module, class_name)  # type: ignore[no-any-return]
    except AttributeError:
        raise ImportError(
            f"Module '{module_path}' has no attribute '{class_name}'"
        ) from None
