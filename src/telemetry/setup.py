"""OpenTelemetry initialization and shutdown."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Optional

from opentelemetry import trace
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SpanExporter
from opentelemetry.sdk.trace.sampling import ParentBasedTraceIdRatio, Sampler

if TYPE_CHECKING:
    from fastapi import FastAPI

from src.config import settings

# Resource attribute keys (using string constants per OpenTelemetry spec)
SERVICE_NAME = "service.name"
SERVICE_VERSION = "service.version"
DEPLOYMENT_ENVIRONMENT = "deployment.environment"

_tracer_provider: Optional[TracerProvider] = None
_initialized: bool = False


def _get_propagators() -> CompositePropagator:
    from opentelemetry.baggage.propagation import W3CBaggagePropagator
    from opentelemetry.propagators.b3 import B3MultiFormat, B3SingleFormat
    from opentelemetry.trace.propagation.tracecontext import (
        TraceContextTextMapPropagator,
    )

    propagator_map: dict[str, Callable[[], Any]] = {
        "tracecontext": TraceContextTextMapPropagator,
        "baggage": W3CBaggagePropagator,
        "b3": B3SingleFormat,
        "b3multi": B3MultiFormat,
    }

    propagators = [
        propagator_map[p.strip().lower()]()
        for p in settings.otel_propagators.split(",")
        if p.strip().lower() in propagator_map
    ]

    return CompositePropagator(
        propagators
        or [
            TraceContextTextMapPropagator(),
            W3CBaggagePropagator(),
        ]
    )


def _get_exporter() -> Optional[SpanExporter]:
    exporter_type = settings.otel_exporter.lower()

    if exporter_type == "none":
        return None

    if exporter_type == "console":
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter

        return ConsoleSpanExporter()

    if exporter_type == "otlp":
        if settings.otel_otlp_http_endpoint:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter as OTLPSpanExporterHTTP,
            )

            return OTLPSpanExporterHTTP(endpoint=settings.otel_otlp_http_endpoint)
        else:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter as OTLPSpanExporterGRPC,
            )

            return OTLPSpanExporterGRPC(endpoint=settings.otel_otlp_endpoint)

    from opentelemetry.sdk.trace.export import ConsoleSpanExporter

    return ConsoleSpanExporter()


def _get_sampler() -> Sampler:
    rate = settings.otel_sample_rate

    if rate >= 1.0:
        from opentelemetry.sdk.trace.sampling import ALWAYS_ON

        return ALWAYS_ON

    if rate <= 0.0:
        from opentelemetry.sdk.trace.sampling import ALWAYS_OFF

        return ALWAYS_OFF

    return ParentBasedTraceIdRatio(rate)


def init_telemetry() -> Optional[TracerProvider]:
    global _tracer_provider, _initialized

    if _initialized or not settings.otel_enabled:
        return _tracer_provider

    service_name = settings.otel_service_name or settings.app_name

    resource = Resource.create(
        {
            SERVICE_NAME: service_name,
            SERVICE_VERSION: settings.app_version,
            DEPLOYMENT_ENVIRONMENT: settings.env,
        }
    )

    _tracer_provider = TracerProvider(resource=resource, sampler=_get_sampler())

    exporter = _get_exporter()
    if exporter:
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        _tracer_provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(_tracer_provider)
    set_global_textmap(_get_propagators())

    # Instrument aiohttp client globally (works for all sessions)
    if settings.otel_instrument_aiohttp:
        _instrument_aiohttp()

    if settings.otel_instrument_logging:
        _instrument_logging()

    _initialized = True
    return _tracer_provider


def instrument_app(app: FastAPI) -> None:
    if not settings.otel_enabled or not settings.otel_instrument_fastapi:
        return

    if not _initialized:
        init_telemetry()

    _instrument_fastapi(app)


def shutdown_telemetry() -> None:
    """Shutdown OpenTelemetry and flush pending spans."""
    global _tracer_provider, _initialized
    if _tracer_provider:
        _tracer_provider.shutdown()
        _tracer_provider = None
    _initialized = False


def _instrument_fastapi(app: FastAPI) -> None:
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(
            app,
            excluded_urls="health,healthz,ready,readyz,live,livez",
        )
    except (ImportError, Exception):
        pass


def _instrument_aiohttp() -> None:
    try:
        from opentelemetry.instrumentation.aiohttp_client import (
            AioHttpClientInstrumentor,
        )

        AioHttpClientInstrumentor().instrument()
    except (ImportError, Exception):
        pass


def _instrument_logging() -> None:
    try:
        from opentelemetry.instrumentation.logging import LoggingInstrumentor

        LoggingInstrumentor().instrument(set_logging_format=True)
    except (ImportError, Exception):
        pass
