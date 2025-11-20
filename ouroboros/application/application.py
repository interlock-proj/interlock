"""Application builder and container for Ouroboros applications."""

import asyncio
from collections.abc import Callable, Sequence
from typing import Any, TypeVar

from ..aggregates import (
    Aggregate,
    AggregateRepository,
    AggregateRepositoryRegistry,
    RepositoryConfig,
    RepositoryConfigRegistry,
)
from ..commands import (
    Command,
    CommandBus,
    CommandMiddleware,
    CommandMiddlewareRegistry,
    CommandTypeRegistry,
)
from ..events import (
    AsynchronousDelivery,
    EventBus,
    EventDelivery,
    EventStore,
    EventTransport,
    InMemoryEventStore,
    InMemoryEventTransport,
    SynchronousDelivery,
    UpcastingPipeline,
)
from ..events.processing import (
    EventProcessor,
    EventProcessorExecutor,
    EventProcessorRegistry,
    ProcessorConfigRegistry,
    ProcessorExecutionConfig,
)
from ..events.upcasting import UpcastingConfig, UpcastingRegistry
from .container import DependencyContainer

T = TypeVar("T")


class Application:
    """The main application container for a CQRS/Event Sourcing application.

    The Application class serves as the central coordination point for your
    event-sourced application. It manages command dispatching, event processing,
    and the lifecycle of aggregates.

    Examples:
        Create a simple application:

        >>> from ouroboros.application import ApplicationBuilder
        >>> app = (ApplicationBuilder()
        ...     .add_aggregate(BankAccount)
        ...     .add_command(OpenAccount)
        ...     .add_dependency(EventStore, InMemoryEventStore)
        ...     .build())
        >>> await app.dispatch(OpenAccount(owner="Alice"))

    Attributes:
        command_bus: The command bus used for dispatching commands to handlers.
        event_bus: The event bus used for publishing and loading events.
    """

    def __init__(
        self,
        command_bus: CommandBus,
        event_bus: EventBus,
        dependencies: dict[type, Any],
        registered_processors: set[type[EventProcessor]],
    ):
        """Initialize the application with its core components.

        Args:
            command_bus: The command bus for dispatching commands
            event_bus: The event bus for event storage and publishing
            dependencies: Registry of all dependencies (configs, services, etc.)
            registered_processors: Set of event processor types registered with the app
        """
        self.command_bus = command_bus
        self.event_bus = event_bus
        self._dependencies = dependencies
        self._registered_processors = registered_processors

    async def dispatch(self, command: Command) -> None:
        """Dispatch a command to its handler.

        Args:
            command: The command to dispatch.

        Raises:
            ValueError: If no handler is registered for the command type.

        Examples:
            >>> await app.dispatch(DepositMoney(
            ...     account_id=account.id,
            ...     amount=Decimal("100.00")
            ... ))
        """
        await self.command_bus.dispatch(command)

    def get_dependency(self, service_type: type[T]) -> T:
        """Retrieve a registered dependency by type.

        Args:
            service_type: The type of dependency to retrieve

        Returns:
            The dependency instance

        Raises:
            ValueError: If the dependency type is not registered

        Example:
            >>> payment_gateway = app.get_dependency(PaymentGateway)
        """
        if service_type not in self._dependencies:
            available = ", ".join(t.__name__ for t in self._dependencies)
            raise ValueError(
                f"Dependency {service_type.__name__} not registered. Available types: {available}"
            )
        return self._dependencies[service_type]  # type: ignore[no-any-return]

    async def run_event_processors(self, *processors: EventProcessor) -> None:
        """Run event processors in standalone mode.

        This method creates EventProcessorExecutor instances for the specified
        processors and runs them concurrently. If no processors are provided,
        all registered processors will be run.

        This is the entry point for running event processors in a separate
        process/container from command processing (distributed architecture).

        Args:
            *processors: Event processor instances to run. If empty, runs all
                        registered processors.

        Example:
            Run specific processors:

            >>> processor1 = OrderReadModelProcessor()
            >>> processor2 = EmailNotificationProcessor()
            >>> await app.run_event_processors(processor1, processor2)

            Run all registered processors:

            >>> await app.run_event_processors()  # Runs all registered

        Note:
            This method runs indefinitely until interrupted. Event processors
            will continuously consume events from the event bus. Use asyncio
            task cancellation or Ctrl+C to stop.
        """
        # Determine which processors to run
        processors_to_run: list[EventProcessor]
        if processors:
            # Use provided processors
            processors_to_run = list(processors)
        else:
            # Resolve all registered processors from container
            processors_to_run = [
                self._dependencies[proc_type] for proc_type in self._registered_processors
            ]

        if not processors_to_run:
            raise ValueError(
                "No event processors to run. Either provide processors as arguments "
                "or register them with ApplicationBuilder.add_event_processor()"
            )

        # Get processor config registry
        config_registry = self.get_dependency(ProcessorConfigRegistry)

        # Get delivery strategy to create subscriptions
        delivery = self.get_dependency(EventDelivery)

        # Create executor for each processor with its configuration
        executors = []
        for processor in processors_to_run:
            # Get config for this processor type
            config = config_registry.get(type(processor))

            # Subscribe to all events (TODO: support stream filtering)
            subscription = await delivery.subscribe("all")
            executor = EventProcessorExecutor(
                subscription=subscription,
                processor=processor,
                condition=config.condition,
                strategy=config.strategy,
                batch_size=config.batch_size,
            )
            executors.append(executor)

        # Run all executors concurrently
        tasks = [asyncio.create_task(executor.run()) for executor in executors]
        await asyncio.gather(*tasks)


