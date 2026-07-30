# src/adapters/base_adapter.py
from __future__ import annotations

import asyncio
import time
import weakref
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import aiohttp
from aiohttp import ClientConnectorError, ClientError, ClientResponse, TCPConnector
from fastapi import HTTPException, status
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from src.utilities.errors import ErrorMap, ErrorMapper, error_mapper
from src.utilities.loggers.app_logger import logger


@dataclass(frozen=True)
class SimpleHttpConfig:
    """Configuration for HTTP client adapter."""

    base_url: str
    user_agent: str = "FastAPI-Baseline/1.0"
    total_timeout: float = 10.0
    connect_limit: int = 100
    keepalive_timeout: float = 30.0
    retry_attempts: int = 3
    retry_min_wait: float = 0.25
    retry_max_wait: float = 2.0
    retry_statuses: tuple[int, ...] = (429, 500, 502, 503, 504)
    debug_log_bodies: bool = False
    redact_keys: tuple[str, ...] = (
        "password",
        "secret",
        "token",
        "authorization",
        "api_key",
    )
    static_headers: Mapping[str, str] = field(default_factory=dict)


def _redact(obj: Any, keys: tuple[str, ...]) -> Any:
    """Recursively redact sensitive keys from logs."""
    try:
        if isinstance(obj, Mapping):
            return {
                k: ("***" if k.lower() in keys else _redact(v, keys))
                for k, v in obj.items()
            }
        if isinstance(obj, (list, tuple)):
            return type(obj)(_redact(v, keys) for v in obj)
    except Exception:
        pass
    return obj


