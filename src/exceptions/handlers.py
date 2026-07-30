"""
Global exception handlers for the FastAPI application.
Handles all types of exceptions with RFC 7807 Problem Details responses.
"""

import uuid
from typing import Optional

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from opentelemetry import trace
from starlette.responses import Response

from src.exceptions.base_exception import ProjectBaseException
from src.exceptions.problem_detail import ProblemDetail
from src.utilities.loggers.app_logger import logger


def get_trace_id() -> Optional[str]:
    """
    Get the current OpenTelemetry trace ID.

    Returns:
        Trace ID in hex format, or None if no active span
    """
    try:
        span = trace.get_current_span()
        if span and span.get_span_context().is_valid:
            trace_id = format(span.get_span_context().trace_id, "032x")
            return trace_id
    except Exception:
        # If OTel is not properly initialized or any error occurs
        pass
    return None


def generate_request_id() -> str:
    """Generate a unique request ID for tracing."""
    return f"loc_{uuid.uuid4().hex[:16]}"


def get_request_id(request: Request) -> str:
    """
    Get or generate request ID from the request.
    Prioritizes OpenTelemetry trace ID, then custom headers, then generates UUID.
    """
    # Try to get OpenTelemetry trace ID first
    trace_id = get_trace_id()
    if trace_id:
        return trace_id

    # Try to get from headers (if set by load balancer/gateway)
    request_id = request.headers.get("X-Request-ID") or request.headers.get(
        "X-Correlation-ID"
    )
    if not request_id:
        # Check if already set in request state
        request_id = getattr(request.state, "request_id", None)
        if not request_id:
            request_id = generate_request_id()
            request.state.request_id = request_id
    return request_id


async def base_exception_handler(
    request: Request, exc: ProjectBaseException
) -> Response:
    request_id = get_request_id(request)

    logger.opt(exception=True).warning(
        exc.message, details=exc.details, type=exc.error_code
    )

    # Generate problem type URI
    problem_type = f"urn:problem:{exc.error_code.lower().replace('_', '-')}"

    problem_detail = ProblemDetail(
        type=problem_type,
        title=exc.error_code.lower(),
        status=exc.status_code,
        detail=exc.message,
        instance=str(request.url.path),
        traceId=request_id,
        data=exc.details,
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=problem_detail.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
        headers={"Content-Type": "application/problem+json"},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> Response:
    """
    Handle all unhandled exceptions (catch-all handler).
    This should be the last resort for any unexpected errors.

    Args:
        request: The FastAPI request object
        exc: The unhandled exception

    Returns:
        JSONResponse with RFC 7807 Problem Details format (generic error message)
    """
    request_id = get_request_id(request)

    # Log the full exception with traceback
    logger.exception(str(exc))

    # Return a generic error message to the client (don't expose internal details)
    problem_type = "urn:problem:internal-server-error"

    problem_detail = ProblemDetail(
        type=problem_type,
        title="internal_server_error",
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="An unexpected error occurred. Please try again later.",
        instance=str(request.url.path),
        traceId=request_id,
        data=None,
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=problem_detail.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
        headers={"Content-Type": "application/problem+json"},
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> Response:
    """
    Handle http exceptions.

    Args:
        request: The FastAPI request object
        exc: The HTTP exception

    Returns:
        JSONResponse with RFC 7807 Problem Details format (generic error message)
    """
    request_id = get_request_id(request)

    # Log the full exception with traceback
    logger.exception(str(exc))

    # Return a generic error message to the client (don't expose internal details)

    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        problem_detail = ProblemDetail(
            type="urn:problem:unauthorized",
            title="unauthorized",
            status=exc.status_code,
            detail="requested resource requires authentication.",
            instance=str(request.url.path),
            traceId=request_id,
            data=None,
        )
    elif exc.status_code == status.HTTP_403_FORBIDDEN:
        problem_detail = ProblemDetail(
            type="urn:problem:forbidden",
            title="forbidden",
            status=exc.status_code,
            detail="you do not have permission to access the requested resource.",
            instance=str(request.url.path),
            traceId=request_id,
            data=None,
        )
    elif exc.status_code == status.HTTP_404_NOT_FOUND:
        problem_detail = ProblemDetail(
            type="urn:problem:not-found",
            title="not_found",
            status=exc.status_code,
            detail="requested resource was not found.",
            instance=str(request.url.path),
            traceId=request_id,
            data=None,
        )
    else:
        problem_detail = ProblemDetail(
            type="urn:problem:internal-server-error",
            title="internal_server_error",
            status=500,
            detail="An unexpected error occurred. Please try again later.",
            instance=str(request.url.path),
            traceId=request_id,
            data=None,
        )

    return JSONResponse(
        status_code=problem_detail.status,
        content=problem_detail.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
        headers={"Content-Type": "application/problem+json"},
    )
