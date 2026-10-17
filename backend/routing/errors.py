class PlanningError(Exception):
    """The request cannot be planned as given (user-correctable)."""


class ExternalServiceError(Exception):
    """A third-party API failed or returned something unusable."""
