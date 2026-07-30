from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware

from src.adapters.base_adapter import BaseAdapter
from src.config import settings
from src.database.engine import DBSessionManager
from src.exceptions.base_exception import ProjectBaseException
from src.exceptions.handlers import (
    base_exception_handler,
    http_exception_handler,
    unhandled_exception_handler,
)
from src.routers.admin_router import router as admin_router
from src.telemetry import instrument_app, shutdown_telemetry
from src.utilities.loggers.app_logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info({"event": "app.startup", "app_name": settings.app_name})

    DBSessionManager.initialize()
    app.state.db = DBSessionManager

    if settings.otel_enabled:
        logger.info(
            {
                "event": "telemetry.initialized",
                "exporter": settings.otel_exporter,
                "sample_rate": settings.otel_sample_rate,
            }
        )

    yield

    await DBSessionManager.close()
    await BaseAdapter.close_owned_sessions()
    shutdown_telemetry()
    logger.info({"event": "app.shutdown", "app_name": settings.app_name})


app = FastAPI(
    title=settings.app_name,
    description=settings.app_description,
    version=settings.app_version,
    lifespan=lifespan,
    debug=True,  # TEMPORARY: shows full tracebacks in Swagger. Remove once debugged.
)

instrument_app(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(ProjectBaseException, base_exception_handler)  # type: ignore
app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(admin_router)