class BaseAdapter:
    """
    Generic HTTP adapter with retries, redaction, structured logging, and
    error translation using ErrorMap / ErrorMapper.
    """

    _owned_adapters: weakref.WeakSet[BaseAdapter] = weakref.WeakSet()

    def __init__(
        self, cfg: SimpleHttpConfig, session: aiohttp.ClientSession | None = None
    ) -> None:
        self.cfg = cfg
        self._session = session
        self._connector: TCPConnector | None = None
        self._owns_session = session is None

    # ---------------- HTTP verbs ----------------
    async def get(
        self,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
        error_overrides: list[ErrorMap] | None = None,
        retry_attempts: int | None = None,
    ) -> Any:
        return await self._request(
            "GET",
            path,
            params=params,
            headers=headers,
            timeout=timeout,
            error_overrides=error_overrides,
            retry_attempts=retry_attempts,
        )

    async def post(
        self,
        path: str,
        *,
        json_body: Any | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
        error_overrides: list[ErrorMap] | None = None,
        retry_attempts: int | None = None,
    ) -> Any:
        return await self._request(
            "POST",
            path,
            json_body=json_body,
            headers=headers,
            timeout=timeout,
            error_overrides=error_overrides,
            retry_attempts=retry_attempts,
        )

    async def put(
        self,
        path: str,
        *,
        json_body: Any | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
        error_overrides: list[ErrorMap] | None = None,
        retry_attempts: int | None = None,
    ) -> Any:
        return await self._request(
            "PUT",
            path,
            json_body=json_body,
            headers=headers,
            timeout=timeout,
            error_overrides=error_overrides,
            retry_attempts=retry_attempts,
        )

    async def patch(
        self,
        path: str,
        *,
        json_body: Any | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
        error_overrides: list[ErrorMap] | None = None,
        retry_attempts: int | None = None,
    ) -> Any:
        return await self._request(
            "PATCH",
            path,
            json_body=json_body,
            headers=headers,
            timeout=timeout,
            error_overrides=error_overrides,
            retry_attempts=retry_attempts,
        )

    async def delete(
        self,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
        error_overrides: list[ErrorMap] | None = None,
        retry_attempts: int | None = None,
    ) -> Any:
        return await self._request(
            "DELETE",
            path,
            headers=headers,
            timeout=timeout,
            error_overrides=error_overrides,
            retry_attempts=retry_attempts,
        )

    # ---------------- core request ----------------
    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        json_body: Any | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
        error_overrides: list[ErrorMap] | None = None,
        retry_attempts: int | None = None,
    ) -> Any:
        url = self._join(self.cfg.base_url, path)
        hdrs = self.build_headers(headers)
        req_timeout = aiohttp.ClientTimeout(total=timeout or self.cfg.total_timeout)
        attempts = (
            retry_attempts if retry_attempts is not None else self.cfg.retry_attempts
        )

        def _retry_filter(e: BaseException) -> bool:
            if isinstance(e, HTTPException):
                return int(getattr(e, "status_code", 0)) in self.cfg.retry_statuses
            return isinstance(
                e, (asyncio.TimeoutError, ClientError, ClientConnectorError)
            )

        @retry(
            reraise=True,
            stop=stop_after_attempt(attempts),
            wait=wait_exponential(
                min=self.cfg.retry_min_wait, max=self.cfg.retry_max_wait
            ),
            retry=retry_if_exception(_retry_filter),
        )
        async def _do() -> Any:
            t0 = time.perf_counter()

            try:
                self._log_debug(
                    f"Request: {method} {url} Headers: {hdrs} Params: {params} Body: {json_body}"
                )
                async with self._get_session().request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    headers=hdrs,
                    timeout=req_timeout,
                ) as resp:
                    self._log_debug(f"Response headers: {resp.headers}")

                    try:
                        self._log_debug(f"Response body: {await resp.json()}")
                    except Exception:
                        self._log_debug(f"Response body: {await resp.text()}")

                    body = await self._parse_json(resp)

                    if 200 <= resp.status < 300:
                        self._log_success(
                            method, url, t0, resp.status, params, json_body, body
                        )
                        return body

                    # Handle non-2xx via structured error mapper
                    await self._handle_error(resp, body, url, error_overrides)

            except TimeoutError:
                self._log_timeout(method, url)
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail="Upstream timeout",
                )

            except ClientConnectorError as ex:
                self._log_network_err(method, url, ex)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Connection failed",
                )

            except ClientError as ex:
                self._log_client_err(method, url, ex)
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="HTTP client error",
                )

        return await _do()

    async def _handle_error(
        self,
        resp: ClientResponse,
        body: Any,
        url: str,
        local_overrides: list[ErrorMap] | None,
    ) -> None:
        """Handles non-2xx upstream responses with local-first, then global fallback."""
        upstream_message = ""
        if isinstance(body, dict):
            upstream_message = body.get("error") or body.get("message") or ""
            if isinstance(upstream_message, dict):
                upstream_message = body.get("message") or ""
        elif isinstance(body, str):
            upstream_message = body

        if local_overrides:
            local_mapper = ErrorMapper(overrides=local_overrides)
            matched = local_mapper.try_translate(resp.status, upstream_message)
            if matched:
                new_status, new_message = matched
                logger.error(
                    {
                        "event": "http.client.error",
                        "url": url,
                        "status": resp.status,
                        "upstream_message": upstream_message,
                        "mapped_status": new_status,
                        "mapped_message": new_message,
                        "scope": "local_overrides",
                    }
                )
                raise HTTPException(status_code=new_status, detail=new_message)

        matched = error_mapper.try_translate(resp.status, upstream_message)
        if matched:
            new_status, new_message = matched
            logger.debug(
                {
                    "event": "http.client.error.fallback_global",
                    "url": url,
                    "status": resp.status,
                    "upstream_message": upstream_message,
                    "mapped_status": new_status,
                    "mapped_message": new_message,
                    "scope": "GLOBAL_ERROR_OVERRIDES",
                }
            )
            raise HTTPException(status_code=new_status, detail=new_message)

        logger.debug(
            {
                "event": "http.client.error.unmapped",
                "url": url,
                "status": resp.status,
                "upstream_message": upstream_message,
                "mapped_status": resp.status,
                "mapped_message": "Unexpected error occurred",
                "scope": "no_match",
            }
        )
        raise HTTPException(status_code=resp.status, detail="Unexpected error occurred")

    async def _parse_json(self, resp: ClientResponse) -> Any:
        try:
            return await resp.json(content_type=None)
        except Exception:
            try:
                txt = await resp.text()
            except Exception:
                txt = "<no body>"
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"message": "Invalid JSON from upstream", "body": txt[:500]},
            )

    # ---------------- session and headers ----------------
    def build_headers(self, extra: Mapping[str, str] | None = None) -> dict[str, str]:
        final: dict[str, str] = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": self.cfg.user_agent,
        }
        if self.cfg.static_headers:
            final.update(dict(self.cfg.static_headers))
        if extra:
            final.update(dict(extra))
        return final

    def _join(self, base: str, path: str) -> str:
        base = base.rstrip("/")
        p = path.lstrip("/")
        return f"{base}/{p}" if p else base

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session and not self._session.closed:
            return self._session
        # create & own session
        self._connector = aiohttp.TCPConnector(
            limit=self.cfg.connect_limit,
            keepalive_timeout=self.cfg.keepalive_timeout,
        )
        self._session = aiohttp.ClientSession(
            connector=self._connector,
            connector_owner=True,
            timeout=aiohttp.ClientTimeout(total=self.cfg.total_timeout),
        )
        self._owns_session = True
        logger.warning(
            {
                "event": "http.client.session.created",
                "owned": True,
                "base_url": self.cfg.base_url,
            }
        )
        BaseAdapter._owned_adapters.add(self)
        return self._session

    async def aclose(self) -> None:
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()

    @classmethod
    async def close_owned_sessions(cls) -> None:
        for adapter in list(cls._owned_adapters):
            try:
                await adapter.aclose()
            except Exception:
                pass

    def _log_success(
        self,
        method: str,
        url: str,
        t0: float,
        status_code: int,
        params: Any,
        req_json: Any,
        resp_json: Any,
    ) -> None:
        dur_ms = round((time.perf_counter() - t0) * 1000)
        payload: dict[str, Any] = {
            "event": "http.client.success",
            "method": method,
            "url": url,
            "status": status_code,
            "dur_ms": dur_ms,
        }
        if self.cfg.debug_log_bodies:
            payload["request"] = _redact(
                {"params": params, "json": req_json}, self.cfg.redact_keys
            )
            payload["response"] = _redact(resp_json, self.cfg.redact_keys)
        logger.debug(payload)

    def _log_timeout(self, method: str, url: str) -> None:
        logger.warning({"event": "http.client.timeout", "method": method, "url": url})

    def _log_network_err(self, method: str, url: str, ex: Exception) -> None:
        logger.error(
            {
                "event": "http.client.network_error",
                "method": method,
                "url": url,
                "exc": type(ex).__name__,
                "msg": str(ex),
            }
        )

    def _log_client_err(self, method: str, url: str, ex: Exception) -> None:
        logger.error(
            {
                "event": "http.client.client_error",
                "method": method,
                "url": url,
                "exc": type(ex).__name__,
                "msg": str(ex),
            }
        )

    def _log_debug(self, msg: str) -> None:
        logger.debug({"event": "http.client.debug", "msg": msg})
