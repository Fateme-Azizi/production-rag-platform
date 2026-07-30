from typing import Any, Optional

from fastapi import status


class ProjectBaseException(Exception):
    """
    Base exception class for all custom application exceptions.

    Attributes:
        message: Human-readable error message
        status_code: HTTP status code to return
        error_code: Machine-readable error code
        details: Additional context about the error
    """

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_code: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.error_code = (
            error_code or self.__class__.__name__.replace("Exception", "").upper()
        )
        self.details = details or {}
        super().__init__(self.message)
