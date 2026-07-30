from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class ErrorMap(BaseModel):
    """
    Translate an upstream (status, message) to a downstream (to_status, to_message).
    If `message` is None, it's a generic rule for that status.
    If `message` has text, it's treated as a case-insensitive substring match.
    """

    status: int
    message: Optional[str] = Field(
        default=None,
        description="Substring to match inside upstream 'error' (case-insensitive). None = match any.",
    )
    to_status: int
    to_message: str


class ErrorMapper:
    """
    Holds a self-contained list of rules and can attempt a translation.
    This class does NOT log duplicates and does not know about 'global vs local';
    the caller (BaseAdapter) decides the order (local first, then global).
    """

    def __init__(self, overrides: Optional[List[ErrorMap]] = None):
        self.overrides: List[ErrorMap] = []
        if overrides:
            for rule in overrides:
                self.add_rule(rule)

    def add_rule(self, rule: ErrorMap) -> None:
        self.overrides.append(rule)
        # Specific (message != None) first; then by status for stability
        self.overrides.sort(key=lambda r: (r.message is None, r.status))

    def try_translate(
        self, status: int, message: Optional[str]
    ) -> Optional[tuple[int, str]]:
        """
        Returns (to_status, to_message) if a rule matches; otherwise None.
        """
        msg = (message or "").lower()
        for rule in self.overrides:
            if rule.status != status:
                continue
            if rule.message:
                if rule.message.lower() in msg:
                    return rule.to_status, rule.to_message
            else:
                # generic rule for this status
                return rule.to_status, rule.to_message
        return None


# ----------------------------------------------------------------------
# Global fallback rules — used only if no local rule matched
# ----------------------------------------------------------------------
GLOBAL_ERROR_OVERRIDES: List[ErrorMap] = [
    ErrorMap(status=400, to_status=400, to_message="Invalid request"),
    ErrorMap(status=401, to_status=401, to_message="Authentication failed"),
    ErrorMap(status=403, to_status=403, to_message="Access denied"),
    ErrorMap(status=500, to_status=503, to_message="Service temporarily unavailable"),
]

# A reusable mapper instance for globals. BaseAdapter uses this only as fallback.
error_mapper = ErrorMapper(overrides=GLOBAL_ERROR_OVERRIDES)
