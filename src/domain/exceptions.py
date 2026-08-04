"""Custom exceptions."""


class MemoryBankError(Exception):
    """Raised for memory-bank-related issues (not found, invalid name)."""

    pass


class InstanceError(Exception):
    """Raised for instance creation or management failures."""

    pass


class ValidationError(Exception):
    """Raised for invalid input (bad memory bank name, missing required fields)."""

    pass
