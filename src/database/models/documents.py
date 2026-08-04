from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.models.base import Base, TimestampMixin, UUIDPk
from src.schemas.enums.document_status import DocumentStatus

if TYPE_CHECKING:
    from src.database.models.admins import Admin
    from src.database.models.vectors import VectorEmbedding


class Document(UUIDPk, TimestampMixin, Base):
    __tablename__ = "documents"

    type: Mapped[str] = mapped_column(String(127), nullable=False)

    s3_bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    s3_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)
    checksum: Mapped[str | None] = mapped_column(String(128))

    status: Mapped[DocumentStatus] = mapped_column(
        SAEnum(
            DocumentStatus,
            name="document_status",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        default=DocumentStatus.PENDING,
        nullable=False,
    )

    title: Mapped[str | None] = mapped_column(String(512))

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("admins.id"),
        nullable=False,
    )

    uploaded_by_admin: Mapped["Admin"] = relationship(
        back_populates="documents",
    )

    vectors: Mapped[list["VectorEmbedding"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "s3_bucket",
            "s3_key",
            name="uq_documents_bucket_key",
        ),
    )