class ApplicationBuilder:
    """Builder for constructing an Ouroboros application with a fluent API.

    The ApplicationBuilder provides a fluent interface for configuring all aspects
    of your event-sourced application, including aggregates, commands, middleware,
    event processors, and dependency injection.

    All dependencies are resolved via constructor injection - the container inspects
    __init__ parameters and automatically wires dependencies.

    Examples:
        Build a simple application:

        >>> app = (ApplicationBuilder()
        ...     .add_dependency(EventStore, InMemoryEventStore)
        ...     .add_aggregate(BankAccount)
        ...     .add_command(OpenAccount)
        ...     .add_command(DepositMoney)
        ...     .build())

        Build with Neo4j and dependency injection:

        >>> app = (ApplicationBuilder()
        ...     .add_dependency(Neo4jConfig)  # Auto-loads from env
        ...     .add_dependency(Neo4jConnectionManager)  # Gets config injected
        ...     .add_dependency(EventStore, Neo4jEventStore)  # Gets manager injected
        ...     .add_aggregate(BankAccount)
        ...     .build())

        Convention-based configuration:

        >>> app = (ApplicationBuilder()
        ...     .convention_based("myapp.domain")
        ...     .build())

    Attributes:
        container: Dependency injection container
        aggregates: Set of aggregate types registered with the application
        commands: Set of command types registered with the application
        middleware_registry: Registry managing command middleware
        command_registry: Registry tracking command types
        upcasting_registry: Registry managing event upcasters
        processor_registry: Registry managing event processors
        repository_registry: Registry managing aggregate repositories
        repository_config_registry: Registry managing repository configurations
        processor_config_registry: Registry managing processor configurations
    """

    def __init__(self) -> None:
        self.container = DependencyContainer()

        # Register framework defaults
        self.container.register(EventTransport, InMemoryEventTransport())
        self.container.register(EventStore, InMemoryEventStore())
        self.container.register(UpcastingConfig, UpcastingConfig())  # Default: lazy strategy

        # Create instance registries (manage component instances/types)
        self.middleware_registry = CommandMiddlewareRegistry(self.container)
        self.command_registry = CommandTypeRegistry()
        self.upcasting_registry = UpcastingRegistry(self.container)
        self.processor_registry = EventProcessorRegistry(self.container)
        self.repository_registry = AggregateRepositoryRegistry()

        # Register instance registries with container
        self.container.register(CommandMiddlewareRegistry, self.middleware_registry)
        self.container.register(CommandTypeRegistry, self.command_registry)
        self.container.register(UpcastingRegistry, self.upcasting_registry)
        self.container.register(EventProcessorRegistry, self.processor_registry)
        self.container.register(AggregateRepositoryRegistry, self.repository_registry)

        # Create configuration registries (manage per-type configs)
        self.repository_config_registry = RepositoryConfigRegistry()
        self.processor_config_registry = ProcessorConfigRegistry()
        self.container.register(RepositoryConfigRegistry, self.repository_config_registry)
        self.container.register(ProcessorConfigRegistry, self.processor_config_registry)

        # Register factory methods (container will inject dependencies)
        self.container.register(UpcastingPipeline, UpcastingPipeline.create_from_registry)
        self.container.register(CommandBus, CommandBus.create_from_registries)
        self.container.register(
            EventBus, EventBus
        )  # EventBus constructor takes store, delivery, pipeline

        # Domain tracking (still needed for builder iteration)
        self.aggregates: set[type[Aggregate]] = set()
        self.commands: set[type[Command]] = set()

    def add_dependency(
        self,
        dependency_type: type[T],
        implementation: type[T] | T | Callable[..., T] | None = None,
    ) -> "ApplicationBuilder":
        """Register a dependency: config, service, middleware, processor, etc.

        Dependencies are resolved via constructor injection - all __init__ parameters
        must have type annotations matching registered dependencies.

        Args:
            dependency_type: The type to register
            implementation: The implementation (instance, class, or factory).
                           If None, will instantiate dependency_type directly.

        Returns:
            The application builder for chaining.

        Examples:
            Register config (auto-instantiate, loads from env):

            >>> builder.add_dependency(Neo4jConfig)

            Register config instance:

            >>> builder.add_dependency(Neo4jConfig, Neo4jConfig(uri="..."))

            Register service with dependencies auto-wired:

            >>> builder.add_dependency(EventStore, Neo4jEventStore)

            Register concrete class with dependencies auto-wired:

            >>> builder.add_dependency(AuditService)

            Register factory function:

            >>> builder.add_dependency(Database, lambda cfg: create_db(cfg))
        """
        if implementation is None:
            # Auto-instantiate (useful for configs with BaseSettings)
            if self._is_pydantic_settings(dependency_type):
                implementation = dependency_type()  # Loads from env
            else:
                implementation = dependency_type  # Will be lazily instantiated

        self.container.register(dependency_type, implementation)
        return self

    def add_aggregate(self, aggregate_type: type[Aggregate]) -> "ApplicationBuilder":
        """Add an aggregate to the application.

        Args:
            aggregate_type: The type of aggregate to add.

        Returns:
            The application builder.
        """
        self.aggregates.add(aggregate_type)
        return self

    def add_command(self, command_type: type[Command]) -> "ApplicationBuilder":
        """Add a command to the application.

        Args:
            command_type: The type of command to add.

        Returns:
            The application builder.
        """
        self.commands.add(command_type)
        self.command_registry.register(command_type)
        return self

    def add_middleware(
        self,
        command_or_commands: type[Command] | Sequence[type[Command]],
        middleware: CommandMiddleware[Command] | type[CommandMiddleware[Command]],
    ) -> "ApplicationBuilder":
        """Indicate that a given middleware should be applied to certain types of commands.

        Middleware can be either an instance or a type. If it's a type, it will be
        resolved from the dependency container with automatic dependency injection.

        Args:
            command_or_commands: The type of command or commands to apply the middleware to.
            middleware: The middleware instance or type to apply.

        Returns:
            The application builder.

        Examples:
            Middleware instance:

            >>> builder.add_middleware(DepositMoney, LoggingMiddleware("INFO"))

            Middleware type with dependency injection:

            >>> builder.add_middleware(Command, AuditMiddleware)  # Gets AuditService injected
        """
        commands: Sequence[type[Command]]
        if isinstance(command_or_commands, Sequence):
            commands = command_or_commands
        else:
            commands = [command_or_commands]

        # Register with DI container if it's a type
        self.add_dependency(middleware)

        # Register with middleware registry
        for command_type in commands:
            self.middleware_registry.register(middleware, command_type)

        return self

    def add_event_processor(self, processor_type: type) -> "ApplicationBuilder":
        """Register an event processor with dependency injection.

        Event processors will have their dependencies automatically injected
        via constructor parameters.

        Args:
            processor_type: The event processor class to register

        Returns:
            The application builder

        Example:
            >>> # Processor gets Database, CacheService, Config injected
            >>> builder.add_event_processor(AccountBalanceProjection)
        """
        # Register with DI container
        self.container.register(processor_type, processor_type)

        # Register with processor registry
        self.processor_registry.register(processor_type)
        return self

    def add_upcaster(
        self,
        upcaster: type | object,
    ) -> "ApplicationBuilder":
        """Register an event upcaster with the application.

        Upcasters transform events from old schemas to new schemas as your
        domain model evolves. The source and target event types are automatically
        extracted from the upcaster's generic type parameters.

        Args:
            upcaster: The upcaster instance or class to register

        Returns:
            The application builder

        Example:
            Register upcaster class (will be instantiated with DI):

            >>> builder.add_upcaster(AccountCreatedV1ToV2)

            Register upcaster instance:

            >>> builder.add_upcaster(AccountCreatedV1ToV2())

            Upcaster with dependencies injected:

            >>> class MyUpcaster(EventUpcaster[OldEvent, NewEvent]):
            ...     def __init__(self, config: MyConfig):
            ...         self.config = config
            ...     def upcast_payload(self, data: OldEvent) -> NewEvent:
            ...         return NewEvent(...)
            >>>
            >>> builder.add_upcaster(MyUpcaster)  # Gets config injected
        """
        # Register with container for DI if it's a type
        if isinstance(upcaster, type):
            self.container.register(upcaster, upcaster)

        # Register with upcasting registry
        self.upcasting_registry.register(upcaster)
        return self

    def configure_repository_defaults(self, config: RepositoryConfig) -> "ApplicationBuilder":
        """Set default repository configuration for all aggregates.

        This configuration will be used for any aggregate that doesn't have
        a specific override registered via configure_repository().

        Args:
            config: Default repository configuration

        Returns:
            The application builder for chaining

        Examples:
            >>> builder.configure_repository_defaults(
            ...     RepositoryConfig(
            ...         snapshot_strategy=AggregateSnapshotStrategy.every_n_events(100),
            ...         cache_strategy=CacheStrategy.never()
            ...     )
            ... )
        """
        self.repository_config_registry.set_default(config)
        return self

    def configure_repository(
        self, aggregate_type: type[Aggregate], config: RepositoryConfig
    ) -> "ApplicationBuilder":
        """Configure repository for a specific aggregate type.

        This overrides the default configuration for the specified aggregate type.

        Args:
            aggregate_type: The aggregate type to configure
            config: Repository configuration for this aggregate

        Returns:
            The application builder for chaining

        Examples:
            >>> builder.configure_repository(
            ...     BankAccount,
            ...     RepositoryConfig(
            ...         cache_strategy=CacheStrategy.always(),
            ...         snapshot_strategy=AggregateSnapshotStrategy.every_n_events(10)
            ...     )
            ... )
        """
        self.repository_config_registry.register(aggregate_type, config)
        return self

    def configure_processor_defaults(
        self, config: ProcessorExecutionConfig
    ) -> "ApplicationBuilder":
        """Set default processor execution configuration for all processors.

        This configuration will be used for any processor that doesn't have
        a specific override registered via configure_processor().

        Args:
            config: Default processor execution configuration

        Returns:
            The application builder for chaining

        Examples:
            >>> builder.configure_processor_defaults(
            ...     ProcessorExecutionConfig(
            ...         batch_size=100,
            ...         condition=AfterNEvents(5000),
            ...         strategy=FromReplayingEvents()
            ...     )
            ... )
        """
        self.processor_config_registry.set_default(config)
        return self

    def configure_processor(
        self, processor_type: type[EventProcessor], config: ProcessorExecutionConfig
    ) -> "ApplicationBuilder":
        """Configure execution for a specific event processor type.

        This overrides the default configuration for the specified processor type.

        Args:
            processor_type: The processor type to configure
            config: Execution configuration for this processor

        Returns:
            The application builder for chaining

        Examples:
            >>> builder.configure_processor(
            ...     AccountBalanceProjection,
            ...     ProcessorExecutionConfig(
            ...         batch_size=50,
            ...         condition=Never(),
            ...         strategy=NoCatchup()
            ...     )
            ... )
        """
        self.processor_config_registry.register(processor_type, config)
        return self

    def configure_upcasting(self, config: UpcastingConfig) -> "ApplicationBuilder":
        """Configure upcasting pipeline behavior.

        Controls when event schema transformations are applied (on read, write, or both).

        Args:
            config: Upcasting configuration (primarily the strategy)

        Returns:
            The application builder for chaining

        Examples:
            Use eager upcasting strategy:

            >>> from ouroboros.events import EagerUpcastingStrategy, UpcastingConfig
            >>> builder.configure_upcasting(
            ...     UpcastingConfig(strategy=EagerUpcastingStrategy())
            ... )

            Use lazy upcasting (default):

            >>> from ouroboros.events import LazyUpcastingStrategy, UpcastingConfig
            >>> builder.configure_upcasting(
            ...     UpcastingConfig(strategy=LazyUpcastingStrategy())
            ... )
        """
        self.container.register(UpcastingConfig, config)
        return self

    def use_synchronous_processing(self) -> "ApplicationBuilder":
        """Configure synchronous event processing (simple monolith).

        Processors execute immediately during command handling. Events are
        published to an in-memory transport and all registered processors
        run synchronously before the command completes.

        Characteristics:
        - Immediate consistency
        - Simple deployment (single process)
        - Command latency includes processor execution
        - Processor failures cause command to fail

        Best for:
        - Simple monolithic applications
        - Prototyping and development
        - When immediate consistency is required

        Returns:
            The application builder for chaining

        Example:
            >>> app = (ApplicationBuilder()
            ...     .use_synchronous_processing()
            ...     .add_event_processor(MyProcessor)
            ...     .build())
        """
        self.container.register(EventDelivery, SynchronousDelivery.create_from_registry)
        return self

    def use_asynchronous_processing(self) -> "ApplicationBuilder":
        """Configure asynchronous event processing (distributed).

        Processors run separately via Application.run_event_processors(),
        typically in separate processes or async tasks. Events are published
        to the transport and processors consume via subscriptions.

        Characteristics:
        - Eventual consistency
        - Scalable deployment (separate containers/processes)
        - Minimal command latency (just publish)
        - Processor failures don't affect commands

        Best for:
        - Production microservice architectures
        - High-throughput systems
        - Scaling read and write sides independently

        Returns:
            The application builder for chaining

        Example:
            >>> app = (ApplicationBuilder()
            ...     .use_asynchronous_processing()
            ...     .with_transport(KafkaEventTransport(...))
            ...     .add_event_processor(MyProcessor)
            ...     .build())
            >>>
            >>> # Separate process:
            >>> await app.run_event_processors()
        """
        self.container.register(EventDelivery, AsynchronousDelivery)
        return self

    def use_correlation_tracking(self) -> "ApplicationBuilder":
        """Enable automatic correlation and causation ID tracking for distributed tracing.

        This method registers the ContextPropagationMiddleware for all commands,
        enabling automatic context propagation throughout the system. With correlation
        tracking enabled:

        - Commands automatically get correlation/causation IDs if not provided
        - Events emitted by aggregates inherit correlation context
        - Event processors restore context for saga commands
        - Logging middleware can include correlation IDs

        **What gets tracked:**
        - **Correlation ID**: Traces entire logical operation across all commands/events
        - **Causation ID**: Identifies what directly caused each command/event
        - **Command ID**: Unique identifier for each command instance

        **Context flow:**
        1. HTTP Request → Command (correlation_id generated)
        2. Command → Events (inherit correlation_id, causation_id = command_id)
        3. Event → Saga Command (inherit correlation_id, causation_id = event_id)

        Returns:
            The application builder for chaining

        Examples:
            Enable correlation tracking for all commands:

            >>> app = (ApplicationBuilder()
            ...     .use_correlation_tracking()
            ...     .add_aggregate(BankAccount)
            ...     .build())

            Combine with logging:

            >>> app = (ApplicationBuilder()
            ...     .use_correlation_tracking()  # Must come before logging
            ...     .add_middleware(Command, LoggingMiddleware("INFO"))
            ...     .build())
            >>> # Logs will include correlation_id, causation_id, command_id

            Manual correlation at HTTP entry point:

            >>> correlation_id = uuid4()
            >>> command = MyCommand(
            ...     aggregate_id=...,
            ...     correlation_id=correlation_id,
            ...     causation_id=correlation_id
            ... )
            >>> await app.dispatch(command)
            >>> # Events will inherit this correlation_id

        Note:
            The ContextPropagationMiddleware should run early in the middleware chain,
            before other middleware that might need access to context (like logging).
        """
        from ..commands.middleware import ContextPropagationMiddleware

        self.add_middleware(Command, ContextPropagationMiddleware)
        return self

    def with_transport(
        self, transport: EventTransport | type[EventTransport]
    ) -> "ApplicationBuilder":
        """Override default event transport.

        By default, InMemoryEventTransport is used. Use this method to
        configure a different transport like Kafka, RabbitMQ, or AWS SNS/SQS.

        Args:
            transport: Event transport instance or class

        Returns:
            The application builder for chaining

        Examples:
            With Kafka:

            >>> builder.with_transport(KafkaEventTransport(brokers=["localhost:9092"]))

            With transport class (will be instantiated with DI):

            >>> builder.with_transport(KafkaEventTransport)
        """
        self.add_dependency(EventTransport, transport)
        return self

    def convention_based(self, package_name: str) -> "ApplicationBuilder":
        """Load aggregates, commands, etc from a convention based module hierarchy.

        Args:
            package_name: The name of the package to load aggregates and commands from.

        Returns:
            The application builder.
        """
        from .configurators import ApplicationProfileSet

        profile = ApplicationProfileSet.convention_based(package_name)
        profile.configure(self)
        return self

    def build(self) -> Application:
        """Build the application with dependency injection.

        This method performs topological resolution of all dependencies,
        builds the event bus, repositories, and command bus, then returns
        a fully configured Application instance.

        Returns:
            The configured Application instance

        Raises:
            ValueError: If dependencies cannot be resolved (missing, circular, or invalid)
        """
        # Create repositories for all aggregates and register with repository registry
        # EventBus will be created by factory after repositories are registered
        event_bus = self.container.resolve(EventBus)

        for aggregate_type in self.aggregates:
            repository = self._create_repository(aggregate_type, event_bus)
            self.repository_registry.register(aggregate_type, repository)

        # Resolve all dependencies (includes CommandBus via factory)
        resolved = self.container.resolve_all()

        # Get processor types for Application
        processor_types = self.processor_registry._processor_types

        return Application(
            command_bus=resolved[CommandBus],
            event_bus=resolved[EventBus],
            dependencies=resolved,
            registered_processors=processor_types,
        )

    def _create_repository(
        self, aggregate_type: type[Aggregate], event_bus: EventBus
    ) -> AggregateRepository:  # type: ignore[type-arg]
        """Create repository for an aggregate with configured strategies."""
        # Get config for this aggregate type
        config = self.repository_config_registry.get(aggregate_type)

        return AggregateRepository(
            aggregate_type=aggregate_type,
            event_bus=event_bus,
            snapshot_strategy=config.snapshot_strategy,
            cache_strategy=config.cache_strategy,
            snapshot_backend=config.snapshot_backend,
            cache_backend=config.cache_backend,
        )

    @staticmethod
    def _is_pydantic_settings(cls: type) -> bool:
        """Check if class is a Pydantic BaseSettings."""
        try:
            from pydantic_settings import BaseSettings  # type: ignore[import-not-found]

            return issubclass(cls, BaseSettings)
        except (ImportError, TypeError):
            return False
