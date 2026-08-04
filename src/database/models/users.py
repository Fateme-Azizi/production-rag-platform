from __future__ import annotations

from sqlalchemy import CheckConstraint, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from src.database.models.base import Base, TimestampMixin, UUIDPk
from src.schemas.enums.membership_type import MembershipType


class User(UUIDPk, TimestampMixin, Base):
    __tablename__ = "users"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    membership_type: Mapped[MembershipType] = mapped_column(
        SAEnum(
            MembershipType,
            name="membership_type",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )
    allowed_total_token: Mapped[int] = mapped_column(Integer, nullable=True)

    used_total_token: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active: Mapped[bool] = mapped_column(default=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), unique=True)

    __table_args__ = (
        CheckConstraint("used_total_token >= 0", name="ck_users_used_token_nonneg"),
        CheckConstraint(
            "used_total_token <= allowed_total_token", name="ck_users_token_budget"
        ),
    )
