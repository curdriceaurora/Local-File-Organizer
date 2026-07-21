"""Deterministic fixture corpus for cross-surface conformance (#1605).

Every case materializes an identical byte-for-byte input tree with fixed
modification times, so scans, plans, fingerprints, and image year-folders are
reproducible across runs and supported platforms.  Cases are tagged so adapter
suites can select the divergence-prone scenarios they migrate (#1595-#1598)
and so the transfer (#1602), methodology (#1602), and jobs/recovery (#1604)
slices can extend the corpus without touching existing golden expectations.

Symlink cases are POSIX-only: creating symlinks on Windows requires elevated
privileges, and canonical traversal excludes symlinks everywhere anyway.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

#: 2026-01-01T00:00:00Z — fixed mtime applied to every corpus file unless a
#: spec overrides it (image fallback folders embed the mtime year).
FIXED_MTIME_NS = 1_767_225_600 * 10**9

#: 2020-01-01T00:00:00Z — used by media cases to pin a second image year.
MTIME_2020_NS = 1_577_836_800 * 10**9


@dataclass(frozen=True)
class FileSpec:
    """One regular file in a corpus case, relative to the input root."""

    path: str
    content: bytes
    mtime_ns: int = FIXED_MTIME_NS


@dataclass(frozen=True)
class SymlinkSpec:
    """One symlink in a corpus case (POSIX-only).

    ``target`` is interpreted relative to the symlink's parent directory, so
    ``../outside.txt`` can point outside the input root.
    """

    path: str
    target: str


@dataclass(frozen=True)
class OutputSpec:
    """A file pre-created under the output root before preview/execute."""

    path: str
    content: bytes


@dataclass(frozen=True)
class CorpusCase:
    """A named, deterministic fixture scenario."""

    case_id: str
    description: str
    tags: frozenset[str]
    files: tuple[FileSpec, ...]
    symlinks: tuple[SymlinkSpec, ...] = ()
    preexisting_output: tuple[OutputSpec, ...] = ()

    @property
    def requires_symlinks(self) -> bool:
        """Whether materializing this case creates symlinks (POSIX-only)."""
        return bool(self.symlinks)


def materialize_case(case: CorpusCase, input_root: Path, output_root: Path) -> None:
    """Create the case's input tree (and any pre-existing output entries).

    File mtimes are pinned after every write so fingerprints and year-based
    fallback folders are identical on every run.
    """
    input_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)
    for spec in case.files:
        target = input_root / spec.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(spec.content)
        os.utime(target, ns=(spec.mtime_ns, spec.mtime_ns))
    for link in case.symlinks:
        link_path = input_root / link.path
        link_path.parent.mkdir(parents=True, exist_ok=True)
        link_path.symlink_to(link.target)
    for out in case.preexisting_output:
        target = output_root / out.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(out.content)


CORPUS_CASES: tuple[CorpusCase, ...] = (
    CorpusCase(
        case_id="flat-documents",
        description="Flat directory of text documents; baseline traversal and planning.",
        tags=frozenset({"traversal", "plan", "recovery"}),
        files=(
            FileSpec("alpha.txt", b"alpha body\n"),
            FileSpec("bravo.md", b"# bravo\n"),
            FileSpec("ledger.csv", b"a,b\n1,2\n"),
        ),
    ),
    CorpusCase(
        case_id="nested-mixed",
        description="Nested tree with mixed media; recursion policy must hold end to end.",
        tags=frozenset({"traversal", "media"}),
        files=(
            FileSpec("top.txt", b"top-level\n"),
            FileSpec("docs/report.pdf", b"%PDF-1.4 fixture\n"),
            FileSpec("docs/deep/inner.md", b"inner\n"),
            FileSpec("media/photo.jpg", b"jpg-bytes"),
            FileSpec("media/clip.mp4", b"mp4-bytes"),
            FileSpec("media/song.mp3", b"mp3-bytes"),
            FileSpec("cad/part.dxf", b"dxf-bytes"),
            FileSpec("misc/data.zzz", b"unknown-bytes"),
        ),
    ),
    CorpusCase(
        case_id="hidden-entries",
        description="Dot-prefixed files and directories at several depths.",
        tags=frozenset({"traversal", "hidden"}),
        files=(
            FileSpec("visible.txt", b"visible\n"),
            FileSpec(".hidden.txt", b"hidden\n"),
            FileSpec(".hiddendir/inside.txt", b"inside hidden dir\n"),
            FileSpec("nested/.dotfile.md", b"dot file\n"),
            FileSpec("nested/plain.md", b"plain\n"),
        ),
    ),
    CorpusCase(
        case_id="collision-stems",
        description=(
            "Distinct sources sharing a destination name, plus a pre-existing "
            "destination; exercises skip-existing and rename-with-counter."
        ),
        tags=frozenset({"collision", "plan"}),
        files=(
            FileSpec("archive/summary.txt", b"archived summary\n"),
            FileSpec("reports/summary.txt", b"reported summary\n"),
            FileSpec("notes/draft.txt", b"note draft\n"),
            FileSpec("old/draft.txt", b"old draft\n"),
        ),
        preexisting_output=(OutputSpec("Documents/summary.txt", b"already organized\n"),),
    ),
    CorpusCase(
        case_id="duplicate-content",
        description="Byte-identical files in different directories; content dedup.",
        tags=frozenset({"duplicates"}),
        files=(
            FileSpec("copy/two.txt", b"same bytes\n"),
            FileSpec("one.txt", b"same bytes\n"),
            FileSpec("unique.txt", b"different bytes\n"),
        ),
    ),
    CorpusCase(
        case_id="symlink-entries",
        description="Symlinked file and directory inside the tree; both are excluded.",
        tags=frozenset({"traversal", "symlink"}),
        files=(FileSpec("real.txt", b"real file\n"),),
        symlinks=(
            SymlinkSpec("escape.txt", "../outside.txt"),
            SymlinkSpec("loopdir", "../elsewhere"),
        ),
    ),
    CorpusCase(
        case_id="media-optional",
        description=(
            "Optional media routed through deterministic metadata stubs; image "
            "year folders come from pinned mtimes."
        ),
        tags=frozenset({"media"}),
        files=(
            FileSpec("photo_recent.jpg", b"jpg-recent"),
            FileSpec("photo_older.png", b"png-older", mtime_ns=MTIME_2020_NS),
            FileSpec("song.mp3", b"mp3-song"),
            FileSpec("movie.mkv", b"mkv-movie"),
            FileSpec("clip.mp4", b"mp4-clip"),
            FileSpec("widget.step", b"step-widget"),
            FileSpec("data.zzz", b"unknown"),
        ),
    ),
    CorpusCase(
        case_id="methodology-seed",
        description=(
            "Stable seed tree for methodology semantics; #1602 will extend the "
            "expectations when PARA/Johnny Decimal remapping is canonical."
        ),
        tags=frozenset({"methodology"}),
        files=(
            FileSpec("projects/alpha/plan.txt", b"project plan\n"),
            FileSpec("areas/finance/budget.csv", b"q1,q2\n10,20\n"),
            FileSpec("resources/reading/paper.pdf", b"%PDF-1.4 paper\n"),
            FileSpec("archive/2020/notes.md", b"archived notes\n"),
        ),
    ),
)

_CASES_BY_ID = {case.case_id: case for case in CORPUS_CASES}


def get_case(case_id: str) -> CorpusCase:
    """Return the corpus case registered under *case_id*."""
    try:
        return _CASES_BY_ID[case_id]
    except KeyError as exc:
        known = ", ".join(sorted(_CASES_BY_ID))
        raise KeyError(f"Unknown corpus case {case_id!r}; known cases: {known}") from exc


def cases_tagged(tag: str) -> tuple[CorpusCase, ...]:
    """Return all corpus cases carrying *tag*, in registration order."""
    return tuple(case for case in CORPUS_CASES if tag in case.tags)
