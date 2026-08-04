"""create rag schema: admins, users, documents, vectors, query_logs

Revision ID: 0001_create_rag_schema
Revises:
Create Date: 2026-07-20

"""

from __future__ import annotations

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "0001_create_rag_schema"
down_revision = None
branch_labels = None
depends_on = None

# Must match EMBEDDING_DIM in models.py - see that file's setup notes for
# which local embedding model this corresponds to.
EMBEDDING_DIM = 384


def upgrade() -> None:
    # pgvector must be enabled before any column can use the Vector type.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    bind = op.get_bind()
    admin_type = postgresql.ENUM(
        "super_admin",
        "content_admin",
        "support_admin",
        name="admin_type",
        create_type=False,
    )
    admin_access_type = postgresql.ENUM(
        "read_only",
        "read_write",
        "full_access",
        name="admin_access_type",
        create_type=False,
    )
    membership_type = postgresql.ENUM(
        "free",
        "pro",
        "enterprise",
        name="membership_type",
        create_type=False,
    )
    document_status = postgresql.ENUM(
        "pending",
        "processing",
        "ingested",
        "failed",
        name="document_status",
        create_type=False,
    )

    admin_type.create(bind, checkfirst=True)
    admin_access_type.create(bind, checkfirst=True)
    membership_type.create(bind, checkfirst=True)
    document_status.create(bind, checkfirst=True)

    # ---------------------------------------------------------------- #
    # admins
    # ---------------------------------------------------------------- #
    op.create_table(
        "admins",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", admin_type, nullable=False),
        sa.Column("access_type", admin_access_type, nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("email", sa.String(255), unique=True),
        sa.Column("hashed_password", sa.String(255)),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # ---------------------------------------------------------------- #
    # users
    # ---------------------------------------------------------------- #
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("membership_type", membership_type, nullable=False),
        sa.Column("allowed_total_token", sa.Integer(), nullable=False),
        sa.Column("used_total_token", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("email", sa.String(255), unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("used_total_token >= 0", name="ck_users_used_token_nonneg"),
        sa.CheckConstraint(
            "used_total_token <= allowed_total_token", name="ck_users_token_budget"
        ),
    )

    # ---------------------------------------------------------------- #
    # documents
    # ---------------------------------------------------------------- #
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("type", sa.String(127), nullable=False),
        sa.Column("s3_bucket", sa.String(255), nullable=False),
        sa.Column("s3_key", sa.String(1024), nullable=False),
        sa.Column("file_name", sa.String(512), nullable=False),
        sa.Column("file_size_bytes", sa.Integer()),
        sa.Column("checksum", sa.String(128)),
        sa.Column("status", document_status, nullable=False, server_default="pending"),
        sa.Column("title", sa.String(512)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column(
            "uploaded_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("admins.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("s3_bucket", "s3_key", name="uq_documents_bucket_key"),
    )
    op.create_index("ix_documents_uploaded_by", "documents", ["uploaded_by"])

    # ---------------------------------------------------------------- #
    # vectors
    # ---------------------------------------------------------------- #
    op.create_table(
        "vectors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer()),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=False),
        sa.Column("embedding_model", sa.String(255), nullable=False),
        sa.Column("chunk_metadata", postgresql.JSONB()),
        sa.Column("content_hash", sa.String(64)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "document_id", "chunk_index", name="uq_vectors_document_chunk"
        ),
    )
    op.create_index("ix_vectors_document_id", "vectors", ["document_id"])

    # HNSW ANN index - op.create_index doesn't expose WITH (...) storage
    # params cleanly across dialects, so this one is raw SQL.
    op.execute(
        """
        CREATE INDEX ix_vectors_embedding_hnsw
        ON vectors
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )

    # ---------------------------------------------------------------- #
    # query_logs (optional usage-tracking table)
    # ---------------------------------------------------------------- #
    op.create_table(
        "query_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("tokens_used", sa.Integer(), nullable=False),
        sa.Column(
            "retrieved_chunk_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True))
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_query_logs_user_id", "query_logs", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_query_logs_user_id", table_name="query_logs")
    op.drop_table("query_logs")

    op.execute("DROP INDEX IF EXISTS ix_vectors_embedding_hnsw")
    op.drop_index("ix_vectors_document_id", table_name="vectors")
    op.drop_table("vectors")

    op.drop_index("ix_documents_uploaded_by", table_name="documents")
    op.drop_table("documents")

    op.drop_table("users")
    op.drop_table("admins")

    bind = op.get_bind()
    postgresql.ENUM(name="document_status").drop(bind, checkfirst=True)
    postgresql.ENUM(name="membership_type").drop(bind, checkfirst=True)
    postgresql.ENUM(name="admin_access_type").drop(bind, checkfirst=True)
    postgresql.ENUM(name="admin_type").drop(bind, checkfirst=True)

    # Only drop the extension if nothing else in your database depends on
    # it - commented out by default since that's a shared, global object.
    # op.execute("DROP EXTENSION IF EXISTS vector")
