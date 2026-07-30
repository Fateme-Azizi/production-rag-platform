import json
import logging
import logging.handlers
import sys
from datetime import datetime
from typing import Any, Dict, Mapping, Optional

from loguru import logger as loguru_logger
from pydantic import BaseModel

from src.config import settings


class LogRecord(BaseModel):
    timestamp: datetime
    level: str
    message: str
    module: str
    function: str
    line: int
    extra: Optional[Dict[str, Any]] = None


loguru_logger.remove()


def _safe(value: Any, depth: int = 0) -> Any:
    """Make values JSON-serializable and keep logs bounded."""
    if depth > 4:
        return repr(value)
    if value is None or isinstance(value, (bool, int, float, str)):
        if isinstance(value, str) and len(value) > 5000:
            return value[:5000] + "…"
        return value
    if isinstance(value, (list, tuple, set)):
        return [_safe(v, depth + 1) for v in value]
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for k, v in value.items():
            try:
                key = str(k)
            except Exception:
                key = repr(k)
            out[key] = _safe(v, depth + 1)
        return out
    if isinstance(value, datetime):
        return value.isoformat()
    # pydantic models, dataclasses, etc.
    try:
        if hasattr(value, "model_dump"):
            return _safe(value.model_dump(), depth + 1)
    except Exception:
        pass
    try:
        return json.loads(json.dumps(value))
    except Exception:
        return repr(value)


def _patch_record(record: Any) -> None:
    """Sanitize log record before sinks (especially important with enqueue=True)."""
    # Drop exception object (often unpicklable); message & traceback text still logged.
    if record.get("exception") is not None:
        record["exception"] = None
    # Force extras to JSON-safe primitives
    record["extra"] = _safe(record.get("extra") or {})


loguru_logger.configure(patcher=_patch_record)


def serialize_record(record: Mapping[str, Any]) -> str:
    try:
        log_data = LogRecord(
            timestamp=record["time"],
            level=(
                record["level"].name
                if hasattr(record["level"], "name")
                else str(record["level"])
            ),
            message=record["message"],
            module=record["module"],
            function=record["function"],
            line=record["line"],
            extra=record.get("extra") or None,
        )
        return log_data.model_dump_json()
    except Exception as e:
        return json.dumps(
            {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "level": "ERROR",
                "message": f"Failed to serialize log: {e}",
                "original_message": record.get("message"),
            }
        )


def console_sink(message: Any) -> None:
    record = message.record
    sys.stdout.write(serialize_record(record) + "\n")
    sys.stdout.flush()


if settings.enable_console_logging:
    # Avoid pickling issues entirely; set to True only if you must,
    # but keep the patcher above in place.
    loguru_logger.add(
        console_sink,
        level=settings.log_level.upper(),
        enqueue=False,
        backtrace=False,
        diagnose=False,
    )


if settings.enable_syslog_logging and settings.syslog_host:
    syslog_logger = logging.getLogger("syslog")
    syslog_logger.setLevel(getattr(logging, settings.log_level.upper(), logging.DEBUG))

    syslog_handler = logging.handlers.SysLogHandler(
        address=(settings.syslog_host, settings.syslog_port),
        facility=logging.handlers.SysLogHandler.LOG_USER,
    )
    # Pass-through: we already emit JSON with serialize_record()
    syslog_handler.setFormatter(logging.Formatter("%(message)s"))
    syslog_logger.addHandler(syslog_handler)

    def syslog_sink(message: Any) -> None:
        record = message.record
        syslog_logger.info(serialize_record(record))

    loguru_logger.add(
        syslog_sink,
        level=settings.log_level.upper(),
        enqueue=False,
        backtrace=False,
        diagnose=False,
    )


logger = loguru_logger
