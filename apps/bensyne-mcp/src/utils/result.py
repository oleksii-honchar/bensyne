"""Result pattern with domain events support.

Following the racochu pattern: domain events are returned alongside values
in Result objects, not stored as entity/aggregate properties.

Usage:
    # Success with value
    result = Result.ok(value)
    result = Result.ok(value, events=[domain_event])

    # Failure with error
    result = Result.ko(errors=[ErrorWithDetails("ERROR_CODE", {})])
"""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class ErrorWithDetails:
    """Error with a machine-readable code and optional detail payload."""

    error_code: str
    details: dict


class DomainEvent(ABC):
    """Abstract base class for domain events."""

    @property
    @abstractmethod
    def event_type(self) -> str:
        """Machine-readable event type identifier (e.g. 'memory.remembered')."""

    @property
    @abstractmethod
    def timestamp(self) -> datetime:
        """When the event occurred."""

    @abstractmethod
    def get_name(self) -> str:
        """Human-readable event name."""


@dataclass(frozen=True)
class Result(Generic[T]):
    """Result pattern supporting success/failure with optional domain events.

    Events are produced by entity/aggregate operations and returned in the
    Result object, not stored as properties on the entity/aggregate.
    """

    value: T | None
    errors: list[ErrorWithDetails]
    events: list[DomainEvent]

    @classmethod
    def ok(cls, value: T, events: list[DomainEvent] | None = None) -> "Result[T]":
        """Create a successful result with value and optional events."""
        return cls(value=value, errors=[], events=events or [])

    @classmethod
    def ko(cls, errors: list[ErrorWithDetails], events: list[DomainEvent] | None = None) -> "Result[None]":
        """Create a failed result with error(s) and optional events."""
        return cls(value=None, errors=errors, events=events or [])

    @property
    def is_ok(self) -> bool:
        """Check if result is successful."""
        return len(self.errors) == 0

    @property
    def is_ko(self) -> bool:
        """Check if result failed."""
        return len(self.errors) > 0

    def has_events(self) -> bool:
        """Check if result contains domain events."""
        return len(self.events) > 0

    def get_events(self) -> list[DomainEvent]:
        """Get domain events from result."""
        return self.events

    def get_errors(self) -> list[ErrorWithDetails]:
        """Get errors from result."""
        return self.errors

    def get_formatted_errors(self) -> str:
        """Format all errors into a human-readable string.

        Each error is formatted as: error_code: details_json
        Errors are joined with ", ". Returns empty string when no errors.
        """
        return ", ".join(
            f"{error.error_code}: {json.dumps(error.details)}"
            for error in self.errors
        )
