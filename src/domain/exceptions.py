"""Custom exceptions."""


class DomainException(Exception):
    """Raised when a domain invariant is violated.

    Carries a machine-readable error code and optional detail payload
    so that application-layer handlers can convert it to a Result.ko
    without losing context.
    """

    def __init__(self, code: str, details: dict | None = None) -> None:
        self.code = code
        self.details = details or {}
        super().__init__(f"{code}: {details}")


class MemoryNotFoundError(Exception):
    """Domain exception for memory not found."""

    pass


class MemoryBankError(Exception):
    """Raised for memory-bank-related issues (not found, invalid name)."""

    pass


class InstanceError(Exception):
    """Raised for instance creation or management failures."""

    pass


class ValidationError(Exception):
    """Raised for invalid input (bad memory bank name, missing required fields)."""

    pass
