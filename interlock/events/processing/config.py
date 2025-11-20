from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .conditions import CatchupCondition, Never
from .strategies import CatchupStrategy, NoCatchup

if TYPE_CHECKING:
    from .processor import EventProcessor


@dataclass
class ProcessorExecutionConfig:
    """Configuration for a single event processor's execution.

    This configuration determines how an EventProcessorExecutor runs
    the processor, including catchup behavior and batch processing.

    Attributes:
        condition: Condition for triggering catchup operations
        strategy: Strategy for catching up when condition is met
        batch_size: Number of events to process before checking lag

    Examples:
        Default configuration (no catchup, small batches):

        >>> config = ProcessorExecutionConfig()

        High-throughput processor with large batches:

        >>> config = ProcessorExecutionConfig(batch_size=1000)

        Processor with catchup enabled:

        >>> config = ProcessorExecutionConfig(
        ...     condition=AfterNEvents(5000),
        ...     strategy=FromReplayingEvents(),
        ...     batch_size=100
        ... )

        Processor with multiple catchup conditions:

        >>> config = ProcessorExecutionConfig(
        ...     condition=AnyOf(
        ...         AfterNEvents(10000),
        ...         AfterNAge(timedelta(minutes=5))
        ...     ),
        ...     strategy=FromReplayingEvents(),
        ...     batch_size=500
        ... )
    """

    condition: CatchupCondition = field(default_factory=Never)
    strategy: CatchupStrategy = field(default_factory=NoCatchup)
    batch_size: int = 10


class ProcessorConfigRegistry:
    """Registry mapping processor types to execution configurations.

    This registry provides a centralized place to configure processor
    execution behavior on a per-processor-type basis. It supports:
    - Default configuration for all processors
    - Per-type overrides for specific processors

    The registry is registered with the DI container and resolved when
    creating EventProcessorExecutor instances during processor execution.

    Examples:
        Create registry with defaults:

        >>> registry = ProcessorConfigRegistry()
        >>> registry.set_default(ProcessorExecutionConfig(batch_size=100))

        Register per-type overrides:

        >>> registry.register(
        ...     AccountBalanceProjection,
        ...     ProcessorExecutionConfig(
        ...         batch_size=50,
        ...         condition=AfterNEvents(1000),
        ...         strategy=FromReplayingEvents()
        ...     )
        ... )

        Retrieve configuration:

        >>> config = registry.get(AccountBalanceProjection)  # Returns override
        >>> config = registry.get(EmailNotifications)  # Returns default
    """

    def __init__(self, default: ProcessorExecutionConfig | None = None):
        """Initialize registry with optional default configuration.

        Args:
            default: Default configuration for processors without overrides.
                If None, uses ProcessorExecutionConfig with framework defaults.
        """
        self._default = default or ProcessorExecutionConfig()
        self._overrides: dict[type[EventProcessor], ProcessorExecutionConfig] = {}

    def set_default(self, config: ProcessorExecutionConfig) -> None:
        """Set the default configuration for all processors.

        Args:
            config: Configuration to use as default
        """
        self._default = config

    def register(
        self,
        processor_type: type["EventProcessor"],
        config: ProcessorExecutionConfig,
    ) -> None:
        """Register configuration for a specific processor type.

        Args:
            processor_type: The processor type to configure
            config: Configuration specific to this processor type

        Examples:
            >>> registry.register(
            ...     AccountBalanceProjection,
            ...     ProcessorExecutionConfig(batch_size=200)
            ... )
        """
        self._overrides[processor_type] = config

    def get(self, processor_type: type["EventProcessor"]) -> ProcessorExecutionConfig:
        """Get configuration for a processor type.

        Returns the registered override if available, otherwise the default.

        Args:
            processor_type: The processor type to get configuration for

        Returns:
            Configuration for the specified processor type

        Examples:
            >>> config = registry.get(AccountBalanceProjection)
        """
        return self._overrides.get(processor_type, self._default)
