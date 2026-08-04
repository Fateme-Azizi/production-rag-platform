from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.query_logs import QueryLog
from src.database.repository.base_repository import BaseRepository


class QueryLogRepository(BaseRepository[QueryLog]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(QueryLog, session)
