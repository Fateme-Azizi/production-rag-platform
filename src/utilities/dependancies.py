from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.s3_adapter import S3DirectAdapter
from src.database.repository.admins import AdminRepository
from src.database.repository.documents import DocumentRepository
from src.database.repository.query_logs import QueryLogRepository
from src.database.repository.users import UserRepository
from src.database.repository.vectors import VectorRepository
from src.services.process_service import ProcessFileService


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    from src.fastapi_app import app

    db_manager = getattr(app.state, "db", None)
    if db_manager is None:
        raise RuntimeError(
            "Database dependency has not been initialized on app startup."
        )

    async with db_manager.get_db() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_s3_adapter_service() -> S3DirectAdapter:
    return S3DirectAdapter()


async def get_admin_repository(
    session: AsyncSession = Depends(get_db_session),
) -> AdminRepository:
    return AdminRepository(session)


async def get_document_repository(
    session: AsyncSession = Depends(get_db_session),
) -> DocumentRepository:
    return DocumentRepository(session)


async def get_query_log_repository(
    session: AsyncSession = Depends(get_db_session),
) -> QueryLogRepository:
    return QueryLogRepository(session)


async def get_user_repository(
    session: AsyncSession = Depends(get_db_session),
) -> UserRepository:
    return UserRepository(session)


async def get_vectore_repository(
    session: AsyncSession = Depends(get_db_session),
) -> VectorRepository:
    return VectorRepository(session)


async def get_process_service(
    db: AsyncSession = Depends(get_db_session),
    s3_adapter: S3DirectAdapter = Depends(get_s3_adapter_service),
    admin_repository: AdminRepository = Depends(get_admin_repository),
    document_repository: DocumentRepository = Depends(get_document_repository),
    query_log_repository: QueryLogRepository = Depends(get_query_log_repository),
    user_repository: UserRepository = Depends(get_user_repository),
    vectore_storage: VectorRepository = Depends(get_vectore_repository),
):

    return ProcessFileService(
        db=db,
        s3_adapter=s3_adapter,
        admin_repository=admin_repository,
        document_repository=document_repository,
        query_log_repository=query_log_repository,
        user_repository=user_repository,
        vectore_storage=vectore_storage,
    )
