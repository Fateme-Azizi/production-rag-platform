from typing import Any, Awaitable, Callable, Optional, TypeVar

from faststream.rabbit.fastapi import RabbitRouter
from faststream.rabbit.opentelemetry import RabbitTelemetryMiddleware
from faststream.rabbit.schemas import ExchangeType, RabbitExchange
from pydantic import BaseModel, ValidationError

from src.config import settings
from src.exceptions.base_exception import ProjectBaseException
from src.utilities.loggers.app_logger import logger

T = TypeVar("T", bound=BaseModel)


class RabbitMQService:
    _instance: Optional["RabbitMQService"] = None
    _router: Optional[RabbitRouter] = None
    _initialized: bool = False

    @classmethod
    def log_info(cls, event: str, message: Optional[str] = None, **kwargs: Any) -> None:
        logger.info(event, src="rabbitmq", message=message, event=event, **kwargs)

    @classmethod
    def log_error(
        cls, event: str, message: Optional[str] = None, **kwargs: Any
    ) -> None:
        logger.exception(event, src="rabbitmq", message=message, event=event, **kwargs)

    def __new__(cls) -> "RabbitMQService":
        """Implement singleton pattern for connection pooling."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize RabbitMQService and setup router if not already done."""
        if not self._initialized:
            self._setup_router()
            RabbitMQService._initialized = True

    def _setup_router(self) -> None:
        """Initialize RabbitRouter with middleware and configuration."""
        middlewares = []

        # Add OpenTelemetry middleware if enabled
        if settings.otel_enabled and settings.otel_instrument_aiopika:
            try:
                middlewares.append(RabbitTelemetryMiddleware())
                RabbitMQService.log_info("rabbitmq.telemetry_enabled")
            except (ImportError, Exception) as e:
                logger.warning(
                    {
                        "event": "rabbitmq.telemetry_setup_failed",
                        "error": str(e),
                    }
                )

        # Initialize router with connection pooling
        RabbitMQService._router = RabbitRouter(
            url=settings.rabbitmq_uri,
            virtualhost=settings.rabbitmq_vhost,
            logger=logger,
            middlewares=middlewares,
        )

        RabbitMQService.log_info(
            "router_initialized",
            virtualhost=settings.rabbitmq_vhost,
            uri=settings.rabbitmq_uri.split("@")[-1],  # Hide credentials
        )

    async def publish(
        self,
        message: Any,
        exchange: str,
        routing_key: str = "",
        exchange_type: ExchangeType = ExchangeType.TOPIC,
        mandatory: bool = True,
        immediate: bool = False,
        timeout: Optional[float] = 10.0,
        **kwargs: Any,
    ) -> None:
        """
        Publish a message to a RabbitMQ exchange with reliability patterns.

        Args:
            message: The message payload (will be JSON-serialized if dict/Pydantic model)
            exchange: Exchange name. If None, uses default exchange
            routing_key: Routing key for message delivery
            exchange_type: Type of exchange (direct, topic, fanout, headers)
            mandatory: If True, message must be routable to a queue
            immediate: If True, message must be deliverable to a consumer immediately
            timeout: Publish timeout in seconds
            **kwargs: Additional broker publish arguments

        Raises:
            RuntimeError: If router/broker is not initialized
            Exception: If message publishing fails

        Example:
            ```python
            # Publish to a direct exchange with routing key
            await rabbitmq_service.publish(
                message={"order_id": "123", "status": "completed"},
                exchange="orders",
                routing_key="order.completed",
                mandatory=True
            )

            # Publish to a topic exchange
            await rabbitmq_service.publish(
                message=payment_event,
                exchange=RabbitExchange(
                    name="payments",
                    type=ExchangeType.TOPIC,
                    durable=True
                ),
                routing_key="payment.settled",
            )

            # Publish to default exchange (direct to queue)
            await rabbitmq_service.publish(
                message=task,
                routing_key="task_queue",
            )
            ```
        """
        if self._router is None or self._router.broker is None:
            raise RuntimeError("RabbitMQ notification router/broker not initialized")

        exchange_obj = RabbitExchange(
            name=exchange,
            type=exchange_type,
            durable=True,
        )

        try:
            logger.debug(
                {
                    "event": "rabbitmq.publish_attempt",
                    "exchange": exchange_obj.name if exchange_obj else "default",
                    "routing_key": routing_key,
                    "mandatory": mandatory,
                }
            )

            await self._router.broker.publish(
                message=message,
                exchange=exchange_obj,
                routing_key=routing_key,
                mandatory=mandatory,
                immediate=immediate,
                timeout=timeout,
                **kwargs,
            )
            RabbitMQService.log_info(
                "rabbitmq.message_published",
                exchange=exchange_obj.name if exchange_obj else "default",
                routing_key=routing_key,
            )

        except Exception as e:
            RabbitMQService.log_error(
                "rabbitmq.publish_failed",
                exchange=exchange_obj.name if exchange_obj else "default",
                routing_key=routing_key,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

    @classmethod
    def get_router(cls) -> RabbitRouter:
        instance = cls()
        if instance._router is None:
            raise RuntimeError("RabbitMQ router not initialized")
        return instance._router


    @classmethod
    async def consume(
        cls,
        event_name: str,
        raw_message: Any,
        model_class: type[T],
        callback: Callable[[T], Awaitable[None]],
    ) -> None:
        raw_content = raw_message.body

        if isinstance(raw_content, bytes):
            raw_content = raw_content.decode("utf-8")

        try:
            message = model_class.model_validate_json(
                raw_content if isinstance(raw_content, str) else raw_content
            )

            cls.log_info(f"{event_name}.validation_succeeded", raw_content)

            await callback(message)

            await raw_message.ack()
            cls.log_info(f"{event_name}.processed")

        except ValidationError as e:
            RabbitMQService.log_error(
                f"{event_name}.validation_failed",
                error=str(e),
                error_type=type(e).__name__,
                raw_message=raw_content,
                action="rejecting_to_dlx",
            )
            await raw_message.nack(requeue=False)
        except ProjectBaseException as e:
            RabbitMQService.log_error(
                f"{event_name}.processing_failed",
                error=str(e),
                error_type=type(e).__name__,
                raw_message=raw_content,
                action="rejecting_to_dlx",
            )
            await raw_message.nack(requeue=False)
        except Exception as e:
            RabbitMQService.log_error(
                f"{event_name}.unexpected_error",
                error=str(e),
                error_type=type(e).__name__,
                raw_message=raw_content,
                action="rejecting_to_dlx",
            )
            await raw_message.nack(requeue=False)


# Global singleton instance
rabbitmq_service = RabbitMQService()


def get_rabbitmq_service() -> RabbitMQService:
    return rabbitmq_service
