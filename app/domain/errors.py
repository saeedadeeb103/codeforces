class DomainError(ValueError):
    """A business rule was violated."""


class NotFound(LookupError):
    """The requested aggregate does not exist."""
