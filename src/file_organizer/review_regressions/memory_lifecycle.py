"""Memory-lifecycle detector pack for review-regression audits.

Catches invariants around buffer pool ownership, eager allocation,
absolute RSS usage in feedback loops, and no-op acquire/release cycles.
"""

from __future__ import annotations

import ast
from pathlib import Path

from file_organizer.review_regressions.framework import (
    ReviewRegressionDetector,
    Violation,
    fingerprint_ast_node,
    iter_python_files,
    parse_python_ast,
)

_SOURCE_ROOT = Path("src/file_organizer")

# Function names where buffer-ownership via len() is forbidden
_POOL_FUNCTION_NAMES = {"acquire", "release", "_get_buffer"}

# Class names where buffer-ownership via len() is forbidden
_POOL_CLASS_NAMES = {"BufferPool"}

_BUFFER_NAME_TOKENS = ("buf", "buffer")
_FEEDBACK_METHOD_NAMES = {"adjust_from_feedback"}


def _iter_memory_lifecycle_python_files(root: Path) -> list[Path]:
    source_root = root / _SOURCE_ROOT
    scan_root = source_root if source_root.exists() else root
    return iter_python_files(scan_root)


def _parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    return parents


def _enclosing_function_name(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> str | None:
    """Return the name of the innermost enclosing function, or None if none."""
    current: ast.AST | None = node
    while current is not None:
        current = parents.get(current)
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current.name
    return None


def _enclosing_class_name(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> str | None:
    """Return the name of the innermost enclosing class, or None if none."""
    current: ast.AST | None = node
    while current is not None:
        current = parents.get(current)
        if isinstance(current, ast.ClassDef):
            return current.name
    return None


def _is_len_call_on_name(node: ast.AST) -> str | None:
    """Return the variable name if node is len(<name>), otherwise None."""
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if not (isinstance(func, ast.Name) and func.id == "len"):
        return None
    if len(node.args) != 1 or node.keywords:
        return None
    arg = node.args[0]
    if isinstance(arg, ast.Name):
        return arg.id
    return None


def _is_buffer_pool_call(node: ast.AST) -> bool:
    """Return True if node is BufferPool(...) or something.BufferPool(...)."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name) and func.id == "BufferPool":
        return True
    if isinstance(func, ast.Attribute) and func.attr == "BufferPool":
        return True
    return False


def _is_buffer_like_name(name: str) -> bool:
    """Return True when *name* looks like a buffer variable."""
    lowered = name.lower()
    return any(token in lowered for token in _BUFFER_NAME_TOKENS)


def _has_subtraction_ancestor(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> bool:
    """Return True when node is contained in a subtraction expression."""
    current: ast.AST | None = node
    while current is not None:
        current = parents.get(current)
        if isinstance(current, ast.BinOp) and isinstance(current.op, ast.Sub):
            return True
    return False


def _is_rss_access(node: ast.AST) -> bool:
    """Return True if node is <expr>.memory_info().rss."""
    if not isinstance(node, ast.Attribute):
        return False
    if node.attr != "rss":
        return False
    value = node.value
    if not isinstance(value, ast.Call):
        return False
    func = value.func
    if isinstance(func, ast.Attribute) and func.attr == "memory_info":
        return True
    return False


def _nearest_assignment_ancestor(
    node: ast.AST, parents: dict[ast.AST, ast.AST]
) -> ast.Assign | ast.AnnAssign | None:
    """Return the nearest assignment node containing *node*."""
    current: ast.AST | None = node
    while current is not None:
        current = parents.get(current)
        if isinstance(current, (ast.Assign, ast.AnnAssign)):
            return current
    return None


def _assignment_target_names(node: ast.Assign | ast.AnnAssign) -> set[str]:
    """Return simple assignment target names for Assign/AnnAssign nodes."""
    names: set[str] = set()
    targets = [node.target] if isinstance(node, ast.AnnAssign) else node.targets
    for target in targets:
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, ast.Attribute):
            names.add(target.attr)
    return names


def _is_baseline_assignment(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> bool:
    """Return True if *node* is assigned into a baseline variable."""
    assign = _nearest_assignment_ancestor(node, parents)
    if assign is None:
        return False
    names = _assignment_target_names(assign)
    return any("baseline" in name.lower() for name in names)


def _is_adjust_feedback_argument(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> bool:
    """Return True when *node* is passed to adjust_from_feedback(...)."""
    current: ast.AST | None = node
    while current is not None:
        current = parents.get(current)
        if not isinstance(current, ast.Call):
            continue
        func = current.func
        if isinstance(func, ast.Name) and func.id in _FEEDBACK_METHOD_NAMES:
            return True
        if isinstance(func, ast.Attribute) and func.attr in _FEEDBACK_METHOD_NAMES:
            return True
    return False


class PooledBufferOwnershipViaLengthDetector:
    """Invariant: buffer ownership must be tracked explicitly, not inferred from len()."""

    detector_id = "memory-lifecycle.pooled-buffer-ownership-via-length"
    rule_class = "memory-lifecycle"
    description = (
        "Flags len(buffer) used as an ownership signal inside pool-related functions "
        "or BufferPool classes. Ownership must be tracked explicitly."
    )

    def find_violations(self, root: Path) -> list[Violation]:
        """Return violations where len() is used to infer pool buffer ownership."""
        findings: list[Violation] = []
        for path in _iter_memory_lifecycle_python_files(root):
            tree = parse_python_ast(path)
            parents = _parent_map(tree)
            for node in ast.walk(tree):
                var_name = _is_len_call_on_name(node)
                if var_name is None:
                    continue
                # Check if we are inside a pool-related function or class
                fn_name = _enclosing_function_name(node, parents)
                cls_name = _enclosing_class_name(node, parents)
                in_pool_function = fn_name in _POOL_FUNCTION_NAMES
                in_pool_class = cls_name in _POOL_CLASS_NAMES
                if not (in_pool_function or in_pool_class) or not _is_buffer_like_name(var_name):
                    continue
                findings.append(
                    Violation.from_path(
                        detector_id=self.detector_id,
                        rule_class=self.rule_class,
                        rule_id="pooled-buffer-ownership-via-length",
                        root=root,
                        path=path,
                        line=getattr(node, "lineno", None),
                        message=(
                            f"Do not use len() to infer buffer ownership — "
                            f"track ownership explicitly (found len({var_name}))"
                        ),
                        fingerprint_basis=fingerprint_ast_node(node),
                    )
                )
        return sorted(findings, key=lambda v: v.sort_key())


class EagerBufferPoolAllocationDetector:
    """Invariant: BufferPool() must not be instantiated eagerly inside __init__."""

    detector_id = "memory-lifecycle.eager-buffer-pool-allocation"
    rule_class = "memory-lifecycle"
    description = (
        "Flags BufferPool() instantiated directly inside __init__ methods before "
        "context or configuration is available. Defer instantiation until context "
        "is established."
    )

    def find_violations(self, root: Path) -> list[Violation]:
        """Return __init__ methods that eagerly instantiate BufferPool()."""
        findings: list[Violation] = []
        for path in _iter_memory_lifecycle_python_files(root):
            tree = parse_python_ast(path)
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if node.name != "__init__":
                    continue
                # Walk the body of __init__ looking for BufferPool() calls in assignments
                for stmt in ast.walk(ast.Module(body=node.body, type_ignores=[])):
                    if isinstance(stmt, ast.Assign):
                        if _is_buffer_pool_call(stmt.value):
                            findings.append(
                                Violation.from_path(
                                    detector_id=self.detector_id,
                                    rule_class=self.rule_class,
                                    rule_id="eager-buffer-pool-allocation",
                                    root=root,
                                    path=path,
                                    line=stmt.lineno,
                                    message=(
                                        "BufferPool() should not be instantiated eagerly "
                                        "in __init__ — defer until context is established"
                                    ),
                                    fingerprint_basis=fingerprint_ast_node(stmt),
                                )
                            )
                    elif isinstance(stmt, ast.AnnAssign):
                        if stmt.value is not None and _is_buffer_pool_call(stmt.value):
                            findings.append(
                                Violation.from_path(
                                    detector_id=self.detector_id,
                                    rule_class=self.rule_class,
                                    rule_id="eager-buffer-pool-allocation",
                                    root=root,
                                    path=path,
                                    line=stmt.lineno,
                                    message=(
                                        "BufferPool() should not be instantiated eagerly "
                                        "in __init__ — defer until context is established"
                                    ),
                                    fingerprint_basis=fingerprint_ast_node(stmt),
                                )
                            )
        return sorted(findings, key=lambda v: v.sort_key())


class AbsoluteRSSInBatchFeedbackDetector:
    """Invariant: batch-feedback loops must use per-chunk RSS delta, not absolute RSS."""

    detector_id = "memory-lifecycle.absolute-rss-in-batch-feedback"
    rule_class = "memory-lifecycle"
    description = (
        "Flags process.memory_info().rss used as an absolute value in an assignment "
        "without a subtraction baseline. Batch feedback loops must use "
        "rss - baseline_rss (a delta), not raw absolute RSS."
    )

    def find_violations(self, root: Path) -> list[Violation]:
        """Return RSS accesses that are not subtracted from a baseline."""
        findings: list[Violation] = []
        for path in _iter_memory_lifecycle_python_files(root):
            tree = parse_python_ast(path)
            parents = _parent_map(tree)
            for node in ast.walk(tree):
                if not _is_rss_access(node):
                    continue
                # The RSS access is fine when it appears as an operand of subtraction
                # (either left or right side).
                if _has_subtraction_ancestor(node, parents):
                    continue
                if _is_baseline_assignment(node, parents):
                    continue
                in_assignment = _nearest_assignment_ancestor(node, parents) is not None
                in_feedback_call = _is_adjust_feedback_argument(node, parents)
                if in_assignment or in_feedback_call:
                    findings.append(
                        Violation.from_path(
                            detector_id=self.detector_id,
                            rule_class=self.rule_class,
                            rule_id="absolute-rss-in-batch-feedback",
                            root=root,
                            path=path,
                            line=getattr(node, "lineno", None),
                            message=(
                                "Use per-chunk RSS delta (rss - baseline_rss), "
                                "not absolute RSS, in batch feedback"
                            ),
                            fingerprint_basis=fingerprint_ast_node(node),
                        )
                    )
        return sorted(findings, key=lambda v: v.sort_key())


def _get_name_from_call_result(node: ast.Assign) -> str | None:
    """If node assigns the result of a call to a single Name, return the name."""
    if len(node.targets) != 1:
        return None
    target = node.targets[0]
    if isinstance(target, ast.Name):
        return target.id
    return None


def _consume_pending_by_source(pending: dict[str, ast.Call], stmt: ast.stmt) -> None:
    """Remove pending acquire variables referenced by identifier in *stmt*."""
    identifiers: set[str] = set()
    for node in ast.walk(stmt):
        if isinstance(node, ast.Name):
            identifiers.add(node.id)
        elif isinstance(node, ast.Attribute):
            identifiers.add(node.attr)
    for var in list(pending.keys()):
        if var in identifiers:
            del pending[var]


def _process_release_expr(
    stmt: ast.Expr,
    pending: dict[str, ast.Call],
    pairs: list[tuple[ast.Call, ast.Call]],
) -> None:
    """Handle an expression statement that might be a pool.release() call."""
    call = stmt.value
    if not isinstance(call, ast.Call):
        _consume_pending_by_source(pending, stmt)
        return
    func = call.func
    if not (isinstance(func, ast.Attribute) and func.attr == "release"):
        _consume_pending_by_source(pending, stmt)
        return
    # Check whether any positional arg is a pending acquire variable
    for arg in call.args:
        if isinstance(arg, ast.Name) and arg.id in pending:
            acquire_call = pending.pop(arg.id)
            pairs.append((acquire_call, call))
            return
    # Not a release of a pending variable — treat as a consumer
    _consume_pending_by_source(pending, stmt)


def _find_acquire_release_no_consume(
    body: list[ast.stmt],
) -> list[tuple[ast.Call, ast.Call]]:
    """Find (acquire_call, release_call) pairs with no use of the buffer between them.

    Returns pairs of AST Call nodes for acquire/release that have no intervening
    read, write, yield, or assignment using the acquired buffer variable.
    """
    pairs: list[tuple[ast.Call, ast.Call]] = []
    # variable name → acquire call node
    pending: dict[str, ast.Call] = {}

    for stmt in body:
        if isinstance(stmt, ast.Assign):
            var = _get_name_from_call_result(stmt)
            if var is not None and isinstance(stmt.value, ast.Call):
                func = stmt.value.func
                if isinstance(func, ast.Attribute) and func.attr == "acquire":
                    pending[var] = stmt.value
                    continue
            _consume_pending_by_source(pending, stmt)
        elif isinstance(stmt, ast.Expr):
            _process_release_expr(stmt, pending, pairs)
        else:
            _consume_pending_by_source(pending, stmt)

    return pairs


class LegacyAcquireReleaseWithoutConsumeDetector:
    """Invariant: acquired buffers must be consumed before being released."""

    detector_id = "memory-lifecycle.legacy-acquire-release-without-consume"
    rule_class = "memory-lifecycle"
    description = (
        "Flags pool.acquire(...) followed by pool.release(...) on the same variable "
        "with no intervening usage of the buffer. This is a no-op and typically "
        "indicates a legacy code path."
    )

    def find_violations(self, root: Path) -> list[Violation]:
        """Return acquire→release pairs where the buffer is never consumed."""
        findings: list[Violation] = []
        for path in _iter_memory_lifecycle_python_files(root):
            tree = parse_python_ast(path)
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                pairs = _find_acquire_release_no_consume(node.body)
                for acquire_call, _release_call in pairs:
                    findings.append(
                        Violation.from_path(
                            detector_id=self.detector_id,
                            rule_class=self.rule_class,
                            rule_id="legacy-acquire-release-without-consume",
                            root=root,
                            path=path,
                            line=getattr(acquire_call, "lineno", None),
                            message=(
                                "Buffer acquired and released without being consumed — "
                                "this is a no-op and indicates a legacy code path"
                            ),
                            fingerprint_basis=fingerprint_ast_node(acquire_call),
                        )
                    )
        return sorted(findings, key=lambda v: v.sort_key())


MEMORY_LIFECYCLE_DETECTORS: tuple[ReviewRegressionDetector, ...] = (
    PooledBufferOwnershipViaLengthDetector(),
    EagerBufferPoolAllocationDetector(),
    AbsoluteRSSInBatchFeedbackDetector(),
    LegacyAcquireReleaseWithoutConsumeDetector(),
)
