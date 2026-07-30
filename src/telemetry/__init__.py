from .setup import init_telemetry, instrument_app, shutdown_telemetry
from .tracer import (
    add_span_attributes,
    add_span_event,
    get_current_span,
    get_tracer,
    set_span_status,
    traced,
)

__all__ = [
    "init_telemetry",
    "instrument_app",
    "shutdown_telemetry",
    "get_tracer",
    "traced",
    "get_current_span",
    "add_span_attributes",
    "add_span_event",
    "set_span_status",
]
