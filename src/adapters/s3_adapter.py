from __future__ import annotations

import mimetypes
import time
import weakref
from dataclasses import dataclass, field
from typing import Mapping, Optional

import aioboto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import (
    ClientError,
    ConnectTimeoutError,
    EndpointConnectionError,
    ReadTimeoutError,
)
from fastapi import HTTPException, status
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from src.config import settings
from src.utilities.loggers.app_logger import logger


@dataclass(frozen=True)
class S3DirectConfig:
    """Configuration for talking directly to a MinIO / S3-compatible bucket."""

    endpoint_url: str = "https://minio.internal:9000"
    bucket_name: str = "unsigned_documents"
    access_key: str = "test"
    secret_key: str = "test"
    region_name: str = "us-east-1"
    use_ssl: bool = True
    verify_ssl: bool = True
    addressing_style: str = "path"  # MinIO generally needs "path", not "virtual"
    total_timeout: float = 60.0
    connect_timeout: float = 10.0
    retry_attempts: int = 3
    retry_min_wait: float = 0.25
    retry_max_wait: float = 2.0
    retry_statuses: tuple[int, ...] = (429, 500, 502, 503, 504)
    default_content_type: str = "application/octet-stream"
    static_metadata: Mapping[str, str] = field(default_factory=dict)
    debug_log_bodies: bool = False


