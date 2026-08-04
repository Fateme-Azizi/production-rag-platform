from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.models.base import Base, TimestampMixin, UUIDPk

if TYPE_CHECKING:
    from src.database.models.documents import Document

# ---------------------------------------------------------------------- #
# Embedding dimension - must match whatever model actually produces the
# vectors. Recommended free/local option for English text:
#
#   BAAI/bge-small-en-v1.5            -> 384 dims  (fast, strong for size)
#   BAAI/bge-base-en-v1.5             -> 768 dims  (better quality, slower)
#   sentence-transformers/all-MiniLM-L6-v2 -> 384 dims (older, still solid)
#   nomic-ai/nomic-embed-text-v1.5    -> 768 dims  (long-context chunks)
#
# Both run locally via `sentence-transformers`, no API key needed.
# ---------------------------------------------------------------------- #
EMBEDDING_DIM = 384


class VectorEmbedding(UUIDPk, TimestampMixin, Base):
    """One row per text chunk + its embedding. Requires the pgvector
    extension: `CREATE EXTENSION IF NOT EXISTS vector;`
    """

    __tablename__ = "vectors"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document: Mapped["Document"] = relationship(back_populates="vectors")

    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer)

    embedding: Mapped[list[float]] = mapped_column(
        Vector(EMBEDDING_DIM), nullable=False
    )

    embedding_model: Mapped[str] = mapped_column(String(255), nullable=False)
    chunk_metadata: Mapped[dict | None] = mapped_column(JSONB)
    content_hash: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (
        UniqueConstraint(
            "document_id", "chunk_index", name="uq_vectors_document_chunk"
        ),
        # Approximate-nearest-neighbor index - required for fast similarity
        # search once you have more than a few thousand rows. HNSW is the
        # generally-preferred pgvector index type (better recall/speed
        # tradeoff than IVFFlat, no "train on existing data" step).
        Index(
            "ix_vectors_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
