import asyncio
import hashlib
import io
import logging

import torch
from docx import Document as DocxFile
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.s3_adapter import S3DirectAdapter
from src.config import settings
from src.database.repository.admins import AdminRepository
from src.database.repository.documents import DocumentRepository
from src.database.repository.query_logs import QueryLogRepository
from src.database.repository.users import UserRepository
from src.database.repository.vectors import VectorRepository
from src.schemas.dtos.request_models.embed_files_request import EmbedFilesRequestModel
from src.schemas.enums.document_status import DocumentStatus
from src.schemas.enums.document_type import DocumentType

logger = logging.getLogger(__name__)

EXTENSION_MAP: dict[DocumentType, str] = {
    DocumentType.PDF: ".pdf",
    DocumentType.TXT: ".txt",
    DocumentType.DOCS: ".docx",
}

# 384 dims - matches EMBEDDING_DIM in src/database/models/vectors.py.
# Runs locally via sentence-transformers, no API key needed.
EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"

CHUNK_SIZE_CHARS = 1000
CHUNK_OVERLAP_CHARS = 150

_model: SentenceTransformer | None = None


class IngestionService:
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

    async def embed_files(self, file_data: EmbedFilesRequestModel) -> None:
        key = f"{file_data.s3_key}{EXTENSION_MAP[file_data.type]}"
        print(key)

        content = await self.s3_adapter.download_document(key)
        print(f"FILE DOWNLOADED ({len(content)} bytes), READY FOR INGEST")

        text = self._extract_text(content, file_data.type)
        chunks = self._chunk_text(text)

        if not chunks:
            await self.document_repository.update(
                file_data.document_id, {"status": DocumentStatus.FAILED}
            )
            raise ValueError("No extractable text found in document.")

        model = self._get_embedding_model()
        # encode() is a blocking CPU call - run off the event loop.
        embeddings = await asyncio.to_thread(
            model.encode, chunks, normalize_embeddings=True
        )

        total_chunks = len(chunks)
        for index, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            await self.vectore_storage.create(
                {
                    "document_id": file_data.document_id,
                    "chunk_index": index,
                    "content": chunk,
                    "token_count": len(
                        chunk.split()
                    ),  # rough estimate, not exact tokens
                    "embedding": embedding.tolist(),
                    "embedding_model": EMBEDDING_MODEL_NAME,
                    "content_hash": hashlib.sha256(chunk.encode("utf-8")).hexdigest(),
                    "chunk_metadata": {
                        "source_key": file_data.s3_key,
                        "source_bucket": file_data.s3_bucket,
                        "document_type": file_data.type.value,
                        "chunk_index": index,
                        "total_chunks": total_chunks,
                        "char_start": index * (CHUNK_SIZE_CHARS - CHUNK_OVERLAP_CHARS),
                        "char_count": len(chunk),
                    },
                }
            )

        await self.document_repository.update(
            file_data.document_id, {"status": DocumentStatus.INGESTED}
        )
        print(f"INGESTED {len(chunks)} CHUNKS FOR DOCUMENT {file_data.document_id}")

    def _get_embedding_model(self) -> SentenceTransformer:
        """Load the embedding model once per process and reuse it."""
        global _model
        if _model is None:
            device = settings.embedding_device
            if device == "cuda" and not torch.cuda.is_available():
                logger.warning(
                    "EMBEDDING_DEVICE=cuda but torch.cuda.is_available() is "
                    "False (no GPU visible, driver missing, or torch is a "
                    "CPU-only build). Falling back to CPU."
                )
                device = "cpu"
            logger.info(f"Loading embedding model on device={device}")
            _model = SentenceTransformer(EMBEDDING_MODEL_NAME, device=device)
        return _model

    def _extract_text(self, content: bytes, doc_type: DocumentType) -> str:
        """Pull raw text out of the downloaded file bytes."""
        if doc_type is DocumentType.TXT:
            return content.decode("utf-8", errors="ignore")

        if doc_type is DocumentType.PDF:
            reader = PdfReader(io.BytesIO(content))
            return "\n".join(page.extract_text() or "" for page in reader.pages)

        if doc_type is DocumentType.DOCS:
            docx_file = DocxFile(io.BytesIO(content))
            return "\n".join(p.text for p in docx_file.paragraphs)

        raise ValueError(f"No text extractor for document type: {doc_type}")

    def _chunk_text(self, text: str) -> list[str]:
        """Fixed-size character chunks with overlap. Simple on purpose -
        good enough to start; swap for a smarter splitter later if needed."""
        text = text.strip()
        if not text:
            return []

        chunks = []
        start = 0
        while start < len(text):
            end = start + CHUNK_SIZE_CHARS
            chunks.append(text[start:end])
            start = end - CHUNK_OVERLAP_CHARS
        return chunks
