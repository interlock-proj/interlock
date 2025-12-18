"""Base middleware class for commands and queries.

Middleware components wrap handlers to provide cross-cutting concerns
like logging, validation, authentication, or transaction management.
"""

import inspect
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any, ClassVar, TypeVar

from pydantic import BaseModel

if TYPE_CHECKING:
    from ...routing import MessageRouter

T = TypeVar("T")

# Handler type for both commands and queries
Handler = Callable[[BaseModel], Coroutine[Any, Any, Any]]


class Middleware:
    """Base class for middleware with annotation-based routing.

    Middleware components wrap handlers to provide cross-cutting
    concerns like logging, validation, authentication, or transaction
    management. They follow the chain of responsibility pattern.

    Middleware can intercept both commands and queries using the
    @intercepts decorator. The framework automatically routes messages
    to the appropriate methods based on their type annotations.

    By default, if no interceptor matches the message type, the
    middleware forwards to the next handler (pass-through behavior).

    Examples:
        Intercept all commands:

        >>> class LoggingMiddleware(Middleware):
        ...     @intercepts
        ...     async def log_command(self, cmd: Command, next: Handler) -> Any:
        ...         print(f"Command: {type(cmd).__name__}")
        ...         return await next(cmd)

        Intercept specific command type:

        >>> class AdminOnlyMiddleware(Middleware):
        ...     @intercepts
        ...     async def check_admin(self, cmd: DeleteUser, next: Handler) -> Any:
        ...         if not self.is_admin(cmd.requester_id):
        ...             raise PermissionError("Admin required")
        ...         return await next(cmd)

        Intercept queries:

        >>> class CachingMiddleware(Middleware):
        ...     @intercepts
        ...     async def cache_query(self, query: Query, next: Handler) -> Any:
        ...         if cached := self.cache.get(query):
        ...             return cached
        ...         result = await next(query)
        ...         self.cache.set(query, result)
        ...         return result
    """

    # Class-level routing table
    _command_router: ClassVar["MessageRouter"]

    def __init_subclass__(cls, **kwargs: object) -> None:
        """Set up routing when a subclass is defined."""
        super().__init_subclass__(**kwargs)
        from ...routing import setup_middleware_routing

        cls._command_router = setup_middleware_routing(cls)

    async def intercept(self, message: BaseModel, next: Handler) -> Any:
        """Route message to interceptor method or forward to next.

        This method is called by the bus for each message. It uses the
        routing table to find an appropriate interceptor method based
        on the message type. If no interceptor is registered for the
        message type, it forwards to the next handler.

        Args:
            message: The command or query to intercept.
            next: The next handler in the middleware chain.

        Returns:
            The result from the interceptor or next handler.
        """
        # Route to interceptor, passing next as an extra argument
        result = self._command_router.route(self, message, next)

        # If router returned None (IgnoreHandler), forward to next
        if result is None:
            return await next(message)
        elif inspect.isawaitable(result):
            # Router returned coroutine (async interceptor), await it
            return await result
        else:
            return result
