import logging
import traceback
from typing import Any, Generic, Literal, TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger(__name__)

# BaseModel type hint - users should bind T to their own BaseModel
T = TypeVar("T", bound=DeclarativeBase)


class BaseRepository(Generic[T]):
    """Base repository for database operations (session-injected/UoW-friendly)"""

    def __init__(
        self,
        model: type[T],
        session: AsyncSession,
        logger_instance: logging.Logger | None = None,
    ) -> None:
        self.model = model
        self.session = session
        self._logger = logger_instance or logger

    async def get_all(self) -> list[T]:
        query = select(self.model)
        try:
            result = await self.session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError:
            logger.error(
                f"Error getting all records for model {self.model.__name__}: {traceback.format_exc()}"
            )
            raise

    async def get_by_id(self, id: int | UUID) -> T | None:
        try:
            return await self.session.get(self.model, id)
        except SQLAlchemyError:
            logger.error(
                f"Error getting record by ID for model {self.model.__name__}: {traceback.format_exc()}"
            )
            raise

    async def create(self, obj_in: dict[str, Any]) -> T:
        db_obj = self.model(**obj_in)
        try:
            self.session.add(db_obj)
            # Let UoW/Service manage commit; just flush/refresh here
            await self.session.flush()
            await self.session.refresh(db_obj)
            return db_obj
        except IntegrityError:
            logger.error(
                f"Error creating record for model {self.model.__name__}: {traceback.format_exc()}"
            )
            raise
        except SQLAlchemyError:
            logger.error(
                f"Error creating record for model {self.model.__name__}: {traceback.format_exc()}"
            )
            raise

    async def update(self, id: int | UUID, obj_in: dict[str, Any]) -> T:
        db_obj = await self.get_by_id(id)
        if not db_obj:
            raise ValueError(f"Record with id {id} not found")

        for key, value in obj_in.items():
            if hasattr(db_obj, key):
                setattr(db_obj, key, value)

        try:
            self.session.add(db_obj)
            await self.session.flush()
            await self.session.refresh(db_obj)
            return db_obj
        except SQLAlchemyError:
            logger.error(
                f"Error updating record for model {self.model.__name__}: {traceback.format_exc()}"
            )
            raise

    async def delete(self, id: int | UUID) -> bool:
        db_obj = await self.get_by_id(id)
        if not db_obj:
            raise ValueError(f"Record with id {id} not found")

        try:
            await self.session.delete(db_obj)
            # No commit here; caller manages transaction
            return True
        except SQLAlchemyError:
            logger.error(
                f"Error deleting record for model {self.model.__name__}: {traceback.format_exc()}"
            )
            raise

    async def find(
        self,
        sort: Literal["asc", "desc"] | None = None,
        sort_by: str | None = None,
        **kwargs: Any,
    ) -> list[T]:
        query = select(self.model)
        for key, value in kwargs.items():
            if hasattr(self.model, key):
                query = query.where(getattr(self.model, key) == value)
        if sort and sort_by:
            sort_attr = getattr(self.model, sort_by, None)
            if sort_attr is not None:
                if sort == "asc":
                    query = query.order_by(sort_attr.asc())
                elif sort == "desc":
                    query = query.order_by(sort_attr.desc())
        elif sort and hasattr(self.model, "created_at"):
            # Default to created_at if sort_by not specified
            created_at_attr = getattr(self.model, "created_at", None)
            if created_at_attr is not None:
                if sort == "asc":
                    query = query.order_by(created_at_attr.asc())
                elif sort == "desc":
                    query = query.order_by(created_at_attr.desc())
        try:
            result = await self.session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError:
            logger.error(
                f"Error filtering records for model {self.model.__name__}: {traceback.format_exc()}"
            )
            raise

    async def find_one(
        self,
        sort: Literal["asc", "desc"] | None = None,
        sort_by: str | None = None,
        **kwargs: Any,
    ) -> T | None:
        query = select(self.model)
        for key, value in kwargs.items():
            if hasattr(self.model, key):
                query = query.where(getattr(self.model, key) == value)
        if sort and sort_by:
            sort_attr = getattr(self.model, sort_by, None)
            if sort_attr is not None:
                if sort == "asc":
                    query = query.order_by(sort_attr.asc())
                elif sort == "desc":
                    query = query.order_by(sort_attr.desc())
        elif sort and hasattr(self.model, "created_at"):
            # Default to created_at if sort_by not specified
            created_at_attr = getattr(self.model, "created_at", None)
            if created_at_attr is not None:
                if sort == "asc":
                    query = query.order_by(created_at_attr.asc())
                elif sort == "desc":
                    query = query.order_by(created_at_attr.desc())
        try:
            result = await self.session.execute(query)
            return result.scalars().first()
        except SQLAlchemyError:
            logger.error(
                f"Error finding one record for model {self.model.__name__}: {traceback.format_exc()}"
            )
            raise
