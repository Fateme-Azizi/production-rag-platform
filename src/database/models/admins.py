from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.models.base import Base, TimestampMixin, UUIDPk
from src.schemas.enums.access_type import AccessType
from src.schemas.enums.admin_type import AdminType

if TYPE_CHECKING:
    from src.database.models.documents import Document


class Admin(UUIDPk, TimestampMixin, Base):
    __tablename__ = "admins"

    name: Mapped[str] = mapped_column(String(255), nullable=False)

    type: Mapped[AdminType] = mapped_column(
        SAEnum(
            AdminType,
            name="admin_type",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )

    access_type: Mapped[AccessType] = mapped_column(
        SAEnum(
            AccessType,
            name="admin_access_type",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )

    active: Mapped[bool] = mapped_column(default=True, nullable=False)

    email: Mapped[str | None] = mapped_column(
        String(255),
        unique=True,
    )

    hashed_password: Mapped[str | None] = mapped_column(String(255))

    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    documents: Mapped[list["Document"]] = relationship(
        back_populates="uploaded_by_admin",
    )
