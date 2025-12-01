
import inspect
from abc import ABC, abstractmethod
from collections.abc import Callable
from functools import singledispatch
from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


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
    def __call__(
        self, message: Any, instance: Any, *args: Any, **kwargs: Any
    ) -> Any:
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

    def __call__(
        self, message: Any, instance: Any, *args: Any, **kwargs: Any
    ) -> Any:
        raise NotImplementedError(
            f"No {self.operation_name} registered for "
            f"{self.base_type.__name__} type {type(message).__name__}"
        )


class IgnoreHandler(DefaultHandler):
    """Silently ignore unregistered message types."""

    __slots__ = ()

    def __call__(
        self, message: Any, instance: Any, *args: Any, **kwargs: Any
    ) -> Any:
        # Silently ignore unregistered types
        pass


def _extract_handler_type(
    func: Callable[..., object], param_index: int = 1
) -> type:
    """Extract the type annotation from a handler method.

    Args:
        func: The handler method to inspect.
        param_index: Index of the parameter to extract
            (0=self, 1=first arg, etc.)

    Returns:
        The type annotation for the specified parameter.

    Raises:
        ValueError: If the parameter lacks a type annotation.
    """
    # Fast path: use __annotations__ directly if available
    if hasattr(func, "__annotations__"):
        annotations = func.__annotations__
        if annotations:
            # Get parameter names without creating signature object
            param_names = func.__code__.co_varnames
            if len(param_names) <= param_index:
                raise ValueError(
                    f"Handler {func.__name__} must have at least "
                    f"{param_index + 1} parameters"
                )
            param_name = param_names[param_index]
            if param_name in annotations:
                return annotations[param_name]

    # Fallback to inspect if __annotations__ unavailable
    sig = inspect.signature(func)
    params = list(sig.parameters.values())

    if len(params) <= param_index:
        raise ValueError(
            f"Handler {func.__name__} must have at least "
            f"{param_index + 1} parameters"
        )

    param = params[param_index]

    if param.annotation is inspect.Parameter.empty:
        raise ValueError(
            f"Handler {func.__name__} parameter '{param.name}' must "
            f"have a type annotation"
        )

    return param.annotation


class MessageRouter:
    """Generic router for dispatching messages to type-specific handlers.

    This class uses singledispatch to route messages (commands, events, etc.)
    to registered handler methods based on their type annotations.
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
        def dispatch(
            message: object, instance: object, *args: Any, **kwargs: Any
        ) -> object:
            return default_handler(message, instance, *args, **kwargs)

        self._dispatch = dispatch

    def register(
        self,
        message_type: type,
        handler: Callable[[object, object], object],
    ) -> None:
        """Register a handler for a specific message type.

        Args:
            message_type: The message class this handler processes.
            handler: The method to call when handling this message type.
        """
        # Register directly - singledispatch will handle the lookup
        # efficiently. We create a minimal wrapper to swap argument
        # order and pass through any additional arguments
        self._dispatch.register(message_type)(
            lambda msg, inst, *args, h=handler, **kwargs: h(
                inst, msg, *args, **kwargs
            )
        )

    def route(
        self, instance: Any, message: Any, *args: Any, **kwargs: Any
    ) -> object:
        """Route a message to its registered handler.

        Args:
            instance: The instance to call the handler on (self).
            message: The message to route.
            *args: Additional positional arguments to pass to handler.
            **kwargs: Additional keyword arguments to pass to handler.

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
        message_type = _extract_handler_type(func, param_index=1)
        setattr(func, self.type_attr, message_type)
        setattr(func, self.marker_attr, True)
        return func


# Create decorator instances
handles_command = HandlerDecorator(
    "_is_command_handler", "_handles_command_type"
)
applies_event = HandlerDecorator(
    "_is_event_applier", "_applies_event_type"
)
handles_event = HandlerDecorator(
    "_is_event_handler", "_handles_event_type"
)
intercepts = HandlerDecorator(
    "_is_command_interceptor", "_intercepts_command_type"
)

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

intercepts.__doc__ = """Decorator marking a method as a command \
interceptor (for middleware).

The command type is automatically extracted from the method's type \
annotation. Middleware can intercept the base Command type to handle \
all commands, or specific command types for targeted interception.

Example:
    >>> class LoggingMiddleware(CommandMiddleware):
    ...     @intercepts
    ...     def log_command(self, cmd: Command, next: CommandHandler):
    ...         logger.info(f"Command: {type(cmd).__name__}")
    ...         await next(cmd)
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
                    router.register(message_type, value)
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
    from .commands import Command

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


def setup_middleware_routing(cls: type) -> MessageRouter:
    """Set up command interception routing for middleware.

    Args:
        cls: The middleware class to set up routing for.

    Returns:
        A configured MessageRouter for command interceptors.
    """
    # Import here to avoid circular dependency
    from .commands import Command

    return setup_routing(
        cls,
        marker_attr="_is_command_interceptor",
        type_attr="_intercepts_command_type",
        default_handler=IgnoreHandler(Command, "interceptor"),
    )
