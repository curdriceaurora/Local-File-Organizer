"""Template-JS detector pack for legacy review-regression audits."""

from __future__ import annotations

import re
from pathlib import Path

from file_organizer.review_regressions.framework import (
    ReviewRegressionDetector,
    Violation,
)

_TEMPLATE_ROOT = Path("src/file_organizer/web/templates")
_SCRIPT_BLOCK_RE = re.compile(r"(?is)<script\b[^>]*>(?P<body>.*?)</script\s*>")
_INLINE_HANDLER_RE = re.compile(
    r"""(?is)\bon[a-z][\w-]*\s*=\s*(?P<quote>["'])(?P<body>.*?)(?P=quote)"""
)
_JINJA_EXPR_RE = re.compile(r"(?is)\{\{\-?\s*(?P<expr>.*?)\s*\-?\}\}")
_JINJA_INCLUDE_RE = re.compile(r"(?is)\{%\s*include\b")


def _iter_template_files(root: Path) -> list[Path]:
    """Return template files under the web template root."""
    template_root = root / _TEMPLATE_ROOT
    if not template_root.exists():
        return []
    return sorted(
        (path for path in template_root.rglob("*.html") if path.is_file()),
        key=lambda path: path.as_posix(),
    )


def _quote_state(text: str) -> str | None:
    """Return the current quote delimiter if *text* ends inside a JS string literal."""
    quote: str | None = None
    escaped = False
    for char in text:
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if quote is None:
            if char in {'"', "'", "`"}:
                quote = char
            continue
        if char == quote:
            quote = None
    return quote


def _is_safe_tojson(expr: str) -> bool:
    """Return True when the Jinja expression ends with a direct ``|tojson`` filter."""
    normalized = "".join(expr.split())
    return normalized.endswith("|tojson")


def _line_number(source: str, offset: int) -> int:
    """Return the 1-based line number for *offset* in *source*."""
    return source.count("\n", 0, offset) + 1


def _context_violations(
    *,
    root: Path,
    source: str,
    path: Path,
    body: str,
    body_offset: int,
    context_kind: str,
) -> list[Violation]:
    """Return violations for one JS-bearing template context."""
    findings: list[Violation] = []

    include_match = _JINJA_INCLUDE_RE.search(body)
    if include_match is not None:
        findings.append(
            Violation.from_path(
                detector_id=TemplateJavaScriptInterpolationDetector.detector_id,
                rule_class=TemplateJavaScriptInterpolationDetector.rule_class,
                rule_id="unsafe-js-interpolation",
                root=root,
                path=path,
                line=_line_number(source, body_offset + include_match.start()),
                message=(
                    f"Jinja include inside {context_kind} JavaScript can hide unsafe interpolation; "
                    "move the snippet out of the JS context."
                ),
                fingerprint_basis=f"{context_kind}:include:{include_match.group(0)}",
            )
        )

    for match in _JINJA_EXPR_RE.finditer(body):
        expr = match.group("expr").strip()
        if not expr:
            continue
        inside_string = _quote_state(body[: match.start()]) is not None
        if _is_safe_tojson(expr) and not inside_string:
            continue

        findings.append(
            Violation.from_path(
                detector_id=TemplateJavaScriptInterpolationDetector.detector_id,
                rule_class=TemplateJavaScriptInterpolationDetector.rule_class,
                rule_id="unsafe-js-interpolation",
                root=root,
                path=path,
                line=_line_number(source, body_offset + match.start()),
                message=(
                    f"Unsafe Jinja interpolation in {context_kind} JavaScript; use tojson outside "
                    "quotes/backticks or move data into data-* attributes."
                ),
                fingerprint_basis=f"{context_kind}:{expr}",
            )
        )

    return findings


def _script_spans(source: str) -> list[tuple[int, int]]:
    """Return the character spans covered by ``<script>`` blocks."""
    return [match.span() for match in _SCRIPT_BLOCK_RE.finditer(source)]


def _span_within(span: tuple[int, int], containers: list[tuple[int, int]]) -> bool:
    """Return True if *span* is fully contained in any container span."""
    start, end = span
    return any(
        container_start <= start and end <= container_end
        for container_start, container_end in containers
    )


class TemplateJavaScriptInterpolationDetector:
    """Detect unsafe Jinja interpolation in inline JavaScript contexts."""

    detector_id = "template-js.unsafe-inline-interpolation"
    rule_class = "template-js"
    description = (
        "Flags Jinja interpolation inside inline JavaScript contexts unless the value is emitted "
        "via a direct tojson value or moved into inert data-* attributes."
    )

    def find_violations(self, root: Path) -> list[Violation]:
        """Return template-JS findings under the web template source root."""
        violations: list[Violation] = []
        for path in _iter_template_files(root):
            source = path.read_text(encoding="utf-8")
            script_spans = _script_spans(source)
            for match in _SCRIPT_BLOCK_RE.finditer(source):
                violations.extend(
                    _context_violations(
                        root=root,
                        source=source,
                        path=path,
                        body=match.group("body"),
                        body_offset=match.start("body"),
                        context_kind="<script> block",
                    )
                )
            for match in _INLINE_HANDLER_RE.finditer(source):
                if _span_within(match.span(), script_spans):
                    continue
                violations.extend(
                    _context_violations(
                        root=root,
                        source=source,
                        path=path,
                        body=match.group("body"),
                        body_offset=match.start("body"),
                        context_kind="inline handler",
                    )
                )
        return sorted(violations, key=lambda finding: finding.sort_key())


TEMPLATE_JS_DETECTORS: tuple[ReviewRegressionDetector, ...] = (
    TemplateJavaScriptInterpolationDetector(),
)
