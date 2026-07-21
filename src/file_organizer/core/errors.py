"""Transport-neutral errors shared by organization adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from file_organizer._compat import StrEnum


class DomainErrorCode(StrEnum):
    """Stable error identifiers that presentation layers may translate."""

    INVALID_REQUEST = "invalid_request"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    OPTIONAL_FEATURE_UNAVAILABLE = "optional_feature_unavailable"
    PLAN_MISMATCH = "plan_mismatch"
    INVALID_JOB_TRANSITION = "invalid_job_transition"
    STALE_JOB_REVISION = "stale_job_revision"
    EXECUTION_FAILED = "execution_failed"
    RECOVERY_REQUIRED = "recovery_required"
    CANCELLED = "cancelled"


@dataclass
class DomainError(Exception):
    """A stable domain failure independent of HTTP, CLI, or UI semantics."""

    code: DomainErrorCode
    message: str
    retryable: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Initialize the exception message after validating its public fields."""
        if not self.message.strip():
            raise ValueError("Domain error message must not be empty")
        super().__init__(f"{self.code.value}: {self.message}")

    def to_dict(self) -> dict[str, Any]:
        """Return the stable adapter-facing error payload."""
        payload: dict[str, Any] = {
            "code": self.code.value,
            "message": self.message,
            "retryable": self.retryable,
        }
        if self.details:
            payload["details"] = dict(self.details)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DomainError:
        """Restore a domain error from its stable payload."""
        return cls(
            code=DomainErrorCode(data["code"]),
            message=str(data["message"]),
            retryable=bool(data.get("retryable", False)),
            details=dict(data.get("details", {})),
        )


def optional_feature_unavailable(feature: str, message: str) -> DomainError:
    """Build the canonical result for an unavailable optional feature."""
    return DomainError(
        DomainErrorCode.OPTIONAL_FEATURE_UNAVAILABLE,
        message,
        retryable=False,
        details={"feature": feature},
    )
