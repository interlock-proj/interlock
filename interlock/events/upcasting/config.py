"""Configuration for event upcasting behavior."""

from dataclasses import dataclass, field

from .strategies import LazyUpcastingStrategy, UpcastingStrategy


@dataclass
class UpcastingConfig:
    """Configuration for upcasting pipeline behavior.

    This configuration controls when and how event schema transformations
    are applied as your domain model evolves.

    Attributes:
        strategy: Strategy controlling when to apply upcasting transformations.
            Defaults to LazyUpcastingStrategy (upcast only on read).

    Examples:
        Default configuration (lazy upcasting):

        >>> config = UpcastingConfig()

        Eager upcasting (transform on read and write):

        >>> from interlock.events import EagerUpcastingStrategy
        >>> config = UpcastingConfig(strategy=EagerUpcastingStrategy())

    See Also:
        - LazyUpcastingStrategy: Upcast only when reading (recommended default)
        - EagerUpcastingStrategy: Upcast on both read and write
    """

    strategy: UpcastingStrategy = field(default_factory=LazyUpcastingStrategy)
