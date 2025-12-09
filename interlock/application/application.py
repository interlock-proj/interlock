import asyncio
from collections.abc import Callable
from types import TracebackType
from typing import Any, Protocol, TypeVar, runtime_checkable

from ..domain import Aggregate, Command
from .aggregates import (
    AggregateCacheBackend,
    AggregateFactory,
    AggregateRepository,
    AggregateSnapshotStorageBackend,
    AggregateSnapshotStrategy,
    CacheStrategy,
)
from .commands import (
    AggregateToRepositoryMap,
    CommandBus,
    CommandMiddleware,
    CommandToAggregateMap,
    DelegateToAggregate,
)
from .container import ContextualBinding, DependencyContainer
from .events import (
    CatchupCondition,
    CatchupStrategy,
    EventBus,
    EventDelivery,
    EventProcessor,
    EventProcessorExecutor,
    EventStore,
    EventTransport,
    EventUpcaster,
    InMemoryEventStore,
    InMemoryEventTransport,
    LazyUpcastingStrategy,
    Never,
    NoCatchup,
    SynchronousDelivery,
    UpcasterMap,
    UpcastingPipeline,
    UpcastingStrategy,
)
from .events.processing import SagaStateStore

T = TypeVar("T")


@runtime_checkable
class HasLifecycle(Protocol):
    async def on_startup(self) -> None:
        """Called when the application is started."""
        ...

    async def on_shutdown(self) -> None:
        """Called when the application is shutdown."""
        ...


class Application:
    def __init__(self, contextual_binding: ContextualBinding):
        self.contextual_binding = contextual_binding
        self.command_bus = self.resolve(CommandBus)
        self.event_bus = self.resolve(EventBus)

    async def dispatch(self, command: Command) -> None:
        """Dispatch a command to the application.

        This method will dispatch a command to the application. The command
        will be dispatched to the command bus and the command bus will dispatch
        the command to the appropriate aggregate and middleware chain.

        Args:
            command: The command to dispatch.
        """
        await self.command_bus.dispatch(command)

    def resolve(self, type_to_resolve: type[T]) -> T:
        """Resolve a dependency from the application.

        This method will resolve a dependency from the application.
        The dependency will be resolved from the contextual binding
        and will be returned.

        Args:
            type_to_resolve: The type of the dependency to resolve.

        Returns:
            The resolved dependency.

        Raises:
            DependencyNotFoundError: If the dependency cannot be
                resolved.
        """
        return self.contextual_binding.resolve(type_to_resolve)

    async def startup(self) -> None:
        """Startup the application.

        This method will startup the application. The application will be
        started by calling the on_startup method on all dependencies that
        implement the `HasLifecycle` protocol. The dependencies are started
        in the order of their registration.
        """
        dependencies = self.contextual_binding.resolve_all_of_type(HasLifecycle)
        for dependency in dependencies:
            await dependency.on_startup()

    async def shutdown(self) -> None:
        """Shutdown the application.

        This method will shutdown the application. The application will be
        shutdown by calling the on_shutdown method on all dependencies that
        implement the `HasLifecycle` protocol. The dependencies are shutdown
        in the reverse order of their registration.
        """
        dependencies = self.contextual_binding.resolve_all_of_type(HasLifecycle)
        for dependency in reversed(dependencies):
            await dependency.on_shutdown()

    async def __aenter__(self) -> "Application":
        await self.startup()
        return self

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        await self.shutdown()

    async def run_event_processors(self, *processors: type[EventProcessor]) -> None:
        """Run the event processors for the application.

        This method will run the event processors for the application of the
        given types. The event processors are run asynchronously and will
        continue to run until the application is stopped or all run methods
        have completed. The event processors are run in the order they were
        registered.

        Args:
            *processors: The event processors to run.

        Raises:
            Any exceptions raised by the event processors will be propagated to
            the caller.

        Returns:
            None
        """
        # We will resolve each processors executor from its own container
        # context and then subscribe to the event transport for the processor.
        executors = [
            self.contextual_binding.container_for(processor).resolve(EventProcessorExecutor)
            for processor in processors
        ]

        transport = self.contextual_binding.resolve(EventTransport)
        subscriptions = [
            await transport.subscribe(executor.processor.__class__.__name__)
            for executor in executors
        ]

        # Now that we have a subscription for each processor, we can run the
        # processors in their own async tasks. We will gather the tasks and
        # await them all to complete (This will probably be 'forever' since
        # the processors are expected to run until the application is stopped).
        tasks = [
            executor.run(subscription) for executor, subscription in zip(executors, subscriptions)
        ]
        await asyncio.gather(*tasks)


# At the API level, the application builder simply provides a fluent API for
# configuring the application like all builders. Under the hood, the builder
# is managing a container of containers (ContextualBinding) that are used to
# resolve dependencies for the application. This is what allows us to have
# per-type customizations for dependencies like aggregates, commands,
# middleware, event processors, upcasters, etc.  All dependecies are
# registered as singletons and the builder will use the contextual binding to
# resolve the dependencies for the application by starting at that context and
# then returning to the root container as needed for resolution.
#
# The builder is also responsible for registering the default dependencies for
# the application like the event bus, upcasting pipeline, event transport,
# event store, etc. These defaults are used to configure the application and
# can be overridden by the user.