class S3DirectAdapter:
    _owned_adapters: weakref.WeakSet["S3DirectAdapter"] = weakref.WeakSet()

    def __init__(self) -> None:
        self.cfg = S3DirectConfig(
            endpoint_url=settings.s3_endpoint_url,
            bucket_name=settings.s3_bucket_name,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            region_name=settings.s3_region_name,
            use_ssl=settings.s3_use_ssl,
            verify_ssl=settings.s3_verify_ssl,
        )
        self._session = aioboto3.Session()
        self._client = None

    async def _get_client(self):
        if self._client is not None:
            return self._client
        self._client = await self._session.client(
            "s3", **self._client_kwargs()
        ).__aenter__()
        logger.warning(
            {
                "event": "s3.client.session.created",
                "owned": True,
                "endpoint_url": self.cfg.endpoint_url,
                "bucket": self.cfg.bucket_name,
            }
        )
        S3DirectAdapter._owned_adapters.add(self)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.__aexit__(None, None, None)
            self._client = None

    @classmethod
    async def close_owned_sessions(cls) -> None:
        for adapter in list(cls._owned_adapters):
            try:
                await adapter.aclose()
            except Exception:
                pass

    def _client_kwargs(self) -> dict:
        return dict(
            endpoint_url=self.cfg.endpoint_url,
            aws_access_key_id=self.cfg.access_key,
            aws_secret_access_key=self.cfg.secret_key,
            region_name=self.cfg.region_name,
            use_ssl=self.cfg.use_ssl,
            verify=self.cfg.verify_ssl,
            config=BotoConfig(
                s3={"addressing_style": self.cfg.addressing_style},
                connect_timeout=self.cfg.connect_timeout,
                read_timeout=self.cfg.total_timeout,
            ),
        )

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    async def upload_document(
        self,
        key: str,
        content: bytes,
        *,
        content_type: str | None = None,
        metadata: Optional[Mapping[str, str]] = None,
        retry_attempts: int | None = None,
    ) -> None:
        """Upload a document (.docx, .txt, ...) to the bucket under `key`."""
        resolved_type = content_type or self._guess_content_type(key)
        merged_metadata = {**self.cfg.static_metadata, **(metadata or {})}

        await self._run_with_retry(
            "PUT",
            key,
            retry_attempts,
            self._do_upload,
            content,
            resolved_type,
            merged_metadata,
        )

    async def download_document(
        self,
        key: str,
        *,
        retry_attempts: int | None = None,
    ) -> bytes:
        """Download a document's bytes from the bucket."""
        return await self._run_with_retry("GET", key, retry_attempts, self._do_download)

    async def delete_document(
        self,
        key: str,
        *,
        retry_attempts: int | None = None,
    ) -> None:
        """Delete a document from the bucket."""
        await self._run_with_retry("DELETE", key, retry_attempts, self._do_delete)

    async def document_exists(self, key: str) -> bool:
        """Check whether a document exists without downloading it."""
        try:
            s3 = await self._get_client()
            await s3.head_object(Bucket=self.cfg.bucket_name, Key=key)
            return True
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code in ("404", "NoSuchKey", "NotFound"):
                return False
            raise self._map_client_error("HEAD", key, exc)

    async def list_documents(self, prefix: str = "") -> list[str]:
        """List document keys under an optional prefix."""
        keys: list[str] = []
        try:
            s3 = await self._get_client()
            paginator = s3.get_paginator("list_objects_v2")
            async for page in paginator.paginate(
                Bucket=self.cfg.bucket_name, Prefix=prefix
            ):
                for obj in page.get("Contents", []):
                    keys.append(obj["Key"])
        except ClientError as exc:
            raise self._map_client_error("LIST", prefix, exc)
        return keys

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    async def _do_upload(
        self,
        s3,
        key: str,
        content: bytes,
        content_type: str,
        metadata: Mapping[str, str],
    ) -> None:
        await s3.put_object(
            Bucket=self.cfg.bucket_name,
            Key=key,
            Body=content,
            ContentType=content_type,
            Metadata=dict(metadata),
        )

    async def _do_download(self, s3, key: str) -> bytes:
        resp = await s3.get_object(Bucket=self.cfg.bucket_name, Key=key)
        async with resp["Body"] as stream:
            return await stream.read()

    async def _do_delete(self, s3, key: str) -> None:
        await s3.delete_object(Bucket=self.cfg.bucket_name, Key=key)

    async def _run_with_retry(self, method: str, key: str, retry_attempts, fn, *args):
        attempts = max(
            1, retry_attempts if retry_attempts is not None else self.cfg.retry_attempts
        )

        def _retry_filter(exc: BaseException) -> bool:
            if isinstance(exc, HTTPException):
                return int(exc.status_code) in self.cfg.retry_statuses
            return isinstance(
                exc, (EndpointConnectionError, ConnectTimeoutError, ReadTimeoutError)
            )

        @retry(
            reraise=True,
            stop=stop_after_attempt(attempts),
            wait=wait_exponential(
                min=self.cfg.retry_min_wait, max=self.cfg.retry_max_wait
            ),
            retry=retry_if_exception(_retry_filter),
        )
        async def _do():
            t0 = time.perf_counter()
            try:
                s3 = await self._get_client()
                result = await fn(s3, key, *args)
                self._log_success(method, key, t0)
                return result
            except ClientError as exc:
                raise self._map_client_error(method, key, exc) from exc
            except (EndpointConnectionError, ConnectTimeoutError) as exc:
                self._log_network_err(method, key, exc)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Could not connect to storage backend",
                ) from exc
            except ReadTimeoutError as exc:
                self._log_timeout(method, key)
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail="Storage backend request timed out",
                ) from exc

        return await _do()

    def _map_client_error(
        self, method: str, key: str, exc: ClientError
    ) -> HTTPException:
        error = exc.response.get("Error", {})
        code = error.get("Code", "")
        message = error.get("Message", "S3 request failed")
        http_status = exc.response.get("ResponseMetadata", {}).get(
            "HTTPStatusCode", 502
        )

        logger.error(
            {
                "event": "s3.client.client_error",
                "method": method,
                "key": key,
                "bucket": self.cfg.bucket_name,
                "code": code,
                "status": http_status,
                "message": message,
            }
        )

        if code in ("404", "NoSuchKey", "NotFound"):
            return HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document not found: {key}",
            )

        return HTTPException(
            status_code=http_status or status.HTTP_502_BAD_GATEWAY, detail=message
        )

    def _log_success(self, method: str, key: str, t0: float) -> None:
        dur_ms = round((time.perf_counter() - t0) * 1000, 2)
        payload = {
            "event": "s3.client.success",
            "method": method,
            "key": key,
            "bucket": self.cfg.bucket_name,
            "dur_ms": dur_ms,
        }
        logger.debug(payload) if not self.cfg.debug_log_bodies else logger.debug(
            {
                **payload,
                "note": "debug_log_bodies is on but bodies are binary; not echoed",
            }
        )

    def _log_timeout(self, method: str, key: str) -> None:
        logger.warning(
            {
                "event": "s3.client.timeout",
                "method": method,
                "key": key,
                "bucket": self.cfg.bucket_name,
            }
        )

    def _log_network_err(self, method: str, key: str, exc: Exception) -> None:
        logger.error(
            {
                "event": "s3.client.network_error",
                "method": method,
                "key": key,
                "bucket": self.cfg.bucket_name,
                "exc": type(exc).__name__,
                "msg": str(exc),
            }
        )

    def _guess_content_type(self, key: str) -> str:
        lowered = key.lower()
        if lowered.endswith(".docx"):
            return (
                "application/vnd.openxmlformats-officedocument"
                ".wordprocessingml.document"
            )
        if lowered.endswith(".txt"):
            return "text/plain; charset=utf-8"
        guessed, _ = mimetypes.guess_type(key)
        return guessed or self.cfg.default_content_type
