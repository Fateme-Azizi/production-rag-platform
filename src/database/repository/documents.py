from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.documents import Document
from src.database.repository.base_repository import BaseRepository


class DocumentRepository(BaseRepository[Document]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Document, session)