class ApplicationBuilder:
    """Builder for creating Application instances."""

    def __init__(self) -> None:
        self.container = DependencyContainer()
        self.contextual_binding = ContextualBinding(self.container)

        # Event Bus Defaults:
        self.container.register_singleton(
            dependency_type=UpcastingStrategy,
            factory=LazyUpcastingStrategy,
        )
        self.container.register_singleton(
            dependency_type=EventTransport,
            factory=InMemoryEventTransport,
        )
        self.container.register_singleton(
            dependency_type=EventStore,
            factory=InMemoryEventStore,
        )
        self.container.register_singleton(
            dependency_type=UpcasterMap,
            factory=self._build_upcaster_map,
        )
        self.container.register_singleton(UpcastingPipeline)
        self.container.register_singleton(
            dependency_type=EventDelivery,
            factory=self._build_synchronous_delivery,
        )
        self.container.register_singleton(EventBus)

        # Aggregate Repository Defaults:
        self.container.register_singleton(
            dependency_type=AggregateSnapshotStrategy,
            factory=AggregateSnapshotStrategy.never,
        )
        self.container.register_singleton(
            dependency_type=AggregateCacheBackend,
            factory=AggregateCacheBackend.null,
        )
        self.container.register_singleton(
            dependency_type=AggregateSnapshotStorageBackend,
            factory=AggregateSnapshotStorageBackend.null,
        )

        # Event Processor Defaults:
        self.container.register_singleton(
            dependency_type=CatchupCondition,
            factory=Never,
        )
        self.container.register_singleton(
            dependency_type=CatchupStrategy,
            factory=NoCatchup,
        )
        self.container.register_singleton(
            dependency_type=CacheStrategy,
            factory=CacheStrategy.never,
        )

        # Command Bus Defaults:
        self.container.register_singleton(
            dependency_type=CommandToAggregateMap,
            factory=self._build_command_to_aggregate_map,
        )
        self.container.register_singleton(
            dependency_type=AggregateToRepositoryMap,
            factory=self._build_aggregate_to_repository_map,
        )
        self.container.register_singleton(DelegateToAggregate)
        self.container.register_singleton(
            dependency_type=CommandBus,
            factory=self._build_command_bus,
        )

        self.container.register_singleton(SagaStateStore, SagaStateStore.in_memory)

    def register_dependency(
        self,
        dependency_type: type[T],
        factory: Callable[..., T] | None = None,
    ) -> "ApplicationBuilder":
        """Register a dependency with the application.

        This method will register a dependency with the application.
        All dependencies are registered as singletons and the provided
        factory will be used to create the dependency when it is
        resolved for the first time. If no factory is provided, the
        dependency will be resolved by calling the __init__ method of
        the dependency type. Regardless of dependecies of that function
        will be resolved by the container.

        Args:
            dependency_type: The type to register
            factory: The factory function to create the dependency

        Returns:
            The application builder
        """
        self.container.register_singleton(dependency_type, factory or dependency_type)
        return self

    def register_aggregate(
        self,
        aggregate_type: type[Aggregate],
        cache_strategy: type[CacheStrategy] | None = None,
        snapshot_strategy: type[AggregateSnapshotStrategy] | None = None,
        cache_backend: type[AggregateCacheBackend] | None = None,
        snapshot_backend: type[AggregateSnapshotStorageBackend] | None = None,
    ) -> "ApplicationBuilder":
        """Add an aggregate to the application.

        This method will register an aggregate with the application. The
        aggregate will be registered with the application and will be
        available to be resolved. In addition to registering the aggregate,
        you can also configure related dependencies for the aggregate such as
        the cache and snapshot configurations.

        If the aggregate was already registered, this method will update the
        dependencies for the aggregate. Thefore it is fine to have
        multiple calls to this method for the same aggregate type.

        Args:
            aggregate_type: The type of aggregate to add.
            cache_strategy: The type of cache strategy to use.
            snapshot_strategy: The type of snapshot strategy to use.
            cache_backend: The type of cache backend to use.
            snapshot_backend: The type of snapshot backend to use.

        Returns:
            The application builder.
        """
        container = self.contextual_binding.container_for(aggregate_type)
        container.register_singleton(AggregateFactory, lambda: AggregateFactory(aggregate_type))
        container.register_singleton(Aggregate, aggregate_type)
        container.register_singleton(AggregateRepository)
        if cache_strategy:
            container.register_singleton(
                dependency_type=CacheStrategy,
                factory=cache_strategy,
            )
        if snapshot_strategy:
            container.register_singleton(
                dependency_type=AggregateSnapshotStrategy,
                factory=snapshot_strategy,
            )
        if cache_backend:
            container.register_singleton(
                dependency_type=AggregateCacheBackend,
                factory=cache_backend,
            )
        if snapshot_backend:
            container.register_singleton(
                dependency_type=AggregateSnapshotStorageBackend,
                factory=snapshot_backend,
            )
        return self

    def register_middleware(
        self,
        middleware_type: type[CommandMiddleware],
    ) -> "ApplicationBuilder":
        """Register middleware with the application.

        This method will register middleware with the application. The
        middleware will be registered with the application and will be
        available to be resolved. Middleware uses annotation-based routing
        with @intercepts decorator to determine which commands to intercept.

        Args:
            middleware_type: The type of middleware to register

        Returns:
            The application builder.
        """
        container = self.contextual_binding.container_for(middleware_type)
        container.register_singleton(middleware_type)
        container.register_singleton(CommandMiddleware, middleware_type)
        return self

    def register_event_processor(
        self,
        processor_type: type[EventProcessor],
        catchup_condition: CatchupCondition | None = None,
        catchup_strategy: CatchupStrategy | None = None,
    ) -> "ApplicationBuilder":
        """Creates or updates the registration of an event processor.

        The processor will be registered with the application and will be
        avaiable to be resolved. In addition to registering the processor,
        you can also configure the processor's execution configuration
        via setting any of the relevant optional parameters on the
        CatchupCondition and CatchupStrategy objects.

        Args:
            processor_type: The type of the event processor to register
            catchup_condition: The condition to trigger catchup
            catchup_strategy: The strategy to use for catchup

        Returns:
            The application builder
        """
        container = self.contextual_binding.container_for(processor_type)
        container.register_singleton(processor_type)
        container.register_singleton(EventProcessorExecutor)
        if catchup_condition:
            container.register_singleton(CatchupCondition, catchup_condition)
        if catchup_strategy:
            container.register_singleton(CatchupStrategy, catchup_strategy)
        return self

    def register_upcaster(
        self,
        upcaster: type[EventUpcaster[Any, Any]],
        upcasting_strategy: type[UpcastingStrategy] | None = None,
    ) -> "ApplicationBuilder":
        """Register an upcaster with the application.

        This method will register an upcaster with the application. The
        upcaster will be registered with the application and will be available
        to be resolved. In addition to registering the upcaster, you can also
        configure the upcaster's upcasting strategy via setting the relevant
        optional parameter.

        If the upcaster was already registered, this method will update the
        upcasting strategy for the upcaster. Thefore it is fine to have
        multiple calls to this method for the same upcaster type.

        Args:
            upcaster: The type of the upcaster to register
            upcasting_strategy: The type of the upcasting strategy to register

        Returns:
            The application builder
        """
        container = self.contextual_binding.container_for(upcaster)
        container.register_singleton(upcaster, upcaster)
        if upcasting_strategy:
            container.register_singleton(UpcastingStrategy, upcasting_strategy)
        return self

    def convention_based(self, package_name: str) -> "ApplicationBuilder":
        """Load aggregates, commands, etc from convention based modules.

        This method will load aggregates, commands, middleware, event
        processors, upcasters, configs, and services from a package based on
        the conventions of the package. The package will be scanned
        recursively for the relevant components.

        Args:
            package_name: The name of the package to load components from.

        Returns:
            The application builder.
        """
        from .configurators import ApplicationProfile

        for profile in ApplicationProfile.convention_based(package_name):
            profile.configure(self)
        return self

    def build(self) -> Application:
        """Build the application with dependency injection.

        This method will resolve all dependencies and return an Application
        instance. If any dependencies cannot be resolved, an error will be
        raised. The Application instance will be fully configured and ready to
        use.

        Returns:
            The configured Application instance

        Raises:
            ValueError: If dependencies cannot be resolved (missing, etc.)
        """
        return Application(self.contextual_binding)

    def _build_command_to_aggregate_map(self) -> CommandToAggregateMap:
        all_aggregates = self.contextual_binding.all_of_type(Aggregate)
        return CommandToAggregateMap.from_aggregates(all_aggregates)

    def _build_aggregate_to_repository_map(self) -> AggregateToRepositoryMap:
        all_repositories = [
            self.contextual_binding.container_for(aggregate).resolve(AggregateRepository)
            for aggregate in self.contextual_binding.all_of_type(Aggregate)
        ]
        return AggregateToRepositoryMap.from_repositories(all_repositories)

    def _build_upcaster_map(self) -> UpcasterMap:
        all = self.contextual_binding.resolve_all_of_type(EventUpcaster)
        return UpcasterMap.from_upcasters(all)

    def _build_synchronous_delivery(self) -> SynchronousDelivery:
        transport = self.container.resolve(EventTransport)
        all = self.contextual_binding.resolve_all_of_type(EventProcessor)
        return SynchronousDelivery(transport, all)

    def _build_command_bus(self) -> CommandBus:
        root_handler = self.container.resolve(DelegateToAggregate)
        all = self.contextual_binding.resolve_all_of_type(CommandMiddleware)
        return CommandBus(root_handler, all)
