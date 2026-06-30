#!/usr/bin/env python3
"""CI-rail: Flag subprocess.run() calls without return-code handling (issue #1408).

A ``subprocess.run()`` call site is considered compliant when **at least one**
of the following is true in the immediately enclosing function (or at module
scope):

* ``check=True`` is passed as a keyword argument — Python raises
  ``CalledProcessError`` on non-zero exit automatically.
* The return value is assigned to a name and ``.returncode`` is accessed on
  that same name anywhere in the enclosing block.
* The call line carries a targeted ``# noqa: subprocess-returncode``
  suppression comment.

Scope
-----
Only ``src/file_organizer/`` is scanned.  Developer scripts under
``scripts/`` are excluded (detector overreach boundary — those are not
user-visible success paths).

This rail starts **advisory** (mode = "advisory" in rails.toml) so that any
remaining fire-and-forget call sites can be classified before enforcement.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

try:
    from scripts.ci.guardrails.suppressions import has_targeted_noqa
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from suppressions import has_targeted_noqa

RAIL_ID = "subprocess-returncode"

# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _has_check_true(call_node: ast.Call) -> bool:
    """Return True if the call has ``check=True`` as a keyword argument."""
    for kw in call_node.keywords:
        if kw.arg == "check" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
            return True
    return False


def _assigned_name(call_node: ast.Call, parent: ast.stmt) -> str | None:
    """Return the variable name the call result is assigned to, or None.

    Handles:  ``result = subprocess.run(...)``
    and:      ``result = subprocess.run(...); result.returncode``
    """
    if isinstance(parent, ast.Assign):
        targets = parent.targets
        if len(targets) == 1 and isinstance(targets[0], ast.Name):
            return targets[0].id
    if isinstance(parent, ast.AnnAssign) and isinstance(parent.target, ast.Name):
        return parent.target.id
    return None


def _block_accesses_returncode(block: list[ast.stmt], name: str) -> bool:
    """Return True if any statement in *block* accesses ``<name>.returncode``."""

    class _ReturnCodeChecker(ast.NodeVisitor):
        found = False

        def visit_Attribute(self, node: ast.Attribute) -> None:
            if (
                node.attr == "returncode"
                and isinstance(node.value, ast.Name)
                and node.value.id == name
            ):
                self.found = True
            self.generic_visit(node)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            pass  # Do not traverse into nested function definitions

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            pass  # Do not traverse into nested async function definitions

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            pass  # Do not traverse into nested class definitions

        def visit_Lambda(self, node: ast.Lambda) -> None:
            pass  # Do not traverse into nested lambda expressions

    checker = _ReturnCodeChecker()
    for stmt in block:
        checker.visit(stmt)
        if checker.found:
            return True
    return False


# ---------------------------------------------------------------------------
# Per-file visitor
# ---------------------------------------------------------------------------


def _is_subprocess_run(node: ast.Call) -> bool:
    """Return True if *node* is a ``subprocess.run(...)`` call."""
    func = node.func
    # subprocess.run(...)
    if isinstance(func, ast.Attribute) and func.attr == "run":
        if isinstance(func.value, ast.Name) and func.value.id == "subprocess":
            return True
    # run(...) after ``from subprocess import run``
    if isinstance(func, ast.Name) and func.id == "run":
        # We accept a small false-negative risk here: bare ``run()`` is
        # uncommon and would require import tracking.  Restrict to attribute
        # form only to stay low-noise.
        return False
    return False


class SubprocessReturncodeVisitor(ast.NodeVisitor):
    """Walk a module AST and collect non-compliant subprocess.run() sites.

    Compliance rules (see issue #1408 comment):
    - ``check=True`` with CalledProcessError propagating to the caller: compliant.
    - Assigned result with ``.returncode`` accessed in the **same enclosing block**
      (including a try body): compliant.
    - ``# noqa: subprocess-returncode`` on the call line: accepted exception.
    - Discarded result (no assignment): always flagged unless noqa is present.
    - Result assigned but ``.returncode`` never inspected: flagged.
    - Compound statements (try/if/for/while/with) are recursed into as
      independent blocks, so a ``returncode`` check in a sibling branch does
      NOT satisfy the requirement.
    """

    def __init__(self, filepath: Path, lines: list[str]) -> None:
        self.filepath = filepath
        self.lines = lines
        self.violations: list[tuple[int, str, str]] = []

    # ------------------------------------------------------------------
    # Core block checker
    # ------------------------------------------------------------------

    def _check_block(self, block: list[ast.stmt]) -> None:
        """Check every statement in *block* for unchecked subprocess.run()."""
        for idx, stmt in enumerate(block):
            # Look for an Expr node (call result discarded) or an Assign/AnnAssign
            call_node: ast.Call | None = None
            assigned_name: str | None = None

            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                call_node = stmt.value
            elif isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call):
                call_node = stmt.value
                assigned_name = _assigned_name(call_node, stmt)
            elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.value, ast.Call):
                call_node = stmt.value
                assigned_name = _assigned_name(call_node, stmt)

            if call_node is not None and _is_subprocess_run(call_node):
                # 1. check=True → compliant
                if _has_check_true(call_node):
                    pass  # compliant

                # 2. .returncode accessed on the assigned variable within this
                #    block after the call statement → compliant.
                elif assigned_name and _block_accesses_returncode(block[idx + 1 :], assigned_name):
                    pass  # compliant

                else:
                    # 3. Targeted noqa suppression on the call line → compliant
                    lineno = call_node.lineno
                    line_idx = lineno - 1
                    if 0 <= line_idx < len(self.lines):
                        line_content = self.lines[line_idx]
                        if not has_targeted_noqa(line_content, RAIL_ID):
                            self.violations.append(
                                (
                                    lineno,
                                    "subprocess.run() without returncode check or check=True",
                                    line_content.strip(),
                                )
                            )
                    else:
                        self.violations.append(
                            (
                                call_node.lineno,
                                "subprocess.run() without returncode check or check=True",
                                "",
                            )
                        )

            # Recurse into nested scopes.
            self._check_compound(stmt)

    def _check_try_like(
        self,
        stmt: ast.Try,
    ) -> None:  # pragma: no branch
        """Recurse into every sub-block of a try/except/else/finally node."""
        self._check_block(stmt.body)
        for handler in stmt.handlers:
            self._check_block(handler.body)
        if stmt.orelse:
            self._check_block(stmt.orelse)
        if stmt.finalbody:
            self._check_block(stmt.finalbody)

    def _check_compound(self, stmt: ast.stmt) -> None:
        """Recurse into compound statement sub-blocks.

        Each sub-block is treated as an independent scope: a ``returncode``
        check in one branch does NOT satisfy the requirement for a call in a
        sibling branch.

        Function/class definitions create a new named scope and are dispatched
        via ``self.visit()`` so the normal ``visit_FunctionDef`` / ``visit_ClassDef``
        entry-points fire.  All other compound statements are handled inline by
        iterating their body/handler/orelse/finalbody lists.
        """
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            # Named scope — dispatch to the typed visitor so the correct
            # entry-point fires (avoids double-processing).
            self.visit(stmt)
        elif isinstance(stmt, (ast.Try, ast.TryStar)):
            self._check_try_like(stmt)  # type: ignore[arg-type]
        elif isinstance(stmt, ast.If):
            self._check_block(stmt.body)
            if stmt.orelse:
                self._check_block(stmt.orelse)
        elif isinstance(stmt, (ast.For, ast.AsyncFor, ast.While)):
            self._check_block(stmt.body)
            if stmt.orelse:
                self._check_block(stmt.orelse)
        elif isinstance(stmt, (ast.With, ast.AsyncWith)):
            self._check_block(stmt.body)
        elif hasattr(ast, "Match") and isinstance(stmt, ast.Match):
            for case in stmt.cases:
                self._check_block(case.body)

    # ------------------------------------------------------------------
    # Entry points for different AST scopes
    # ------------------------------------------------------------------

    def visit_Module(self, node: ast.Module) -> None:
        self._check_block(node.body)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_block(node.body)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        # A class body may contain method defs; check it as a block so that
        # nested method-level subprocess.run() calls are processed correctly.
        self._check_block(node.body)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_file(filepath: Path) -> list[tuple[int, str, str]]:
    """Parse and check a single Python file.

    Returns a list of ``(lineno, message, line_content)`` tuples.
    """
    try:
        content = filepath.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Error reading {filepath}: {exc}", file=sys.stderr)
        return []

    lines = content.splitlines()
    try:
        tree = ast.parse(content, filename=str(filepath))
    except SyntaxError as exc:
        print(f"Syntax error in {filepath}: {exc}", file=sys.stderr)
        return []

    visitor = SubprocessReturncodeVisitor(filepath, lines)
    visitor.visit(tree)
    return visitor.violations


def main() -> int:
    """Scan all source files under src/file_organizer/."""
    package_root = Path("src/file_organizer")
    if not package_root.exists():
        print(
            "Error: src/file_organizer directory not found. Run from the repository root.",
            file=sys.stderr,
        )
        return 1

    all_violations: list[tuple[str, int, str, str]] = []
    for path in sorted(package_root.rglob("*.py")):
        violations = check_file(path)
        rel_path = path.as_posix()
        for lineno, msg, line in violations:
            all_violations.append((rel_path, lineno, msg, line))

    if all_violations:
        print(
            f"❌ [{RAIL_ID}] Violations found (subprocess.run() without return-code handling):",
            file=sys.stderr,
        )
        for file_path, lineno, msg, line in all_violations:
            print(f"  {file_path}:{lineno}: {msg} -> `{line}`", file=sys.stderr)
        print(
            f"\nFix: add check=True, inspect .returncode, or add '# noqa: {RAIL_ID}' if exempt.",
            file=sys.stderr,
        )
        return 1

    print(f"✅ [{RAIL_ID}] No violations found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
