import magic
from pydantic import Base64Bytes
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.s3_adapter import S3DirectAdapter
from src.database.repository.admins import AdminRepository
from src.database.repository.documents import DocumentRepository
from src.database.repository.query_logs import QueryLogRepository
from src.database.repository.users import UserRepository
from src.database.repository.vectors import VectorRepository
from src.schemas.dtos.request_models.embed_files_request import EmbedFilesRequestModel
from src.schemas.dtos.request_models.upload_files_request import UploadRequestModel
from src.schemas.enums.document_status import DocumentStatus
from src.schemas.enums.document_type import DocumentType
from src.services.ingestion_service import IngestionService

EXPECTED_MIME_TYPES: dict[DocumentType, set[str]] = {
    DocumentType.PDF: {"application/pdf"},
    DocumentType.TXT: {"text/plain"},
    DocumentType.DOCS: {
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
        "text/plain",
    },
}


def type_mapping(type: str) -> DocumentType:
    try:
        return DocumentType(type)
    except ValueError as exc:
        raise ValueError(f"Unsupported document type: '{type}'") from exc


EXTENSION_MAP: dict[DocumentType, str] = {
    DocumentType.PDF: ".pdf",
    DocumentType.TXT: ".txt",
    DocumentType.DOCS: ".docx",
}


class ProcessFileService:
    def __init__(
        self,
        db: AsyncSession,
        s3_adapter: S3DirectAdapter,
        admin_repository: AdminRepository,
        document_repository: DocumentRepository,
        query_log_repository: QueryLogRepository,
        user_repository: UserRepository,
        vectore_storage: VectorRepository,
    ):
        self.db = db
        self.s3_adapter = s3_adapter
        self.admin_repository = admin_repository
        self.document_repository = document_repository
        self.query_log_repository = query_log_repository
        self.user_repository = user_repository
        self.vectore_storage = vectore_storage
        self.ingestion_service = IngestionService(
            db,
            s3_adapter,
            admin_repository,
            document_repository,
            query_log_repository,
            user_repository,
            vectore_storage,
        )

    async def upload_file_s3(self, data: UploadRequestModel):
        print("DATA IS HERE FOR UPLOAD")
        mime_type = self._detect_mime_type(data.file_bytes)
        expected_mime_types = EXPECTED_MIME_TYPES.get(data.type, set())
        if mime_type not in expected_mime_types:
            raise ValueError(
                f"Declared type '{data.type.value}' does not match detected "
                f"file content (got '{mime_type}')."
            )
        print("WAITING FOR UPLOAD")
        await self.s3_adapter.upload_document(
            key=data.s3_key + EXTENSION_MAP[data.type],
            content=data.file_bytes,
            content_type=EXTENSION_MAP[data.type],
        )
        print("UPLOADED WAITING FOR DB REGISTRY")
        document = await self.document_repository.create(
            {
                "type": data.type.value,
                "s3_bucket": data.s3_bucket,
                "s3_key": data.s3_key,
                "file_name": data.file_name,
                "file_size_bytes": data.file_size_bytes,
                "checksum": "",
                "status": DocumentStatus.PENDING,
                "title": data.title,
                "uploaded_by": "019f84cf-803b-70d4-bc47-8a9100b3859b",
            }
        )

        file_data = EmbedFilesRequestModel(
            document_id=document.id,
            file_size_bytes=data.file_size_bytes,
            type=data.type,
            s3_bucket=data.s3_bucket,
            s3_key=data.s3_key,
        )
        await self.ingestion_service.embed_files(file_data)
        return "DONE !!!!!!!!!!"

    def _detect_mime_type(self, file_bytes: Base64Bytes) -> str:

        return magic.from_buffer(file_bytes, mime=True)


# ---------------------------------------------------------------------- #
# Usage example
# ---------------------------------------------------------------------- #
#

# )
# adapter = S3DirectAdapter(cfg)
#
# await adapter.upload_document("reports/q1.docx", docx_bytes)
# text_bytes = await adapter.download_document("notes/meeting.txt")
# exists = await adapter.document_exists("reports/q1.docx")
# await adapter.delete_document("reports/q1.docx")
#
# # On app shutdown (e.g. FastAPI lifespan/shutdown event), close owned
# # clients the same way you'd call BaseAdapter.close_owned_sessions():
# await S3DirectAdapter.close_owned_sessions()
