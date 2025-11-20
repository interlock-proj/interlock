"""Audit service for testing."""

from abc import ABC, abstractmethod


class IAuditService(ABC):
    """Audit service interface."""

    @abstractmethod
    def log(self, message: str) -> None:
        """Log an audit message."""
        pass


class AuditService(IAuditService):
    """Concrete audit service."""

    def __init__(self) -> None:
        self.logs: list[str] = []

    def log(self, message: str) -> None:
        """Log a message."""
        self.logs.append(message)
