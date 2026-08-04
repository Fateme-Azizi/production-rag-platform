from uuid import UUID

from pydantic import BaseModel

from src.schemas.enums.document_type import DocumentType


class EmbedFilesRequestModel(BaseModel):
    document_id: UUID
    file_size_bytes: int
    type: DocumentType
    s3_bucket: str
    s3_key: str
