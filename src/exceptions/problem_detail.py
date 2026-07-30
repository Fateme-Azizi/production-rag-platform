"""
RFC 7807 Problem Details for HTTP APIs response schemas.
Provides standardized error responses following RFC 7807 specification.

Reference: https://datatracker.ietf.org/doc/html/rfc7807
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ProblemDetail(BaseModel):
    """
    RFC 7807 Problem Details for HTTP APIs.

    A standardized format for representing errors in HTTP APIs.
    """

    type: str = Field(
        ...,
        description="A URI reference that identifies the problem type",
        json_schema_extra={
            "example": "https://api.example.com/problems/payment-not-found"
        },
    )
    title: str = Field(
        ...,
        description="A short, human-readable summary of the problem type",
        json_schema_extra={"example": "Payment Not Found"},
    )
    status: int = Field(
        ...,
        description="The HTTP status code for this occurrence",
        ge=400,
        le=599,
        json_schema_extra={"example": 404},
    )
    detail: str = Field(
        ...,
        description="A human-readable explanation specific to this occurrence of the problem",
        json_schema_extra={"example": "Payment with id 12345 was not found"},
    )
    instance: Optional[str] = Field(
        None,
        description="A URI reference that identifies the specific occurrence of the problem",
        json_schema_extra={"example": "/api/payments/12345"},
    )

    traceId: Optional[str] = Field(
        None,
        alias="traceId",
        description="Unique identifier for tracing this request across services",
        json_schema_extra={"example": "req_abc123xyz"},
    )
    timestamp: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when the error occurred",
    )
    data: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional structured data about the error",
        json_schema_extra={"example": {"field": "value"}},
    )
