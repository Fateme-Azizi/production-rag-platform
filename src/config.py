from __future__ import annotations

import json
from ipaddress import IPv4Address
from typing import Annotated, List, Literal, Optional

from pydantic import BeforeValidator, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_int_list(v: object) -> List[int]:
    """Parse comma-separated or JSON array of integers."""
    if v is None or v == "":
        return []
    if isinstance(v, list):
        return [int(x) for x in v]
    if isinstance(v, str):
        s = v.strip()
        if s.startswith("["):
            try:
                arr = json.loads(s)
                return [int(x) for x in arr]
            except Exception:
                pass
        return [int(p.strip()) for p in s.split(",") if p.strip()]
    return []


def _parse_str_list(v: object) -> List[str]:
    """Parse comma-separated or JSON array of strings."""
    if v is None or v == "":
        return []
    if isinstance(v, list):
        return [str(x) for x in v]
    if isinstance(v, str):
        s = v.strip()
        if s.startswith("["):
            try:
                return json.loads(s)
            except Exception:
                pass
        return [p.strip() for p in s.split(",") if p.strip()]
    return []


# Custom types that handle CSV parsing before pydantic-settings tries JSON decode
IntList = Annotated[List[int], BeforeValidator(_parse_int_list)]
StrList = Annotated[List[str], BeforeValidator(_parse_str_list)]


class Settings(BaseSettings):
    """
    Central application configuration (Pydantic v2).

    Conventions:
    - All env vars use flat naming with underscores.
    - Supports .env file for local development.
    """

    # -------------------------------------------------------------------------
    # Meta / Environment
    # -------------------------------------------------------------------------
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "fastapi-baseline"
    app_description: str = "FastAPI Baseline Application"
    app_version: str = "0.1.0"
    env: Literal["dev", "staging", "production"] = "dev"
    behind_proxy: bool = False

    # -------------------------------------------------------------------------
    # HTTP Server (Uvicorn)
    # -------------------------------------------------------------------------
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1
    timeout_keep_alive: int = 30
    limit_concurrency: int | None = None
    limit_max_requests: int | None = None
    forwarded_allow_ips: str = "*"
    reload: bool = True  # keep False in prod

    # -------------------------------------------------------------------------
    # Logging
    # -------------------------------------------------------------------------
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "DEBUG"
    enable_console_logging: bool = True
    enable_syslog_logging: bool = False
    enable_request_logging: bool = True
    base_dir: str = "logs"
    retention_count: int = 7
    syslog_host: str | None = None
    syslog_port: int = 514
    traceback_limit: int = 1

    # -------------------------------------------------------------------------
    # HTTP Client (aiohttp) — shared defaults for adapters
    # -------------------------------------------------------------------------
    http_user_agent: str = "FastAPI-Baseline/1.0"

    http_max_connections: int = Field(
        100, description="Max concurrent upstream connections for aiohttp pool"
    )
    http_total_timeout: float = Field(
        10.0, description="Total request timeout in seconds"
    )
    http_connect_timeout: float = Field(3.0, description="Connect timeout in seconds")
    http_read_timeout: float = Field(
        7.0, description="Read (sock_read) timeout in seconds"
    )
    http_keepalive_timeout: float = Field(
        30.0, description="Keep-alive idle timeout for pooled connections"
    )

    # Retries / resilience (used by BaseAdapter)
    http_retry_attempts: int = 3
    http_retry_min_wait: float = 0.25
    http_retry_max_wait: float = 2.0
    # Accept CSV ("429,500,502,503,504") or JSON array ([429,500,...])
    http_retry_status_codes: IntList = Field(
        default=[429, 500, 502, 503, 504],
        description="HTTP status codes that trigger retry",
    )

    # Debug body logging & redaction (DEV ONLY; never enable in prod)
    debug_http_bodies: bool = False
    http_log_redact_keys: StrList = Field(
        default=["password", "secret", "token", "authorization", "api_key"],
        description="Keys to redact from HTTP logs",
    )

    # -------------------------------------------------------------------------
    # Database (Optional - PostgreSQL)
    # -------------------------------------------------------------------------
    database_use_uri: bool = False
    database_uri: Optional[str] = None
    database_server: Optional[str | IPv4Address] = None
    database_port: Optional[int] = None
    database_name: Optional[str] = None
    database_username: Optional[str] = None
    database_password: Optional[str] = None

    # -------------------------------------------------------------------------
    # Embeddings
    # -------------------------------------------------------------------------
    embedding_device: str = "cpu"  # "cpu" or "cuda"

    # -------------------------------------------------------------------------
    # MINIO & S3
    # -------------------------------------------------------------------------
    s3_endpoint_url: str = "http://localhost:9000"
    s3_bucket_name: str = "unsigned-documents"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_region_name: str = "us-east-1"
    s3_use_ssl: bool = False
    s3_verify_ssl: bool = False
    # -------------------------------------------------------------------------
    # RabbitMQ
    rabbitmq_uri: str = Field(
        # default="amqp://guest:guest@localhost:5672",
        description="RabbitMQ URI",
    )
    rabbitmq_vhost: str = Field(
        default="/",
        description="RabbitMQ virtual host",
    )
    # -----------------------------------------------------------------------------
    # -------------------------------------------------------------------------
    # OpenTelemetry / Tracing
    # -------------------------------------------------------------------------
    otel_enabled: bool = Field(
        default=False, description="Enable OpenTelemetry tracing"
    )
    otel_service_name: str | None = Field(
        default=None,
        description="Service name for tracing (defaults to app_name if not set)",
    )
    otel_exporter: Literal["console", "otlp", "none"] = Field(
        default="console",
        description="Trace exporter type: 'console' for dev, 'otlp' for production",
    )
    otel_otlp_endpoint: str = Field(
        default="http://localhost:4317",
        description="OTLP collector endpoint (gRPC)",
    )
    otel_otlp_http_endpoint: str | None = Field(
        default=None,
        description="OTLP collector HTTP endpoint (if using HTTP instead of gRPC)",
    )
    otel_sample_rate: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Trace sampling rate (0.0 to 1.0). Use lower values in production.",
    )
    otel_propagators: str = Field(
        default="tracecontext,baggage",
        description="Comma-separated list of propagators (tracecontext, baggage, b3, etc.)",
    )
    otel_instrument_fastapi: bool = Field(
        default=True, description="Auto-instrument FastAPI with OpenTelemetry"
    )
    otel_instrument_aiohttp: bool = Field(
        default=True, description="Auto-instrument aiohttp client with OpenTelemetry"
    )
    otel_instrument_aiopika: bool = Field(
        default=True, description="Auto-instrument aiopika client with OpenTelemetry"
    )
    otel_instrument_logging: bool = Field(
        default=False, description="Inject trace context into logs"
    )

    # -------------------------------------------------------------------------
    # Computed properties
    # -------------------------------------------------------------------------
    def is_production(self) -> bool:
        if self.env.lower() == "production":
            self.reload = False
            return True
        return False


settings = Settings()  # type: ignore
