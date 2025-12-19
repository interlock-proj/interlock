import inspect
from abc import ABC, abstractmethod
from collections.abc import Callable
from functools import singledispatch
from typing import Any, TypeVar, get_args, get_origin

from pydantic import BaseModel

T = TypeVar("T")

# Marker for handlers that want the Event wrapper, not just payload
_WANTS_EVENT_WRAPPER_ATTR = "_wants_event_wrapper"


class DefaultHandler(ABC):
    """Base handler for unregistered message types."""

    __slots__ = ("base_type", "operation_name")

    def __init__(self, base_type: type, operation_name: str):
        """Initialize the default handler.

        Args:
            base_type: The base type for messages (e.g., Command,
                BaseModel).
            operation_name: Name of the operation for error
                messages.
        """
        self.base_type = base_type
        self.operation_name = operation_name

    @abstractmethod
    def __call__(self, message: Any, instance: Any, *args: Any, **kwargs: Any) -> Any:
        """Handle an unregistered message type.

        Args:
            message: The message to handle.
            instance: The instance handling the message.
            *args: Additional positional arguments (ignored).
            **kwargs: Additional keyword arguments (ignored).

        Returns:
            The result of handling the message.
        """
        ...


class RaiseHandler(DefaultHandler):
    """Raise NotImplementedError for unregistered message types."""

    __slots__ = ()

    def __call__(self, message: Any, instance: Any, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError(
            f"No {self.operation_name} registered for "
            f"{self.base_type.__name__} type {type(message).__name__}"
        )


class IgnoreHandler(DefaultHandler):
    """Silently ignore unregistered message types."""

    __slots__ = ()

    def __call__(self, message: Any, instance: Any, *args: Any, **kwargs: Any) -> Any:
        # Silently ignore unregistered types
        pass


def _extract_handler_type(func: Callable[..., Any], param_index: int = 1) -> tuple[type, bool]:
    """Extract the type annotation from a handler method.

    For event handlers, this also detects if the handler wants the Event wrapper
    (annotated as `Event[T]`) or just the payload (annotated as `T`).

    Args:
        func: The handler method to inspect.
        param_index: Index of the parameter to extract
            (0=self, 1=first arg, etc.)

    Returns:
        A tuple of (payload_type, wants_wrapper):
        - payload_type: The inner type to route on (e.g., MoneyDeposited)
        - wants_wrapper: True if annotated as Event[T], False if just T

    Raises:
        ValueError: If the parameter lacks a type annotation.
    """
    annotation = None
    func_name = getattr(func, "__name__", repr(func))

    # Fast path: use __annotations__ directly if available
    annotations = getattr(func, "__annotations__", None)
    code = getattr(func, "__code__", None)
    if annotations and code:
        # Get parameter names without creating signature object
        param_names = code.co_varnames
        if len(param_names) <= param_index:
            raise ValueError(f"Handler {func_name} must have at least {param_index + 1} parameters")
        param_name = param_names[param_index]
        if param_name in annotations:
            annotation = annotations[param_name]

    # Fallback to inspect if __annotations__ unavailable
    if annotation is None:
        sig = inspect.signature(func)
        params = list(sig.parameters.values())

        if len(params) <= param_index:
            raise ValueError(f"Handler {func_name} must have at least {param_index + 1} parameters")

        param = params[param_index]

        if param.annotation is inspect.Parameter.empty:
            raise ValueError(
                f"Handler {func_name} parameter '{param.name}' must have a type annotation"
            )
        annotation = param.annotation

    # Check if annotation is Event[T]
    from .domain import Event  # Import here to avoid circular dependency

    # First try standard typing generics
    origin = get_origin(annotation)
    if origin is Event:
        # Handler wants the Event wrapper - extract inner type
        args = get_args(annotation)
        if args:
            return (args[0], True)
        else:
            raise ValueError(
                f"Handler {func_name}: Event type must have a type"
                " argument, e.g., Event[MoneyDeposited]"
            )

    # For Pydantic models, Event[T] creates a new class at runtime
    # Check if the annotation is a Pydantic model subclassing Event
    if isinstance(annotation, type) and issubclass(annotation, Event):
        # Check for Pydantic's generic metadata
        metadata = getattr(annotation, "__pydantic_generic_metadata__", None)
        if metadata:
            pydantic_origin = metadata.get("origin")
            pydantic_args = metadata.get("args", ())
            if pydantic_origin is Event and pydantic_args:
                # Handler wants the Event wrapper - extract inner type
                return (pydantic_args[0], True)

    # Handler wants just the payload
    return (annotation, False)


class MessageRouter:
    """Generic router for dispatching messages to type-specific handlers.

    This class uses singledispatch to route messages (commands, events, etc.)
    to registered handler methods based on their type annotations.

    For event handlers, supports passing either the event payload or the full
    Event wrapper based on the handler's type annotation.
    """

    __slots__ = ("_dispatch",)

    def __init__(
        self,
        default_handler: DefaultHandler,
    ):
        """Initialize the message router.

        Args:
            default_handler: Handler for unregistered message types.
        """

        # Create singledispatch function with the default handler
        @singledispatch
        def dispatch(message: object, instance: object, *args: Any, **kwargs: Any) -> object:
            return default_handler(message, instance, *args, **kwargs)

        self._dispatch = dispatch

    def register(
        self,
        message_type: type,
        handler: Callable[[object, object], object],
        wants_wrapper: bool = False,
    ) -> None:
        """Register a handler for a specific message type.

        Args:
            message_type: The message class this handler processes.
            handler: The method to call when handling this message type.
            wants_wrapper: If True, handler receives Event wrapper via
                'event_wrapper' kwarg. If False, receives just the payload.
        """
        # Register directly - singledispatch will handle the lookup
        # efficiently. We create a minimal wrapper to swap argument
        # order and pass through any additional arguments
        if wants_wrapper:
            # Handler wants the Event wrapper - pass it via event_wrapper kwarg
            def wrapper(
                msg: object, inst: object, *args: Any, h: Any = handler, **kwargs: Any
            ) -> object:
                # The event_wrapper kwarg contains the full Event object
                event_wrapper = kwargs.pop("event_wrapper", None)
                if event_wrapper is not None:
                    return h(inst, event_wrapper, *args, **kwargs)
                else:
                    # Fallback if no wrapper provided (e.g., testing)
                    return h(inst, msg, *args, **kwargs)

            self._dispatch.register(message_type)(wrapper)
        else:
            # Handler wants just the payload - strip event_wrapper if present
            def payload_wrapper(
                msg: object, inst: object, *args: Any, h: Any = handler, **kwargs: Any
            ) -> object:
                kwargs.pop("event_wrapper", None)  # Remove if present
                return h(inst, msg, *args, **kwargs)

            self._dispatch.register(message_type)(payload_wrapper)

    def route(self, instance: Any, message: Any, *args: Any, **kwargs: Any) -> object:
        """Route a message to its registered handler.

        Args:
            instance: The instance to call the handler on (self).
            message: The message to route (the payload for events).
            *args: Additional positional arguments to pass to handler.
            **kwargs: Additional keyword arguments to pass to handler.
                For events, pass event_wrapper=<Event> to provide the
                full wrapper to handlers that want it.

        Returns:
            The result of the handler method.
        """
        return self._dispatch(message, instance, *args, **kwargs)


class HandlerDecorator:
    """Base class for handler decorators.

    This class encapsulates the logic for creating decorators that mark methods
    as handlers for specific message types.
    """

    def __init__(self, marker_attr: str, type_attr: str):
        """Initialize the decorator.

        Args:
            marker_attr: Attribute name to mark decorated methods
                (e.g., '_is_command_handler').
            type_attr: Attribute name to store the message type
                (e.g., '_handles_command_type').
        """
        self.marker_attr = marker_attr
        self.type_attr = type_attr

    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        """Decorate a handler method.

        Args:
            func: The handler method to decorate.

        Returns:
            The decorated method with metadata attached.
        """
        message_type, wants_wrapper = _extract_handler_type(func, param_index=1)
        setattr(func, self.type_attr, message_type)
        setattr(func, self.marker_attr, True)
        setattr(func, _WANTS_EVENT_WRAPPER_ATTR, wants_wrapper)
        return func


# Create decorator instances
handles_command = HandlerDecorator("_is_command_handler", "_handles_command_type")
applies_event = HandlerDecorator("_is_event_applier", "_applies_event_type")
handles_event = HandlerDecorator("_is_event_handler", "_handles_event_type")
handles_query = HandlerDecorator("_is_query_handler", "_handles_query_type")
intercepts = HandlerDecorator("_is_command_interceptor", "_intercepts_command_type")

# Add docstrings
handles_command.__doc__ = """Decorator marking a method as a command handler.

The command type is automatically extracted from the method's type annotation.

Example:
    >>> class MyAggregate(Aggregate):
    ...     @handles_command
    ...     def handle_create(self, cmd: CreateAggregate):
    ...         self.emit(AggregateCreated(name=cmd.name))
"""

applies_event.__doc__ = """Decorator marking a method as an event applier.

The event type is automatically extracted from the method's type annotation.

Example:
    >>> class MyAggregate(Aggregate):
    ...     @applies_event
    ...     def apply_created(self, evt: AggregateCreated):
    ...         self.name = evt.name
"""

handles_event.__doc__ = """Decorator marking a method as an event \
handler (for event processors).

The event type is automatically extracted from the method's type annotation.

Example:
    >>> class MyProcessor(EventProcessor):
    ...     @handles_event
    ...     def handle_created(self, evt: AggregateCreated):
    ...         self.update_read_model(evt)
"""

handles_query.__doc__ = """Decorator marking a method as a query \
handler (for projections).

The query type is automatically extracted from the method's type annotation.
Query handlers return typed responses based on the Query's generic parameter.

Example:
    >>> class UserProjection(Projection):
    ...     @handles_query
    ...     async def get_user(self, query: GetUserById) -> UserProfile:
    ...         return self.users[query.user_id]
    ...
    ...     @handles_query
    ...     async def find_by_email(self, query: GetUserByEmail) -> UUID | None:
    ...         return self.email_index.get(query.email)
"""

intercepts.__doc__ = """Decorator marking a method as a \
message interceptor (for middleware).

The message type is automatically extracted from the method's type \
annotation. Middleware can intercept commands, queries, or both.
Use base types (Command, Query) to intercept all messages of that kind,
or specific types for targeted interception.

Example:
    >>> class LoggingMiddleware(Middleware):
    ...     @intercepts
    ...     async def log_command(self, cmd: Command, next: Handler):
    ...         logger.info(f"Command: {type(cmd).__name__}")
    ...         return await next(cmd)
    ...
    ...     @intercepts
    ...     async def log_query(self, query: Query, next: Handler):
    ...         logger.info(f"Query: {type(query).__name__}")
    ...         return await next(query)
"""


def setup_routing(
    cls: type,
    marker_attr: str,
    type_attr: str,
    default_handler: DefaultHandler,
) -> MessageRouter:
    """Set up message routing for a class.

    Scans the class for methods decorated with the specified marker and
    registers them with a MessageRouter.

    Args:
        cls: The class to set up routing for.
        marker_attr: Attribute name marking decorated methods.
        type_attr: Attribute name storing the message type.
        default_handler: Handler for unregistered message types.

    Returns:
        A configured MessageRouter.
    """
    router = MessageRouter(default_handler)

    # Scan all methods in the class hierarchy
    # Use try/except instead of hasattr for better performance
    for klass in cls.__mro__:
        for value in klass.__dict__.values():
            try:
                # Check if it has the marker attribute
                if getattr(value, marker_attr, None):
                    message_type = getattr(value, type_attr)
                    wants_wrapper = getattr(value, _WANTS_EVENT_WRAPPER_ATTR, False)
                    router.register(message_type, value, wants_wrapper=wants_wrapper)
            except AttributeError:
                # Not a method or doesn't have the attributes
                continue

    return router


def setup_command_routing(cls: type) -> MessageRouter:
    """Set up command routing for a class.

    Args:
        cls: The class to set up routing for.

    Returns:
        A configured MessageRouter for commands.
    """
    # Import here to avoid circular dependency
    from .domain import Command

    return setup_routing(
        cls,
        marker_attr="_is_command_handler",
        type_attr="_handles_command_type",
        default_handler=RaiseHandler(Command, "handler"),
    )


def setup_event_applying(cls: type) -> MessageRouter:
    """Set up event applying for a class.

    Args:
        cls: The class to set up routing for.

    Returns:
        A configured MessageRouter for event appliers.
    """
    return setup_routing(
        cls,
        marker_attr="_is_event_applier",
        type_attr="_applies_event_type",
        default_handler=IgnoreHandler(BaseModel, "applier"),
    )


def setup_event_handling(cls: type) -> MessageRouter:
    """Set up event handling for a class.

    Args:
        cls: The class to set up routing for.

    Returns:
        A configured MessageRouter for event handlers.
    """
    return setup_routing(
        cls,
        marker_attr="_is_event_handler",
        type_attr="_handles_event_type",
        default_handler=IgnoreHandler(BaseModel, "handler"),
    )


def setup_query_routing(cls: type) -> MessageRouter:
    """Set up query routing for a projection class.

    Args:
        cls: The projection class to set up routing for.

    Returns:
        A configured MessageRouter for query handlers.
    """
    # Import here to avoid circular dependency
    from .domain import Query

    return setup_routing(
        cls,
        marker_attr="_is_query_handler",
        type_attr="_handles_query_type",
        default_handler=RaiseHandler(Query, "handler"),
    )


def setup_middleware_routing(cls: type) -> MessageRouter:
    """Set up message interception routing for middleware.

    Middleware can intercept both commands and queries using the
    @intercepts decorator. The routing is based on message type
    annotations.

    Args:
        cls: The middleware class to set up routing for.

    Returns:
        A configured MessageRouter for message interceptors.
    """
    return setup_routing(
        cls,
        marker_attr="_is_command_interceptor",
        type_attr="_intercepts_command_type",
        default_handler=IgnoreHandler(BaseModel, "interceptor"),
    )
