from typing import Any

import uvicorn

from src.config import settings


def get_uvicorn_config() -> dict[str, Any]:
    return {
        "host": settings.host,
        "port": settings.port,
        "log_level": settings.log_level.lower(),
        "proxy_headers": settings.behind_proxy,
        "forwarded_allow_ips": settings.forwarded_allow_ips,
        "reload": settings.reload and not settings.is_production(),
        "loop": "asyncio",
        "workers": settings.workers,
        "timeout_keep_alive": settings.timeout_keep_alive,
        # Disable uvicorn's default loggers to avoid duplicate logs
        # "access_log": False,
        # "log_config": None,
    }


if __name__ == "__main__":
    config = get_uvicorn_config()
    uvicorn.run("src.main:app", **config)
