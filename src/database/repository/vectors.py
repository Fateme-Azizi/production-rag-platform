from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.vectors import Vector
from src.database.repository.base_repository import BaseRepository


class VectorRepository(BaseRepository[Vector]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Vector, session)
