"""Custom exceptions."""


class NamespaceError(Exception):
    """Raised for namespace-related issues (not found, invalid name)."""

    pass


class InstanceError(Exception):
    """Raised for instance creation or management failures."""

    pass


class ValidationError(Exception):
    """Raised for invalid input (bad namespace name, missing required fields)."""

    pass
