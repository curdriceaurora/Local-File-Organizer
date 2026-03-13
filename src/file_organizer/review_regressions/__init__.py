"""Framework for detector-based review-regression audits."""

from file_organizer.review_regressions.correctness import (
    CORRECTNESS_DETECTORS,
    ActiveModelPrimitiveStoreDetector,
    StageContextValidationBypassDetector,
)
from file_organizer.review_regressions.framework import (
    AuditReport,
    DetectorDescriptor,
    ReviewRegressionDetector,
    Violation,
    fingerprint_ast_node,
    iter_python_files,
    parse_python_ast,
    render_report_json,
    run_audit,
)
from file_organizer.review_regressions.security import (
    SECURITY_DETECTORS,
    GuardedContextDirectPathDetector,
    ValidatedPathBypassDetector,
)

__all__ = [
    "AuditReport",
    "DetectorDescriptor",
    "ReviewRegressionDetector",
    "Violation",
    "ActiveModelPrimitiveStoreDetector",
    "CORRECTNESS_DETECTORS",
    "GuardedContextDirectPathDetector",
    "ValidatedPathBypassDetector",
    "StageContextValidationBypassDetector",
    "SECURITY_DETECTORS",
    "fingerprint_ast_node",
    "iter_python_files",
    "parse_python_ast",
    "render_report_json",
    "run_audit",
]
