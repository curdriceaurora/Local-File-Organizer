#!/usr/bin/env python3
"""CI rail: keep raw filesystem traversal behind an executable scope note.

Issue #1736 found that prose describing ``safe_walk`` coverage had drifted
from the source.  This rail recognizes the raw traversal APIs used by the
package, rejects new call sites, and verifies that every retained call still
matches one reviewed exemption with a reason.

The distinction between ``ast.walk`` and filesystem traversal is deliberate:
review-regression detectors walk syntax trees heavily, but that must not hide
the real ``os.walk`` and ``Path.rglob`` calls in the same package.
"""

from __future__ import annotations

import ast
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

RAIL_NAME = "raw-filesystem-traversal"
PACKAGE_ROOT = Path("src/file_organizer")
_PRIMITIVE_PATH = "core/path_guard.py"

TraversalKey = tuple[str, str, str]


@dataclass(frozen=True)
class TraversalSite:
    """One raw traversal call found in package source."""

    path: str
    function: str
    api: str
    line: int

    @property
    def key(self) -> TraversalKey:
        """Return the stable allowlist key for this call."""
        return (self.path, self.function, self.api)


@dataclass(frozen=True)
class TraversalExemption:
    """Reviewed reason and exact call count for an allowed raw traversal."""

    count: int
    reason: str


# The executable safe_walk scope note.  Counts make duplicate calls visible:
# deleting one or adding another both fail until this reviewed inventory is
# deliberately updated.  Keep reasons specific to the contract safe_walk
# cannot or need not provide.
_EXEMPTIONS: dict[TraversalKey, TraversalExemption] = {
    (
        "cli/completion.py",
        "complete_directory",
        "Path.iterdir",
    ): TraversalExemption(
        count=1,
        reason="single-level shell completion must expose symlinked directory candidates",
    ),
    (
        "cli/completion.py",
        "complete_file",
        "Path.iterdir",
    ): TraversalExemption(
        count=1,
        reason="single-level shell completion must expose symlinked file candidates",
    ),
    (
        "config/path_migration.py",
        "resolve_legacy_path",
        "Path.iterdir",
    ): TraversalExemption(
        count=2,
        reason="one-time emptiness checks over app-owned current and legacy XDG directories",
    ),
    (
        "methodologies/para/migration_manager.py",
        "PARAMigrationManager.analyze_source",
        "Path.glob",
    ): TraversalExemption(
        count=1,
        reason="internal migration inventory preserves caller-selected glob semantics",
    ),
    (
        "methodologies/para/migration_manager.py",
        "PARAMigrationManager.list_backups",
        "Path.iterdir",
    ): TraversalExemption(
        count=1,
        reason="single-level listing of the app-owned migration backup directory",
    ),
    (
        "parallel/persistence.py",
        "JobPersistence.list_jobs",
        "Path.glob",
    ): TraversalExemption(
        count=1,
        reason="single-level listing of app-owned job-queue JSON state",
    ),
    (
        "plugins/config.py",
        "PluginConfigManager.list_configured_plugins",
        "Path.glob",
    ): TraversalExemption(
        count=1,
        reason="single-level listing of app-owned plugin configuration JSON files",
    ),
    (
        "review_regressions/framework.py",
        "iter_python_files",
        "os.walk",
    ): TraversalExemption(
        count=1,
        reason="repository audit must prune excluded directories before descending",
    ),
    (
        "review_regressions/template_js.py",
        "_iter_template_files",
        "Path.rglob",
    ): TraversalExemption(
        count=1,
        reason="static audit reads only the repository-owned web template tree",
    ),
    (
        "services/analytics/storage_analyzer.py",
        "StorageAnalyzer._walk_directory",
        "Path.iterdir",
    ): TraversalExemption(
        count=1,
        reason="recursive analyzer requires a caller-selected maximum depth",
    ),
    (
        "services/copilot/rules/rule_manager.py",
        "RuleManager.list_rule_sets",
        "Path.glob",
    ): TraversalExemption(
        count=1,
        reason="single-level listing of app-shipped rule YAML files",
    ),
    (
        "services/intelligence/profile_manager.py",
        "ProfileManager.list_profiles",
        "Path.glob",
    ): TraversalExemption(
        count=1,
        reason="single-level listing of the app-owned profile directory",
    ),
    (
        "services/intelligence/profile_manager.py",
        "ProfileManager.get_profile_count",
        "Path.glob",
    ): TraversalExemption(
        count=1,
        reason="single-level count of the app-owned profile directory",
    ),
    (
        "services/intelligence/profile_migrator.py",
        "ProfileMigrator.list_backups",
        "Path.glob",
    ): TraversalExemption(
        count=1,
        reason="single-level listing of app-owned profile backups",
    ),
    (
        "services/misplacement_detector.py",
        "MisplacementDetector._list_directory_files",
        "Path.iterdir",
    ): TraversalExemption(
        count=1,
        reason="single-level cache funnel deliberately lists one directory once",
    ),
    (
        "tui/file_preview.py",
        "FilePreviewPanel._preview_directory",
        "Path.iterdir",
    ): TraversalExemption(
        count=2,
        reason="bounded single-level UI preview preserves hidden and symlink visibility",
    ),
    (
        "undo/trash_gc.py",
        "TrashGC._recover_orphans",
        "Path.iterdir",
    ): TraversalExemption(
        count=1,
        reason="single-level recovery scan of the app-owned trash directory",
    ),
    (
        "undo/validator.py",
        "OperationValidator._get_trash_path",
        "Path.rglob",
    ): TraversalExemption(
        count=1,
        reason="recovery lookup is confined to the app-owned trash directory",
    ),
    (
        "utils/safedir.py",
        "SafeDir.scandir",
        "os.scandir",
    ): TraversalExemption(
        count=1,
        reason="fd-anchored secure enumeration primitive underlying SafeDir",
    ),
}

