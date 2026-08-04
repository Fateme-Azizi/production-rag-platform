from enum import Enum


class AccessType(str, Enum):
    READ_ONLY = "read_only"
    READ_WRITE = "read_write"
    FULL_ACCESS = "full_access"
