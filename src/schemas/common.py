from __future__ import annotations

from datetime import datetime, timezone
from typing import Generic, Optional, TypeVar

from fastapi import Request
from pydantic import BaseModel

from src.exceptions.handlers import get_request_id

T = TypeVar("T")


class ResponseMeta(BaseModel):
    request_id: str
    timestamp: datetime
    path: str

    def __init__(self, request: Request) -> None:
        super().__init__(
            request_id=get_request_id(request),
            timestamp=datetime.now(tz=timezone.utc),
            path=request.url.path,
        )


class ApiResponse(BaseModel, Generic[T]):
    data: Optional[T] = None
    meta: ResponseMeta

    @staticmethod
    def now_utc() -> datetime:
        return datetime.now(tz=timezone.utc)