_PATH_METHODS = frozenset({"glob", "iterdir", "rglob"})
_OS_APIS = frozenset({"os.fwalk", "os.listdir", "os.scandir", "os.walk"})
_GLOB_APIS = frozenset({"glob.glob", "glob.iglob"})


def _dotted_name(node: ast.AST) -> str | None:
    """Return a dotted name for a simple Name/Attribute expression."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        if prefix is not None:
            return f"{prefix}.{node.attr}"
    return None


def _import_aliases(tree: ast.AST) -> dict[str, str]:
    """Map import-local names to their qualified module/API names."""
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".", 1)[0]
                aliases[local] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                if alias.name == "*":
                    continue
                aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return aliases


def _resolve_alias(name: str, aliases: dict[str, str]) -> str:
    """Resolve the first component of *name* through imports."""
    first, dot, rest = name.partition(".")
    resolved = aliases.get(first, first)
    return f"{resolved}.{rest}" if dot else resolved


def _filesystem_api(node: ast.Call, aliases: dict[str, str]) -> str | None:
    """Return a normalized raw traversal API, excluding syntax-tree walks."""
    name = _dotted_name(node.func)
    if name is None:
        return None
    resolved = _resolve_alias(name, aliases)
    if resolved == "ast.walk":
        return None
    if resolved in _OS_APIS or resolved in _GLOB_APIS:
        return resolved

    # pathlib traversal is normally called on a variable, so the receiver's
    # type is not statically named.  Attribute shape is the reliable signal.
    if isinstance(node.func, ast.Attribute) and node.func.attr in _PATH_METHODS:
        return f"Path.{node.func.attr}"

    # Path.walk() is available on newer supported Python versions.  Treat any
    # non-ast attribute walk as review-required; a custom walk can be exempted
    # with an exact function-level reason if one is ever introduced.
    if isinstance(node.func, ast.Attribute) and node.func.attr == "walk":
        return "Path.walk"
    return None


class _TraversalVisitor(ast.NodeVisitor):
    """Collect raw traversal calls with their enclosing qualified function."""

    def __init__(self, path: str, aliases: dict[str, str]) -> None:
        self.path = path
        self.aliases = aliases
        self.scope: list[str] = []
        self.sites: list[TraversalSite] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_Call(self, node: ast.Call) -> None:
        api = _filesystem_api(node, self.aliases)
        if api is not None:
            self.sites.append(
                TraversalSite(
                    path=self.path,
                    function=".".join(self.scope) or "<module>",
                    api=api,
                    line=node.lineno,
                )
            )
        self.generic_visit(node)


def find_traversals(source: str, *, path: str) -> list[TraversalSite]:
    """Parse *source* and return its raw filesystem traversal sites."""
    tree = ast.parse(source, filename=path)
    visitor = _TraversalVisitor(path, _import_aliases(tree))
    visitor.visit(tree)
    return sorted(visitor.sites, key=lambda site: (site.path, site.line, site.api))


def audit_sites(
    sites: list[TraversalSite],
    exemptions: dict[TraversalKey, TraversalExemption],
) -> tuple[list[TraversalSite], list[tuple[TraversalKey, int, int]]]:
    """Return unexpected sites and stale/mismatched exemption counts."""
    counts = Counter(site.key for site in sites)
    unexpected = [site for site in sites if site.key not in exemptions]
    stale = [
        (key, exemption.count, counts.get(key, 0))
        for key, exemption in exemptions.items()
        if counts.get(key, 0) != exemption.count
    ]
    return unexpected, sorted(stale)


def scan_package(package_root: Path = PACKAGE_ROOT) -> list[TraversalSite]:
    """Return every non-primitive raw traversal under *package_root*."""
    sites: list[TraversalSite] = []
    for file_path in sorted(package_root.rglob("*.py")):
        relative = file_path.relative_to(package_root).as_posix()
        if relative == _PRIMITIVE_PATH:
            continue
        source = file_path.read_text(encoding="utf-8")
        sites.extend(find_traversals(source, path=relative))
    return sorted(sites, key=lambda site: (site.path, site.line, site.api))


def main() -> int:
    """Audit package traversal sites against the executable scope note."""
    if not PACKAGE_ROOT.exists():
        print(f"[{RAIL_NAME}] {PACKAGE_ROOT} not found; run from repository root.", file=sys.stderr)
        return 1

    try:
        sites = scan_package()
    except (OSError, SyntaxError) as exc:
        print(f"[{RAIL_NAME}] could not scan package: {exc}", file=sys.stderr)
        return 1

    unexpected, stale = audit_sites(sites, _EXEMPTIONS)
    if unexpected or stale:
        print(f"[{RAIL_NAME}] traversal scope drift found:", file=sys.stderr)
        for site in unexpected:
            print(
                f"  {site.path}:{site.line}: {site.function} calls {site.api} without an exemption",
                file=sys.stderr,
            )
        for key, expected, actual in stale:
            path, function, api = key
            reason = _EXEMPTIONS[key].reason
            print(
                f"  stale exemption {path}:{function}:{api}: expected {expected}, found {actual} ({reason})",
                file=sys.stderr,
            )
        print(
            "Fix: migrate user-root traversal to core.path_guard.safe_walk, or add/update "
            "one exact _EXEMPTIONS entry with a reviewed reason.",
            file=sys.stderr,
        )
        return 1

    print(
        f"[{RAIL_NAME}] {len(sites)} reviewed raw call(s); "
        f"{len(_EXEMPTIONS)} exact exemption key(s)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
