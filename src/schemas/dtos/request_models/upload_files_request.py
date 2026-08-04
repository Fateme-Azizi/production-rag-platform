from pydantic import Base64Bytes, BaseModel

from src.schemas.enums.document_type import DocumentType


class UploadRequestModel(BaseModel):
    file_name: str
    file_size_bytes: int
    file_bytes: Base64Bytes
    type: DocumentType
    s3_bucket: str
    s3_key: str
    title: str | None
