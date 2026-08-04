from enum import Enum


class AdminType(str, Enum):
    SUPER_ADMIN = "super_admin"
    CONTENT_ADMIN = "content_admin"
    SUPPORT_ADMIN = "support_admin"
