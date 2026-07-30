import logging.handlers
from os import makedirs, path, sep

from src.config import settings

middleware_req_logger = logging.getLogger("MiddlewareReqFileLogger")
middleware_req_logger.setLevel(logging.DEBUG)

middleware_req_log_formatter = logging.Formatter(
    '{"server_instance": "%(instance_name)s",'
    '"time": "%(asctime)s",'
    '"function": "logging_middleware",'
    '"level": "%(levelname)s",'
    '"microservice": "%(microservice)s",'
    '"client_ip": "%(client_ip)s",'
    '"request_path": "%(request_path)s",'
    '"request_id": "%(request_id)s",'
    '"request_body": "%(request_body)s"}',
    defaults={"instance_name": settings.app_name},
)

if settings.enable_request_logging is True:
    log_dir = (
        path.dirname(path.dirname(path.dirname(path.dirname(path.abspath(__file__)))))
        + sep
        + "logs"
    )
    makedirs(log_dir, exist_ok=True)

    middleware_req_log_handler = logging.handlers.TimedRotatingFileHandler(
        log_dir + sep + "requests.json",
        when="midnight",
        interval=1,
        backupCount=settings.retention_count,
        encoding="utf-8",
        delay=True,
        utc=True,
    )
    middleware_req_log_handler.setLevel(logging.DEBUG)
    middleware_req_log_handler.setFormatter(middleware_req_log_formatter)
    middleware_req_logger.addHandler(middleware_req_log_handler)

if settings.enable_syslog_logging is True:
    syslog_logger = logging.getLogger("syslog")
    syslog_logger.setLevel(getattr(logging, settings.log_level.upper(), logging.DEBUG))

    syslog_handler = logging.handlers.SysLogHandler(
        address=((settings.syslog_host or "localhost"), settings.syslog_port),
        facility=logging.handlers.SysLogHandler.LOG_USER,
    )
    # Pass-through: we already emit JSON with serialize_record()
    syslog_handler.setLevel(logging.DEBUG)
    syslog_handler.setFormatter(middleware_req_log_formatter)
    middleware_req_logger.addHandler(syslog_handler)
