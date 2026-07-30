"""Tracing utilities for manual span creation."""

from __future__ import annotations

import asyncio
import functools
from typing import Any, Callable, Optional, ParamSpec, TypeVar, cast

from opentelemetry import trace
from opentelemetry.trace import Span, SpanKind, Status, StatusCode, Tracer

from src.config import settings

P = ParamSpec("P")
R = TypeVar("R")


def get_tracer(name: Optional[str] = None) -> Tracer:
    """Get a tracer instance for creating spans."""
    tracer_name = name or settings.otel_service_name or settings.app_name
    return trace.get_tracer(tracer_name, settings.app_version)


def traced(
    name: Optional[str] = None,
    *,
    kind: SpanKind = SpanKind.INTERNAL,
    attributes: Optional[dict[str, Any]] = None,
    record_exception: bool = True,
    set_status_on_exception: bool = True,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    Decorator to automatically trace a function.

    Args:
        name: Span name (defaults to function name)
        kind: SpanKind (INTERNAL, CLIENT, SERVER, PRODUCER, CONSUMER)
        attributes: Static attributes to add to the span
        record_exception: Record exceptions in the span
        set_status_on_exception: Set error status on exception
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        span_name = name or func.__name__
        tracer = get_tracer(func.__module__)

        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            if not settings.otel_enabled:
                return await func(*args, **kwargs)  # type: ignore

            with tracer.start_as_current_span(
                span_name,
                kind=kind,
                attributes=attributes,
                record_exception=record_exception,
                set_status_on_exception=set_status_on_exception,
            ) as span:
                try:
                    return await func(*args, **kwargs)  # type: ignore
                except Exception as e:
                    if record_exception:
                        span.record_exception(e)
                    if set_status_on_exception:
                        span.set_status(Status(StatusCode.ERROR, str(e)))
                    raise

        @functools.wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            if not settings.otel_enabled:
                return func(*args, **kwargs)

            with tracer.start_as_current_span(
                span_name,
                kind=kind,
                attributes=attributes,
                record_exception=record_exception,
                set_status_on_exception=set_status_on_exception,
            ) as span:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if record_exception:
                        span.record_exception(e)
                    if set_status_on_exception:
                        span.set_status(Status(StatusCode.ERROR, str(e)))
                    raise

        if asyncio.iscoroutinefunction(func):
            return cast(Callable[P, R], async_wrapper)
        return sync_wrapper

    return decorator


def get_current_span() -> Span:
    """Get the current active span."""
    return trace.get_current_span()


def add_span_attributes(attributes: dict[str, Any]) -> None:
    """Add attributes to the current span."""
    span = get_current_span()
    for key, value in attributes.items():
        span.set_attribute(key, value)


def add_span_event(name: str, attributes: Optional[dict[str, Any]] = None) -> None:
    """Add an event to the current span."""
    get_current_span().add_event(name, attributes=attributes)


def set_span_status(code: StatusCode, description: Optional[str] = None) -> None:
    """Set the status of the current span."""
    get_current_span().set_status(Status(code, description))
