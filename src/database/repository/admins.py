from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.admins import Admin
from src.database.repository.base_repository import BaseRepository


class AdminRepository(BaseRepository[Admin]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Admin, session)
