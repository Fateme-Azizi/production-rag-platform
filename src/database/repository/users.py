from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.users import User
from src.database.repository.base_repository import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(User, session)
