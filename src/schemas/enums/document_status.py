from enum import Enum


class DocumentStatus(str, Enum):
    """Ingestion pipeline state - a document isn't queryable until INGESTED."""

    PENDING = "pending"
    PROCESSING = "processing"
    INGESTED = "ingested"
    FAILED = "failed"
