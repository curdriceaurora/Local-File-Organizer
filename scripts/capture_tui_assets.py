# pyre-ignore-all-errors
"""Capture real TUI screenshots and the demo GIF for the docs.

Drives the actual Textual application headlessly (via ``App.run_test``)
against a staged demo home directory, exporting genuine SVG screenshots
of each view plus an animated GIF walkthrough. Also captures the real
``fo dedupe --dry-run`` CLI output as an SVG.

The demo home is populated with real files (Pillow-generated images,
synthesized WAV audio, markdown/CSV/code documents, duplicate copies)
and real operation history: files are actually moved on disk and the
moves are logged through ``OperationHistory``, exactly as the organizer
records them.

Usage::

    uv run python scripts/capture_tui_assets.py --home ~/fo-demo-home --out docs/assets

The --home directory is wiped and re-staged on every run, and its path
appears verbatim in the captured screenshots — pick a short, tidy one.

Requirements beyond the project dependencies: ``playwright`` (with a
Chromium binary available) for rendering GIF frames.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import math
import os
import shutil
import struct
import sys
import tempfile
import wave
import zipfile
from pathlib import Path

# Terminal geometry for every capture. Wide enough for split panes,
# short enough that GIF frames stay readable at docs width.
TERM_SIZE = (120, 36)
# 880px and 96 colors keep the walkthrough GIF under the repo's 500 KB
# large-file pre-commit limit while staying readable in the docs.
GIF_WIDTH = 880
GIF_COLORS = 96


# ---------------------------------------------------------------------------
# Demo workspace
# ---------------------------------------------------------------------------


def _make_image(path: Path, size: tuple[int, int], base: tuple[int, int, int]) -> None:
    """Write a real JPEG/PNG/PDF with a simple generated scene."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", size)
    px = img.load()
    w, h = size
    for y in range(h):
        t = y / h
        row = (
            int(base[0] * (1 - t) + 30 * t),
            int(base[1] * (1 - t) + 40 * t),
            int(base[2] * (1 - t) + 70 * t),
        )
        for x in range(w):
            px[x, y] = row
    draw = ImageDraw.Draw(img)
    for i in range(6):
        cx, cy = (w * (i * 37 % 100)) // 100, (h * (i * 53 % 100)) // 100
        r = 20 + 15 * i
        draw.ellipse(
            (cx - r, cy - r, cx + r, cy + r),
            outline=(255, 255, 255),
            width=3,
        )
    img.save(path, quality=88)


def _make_wav(
    path: Path,
    seconds: float,
    freqs: tuple[float, ...],
    tags: dict[str, str] | None = None,
) -> None:
    """Synthesize a real 44.1 kHz 16-bit mono WAV of the given length."""
    rate = 44100
    n = int(rate * seconds)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        samples = bytearray()
        for i in range(n):
            t = i / rate
            envelope = min(1.0, t * 8, (seconds - t) * 8)
            value = sum(math.sin(2 * math.pi * f * t) for f in freqs) / len(freqs)
            samples += struct.pack("<h", int(value * envelope * 20000))
        wav.writeframes(bytes(samples))
    if tags:
        try:
            from mutagen.wave import WAVE

            audio = WAVE(str(path))
            audio.add_tags()
            from mutagen.id3 import TALB, TCON, TDRC, TIT2, TPE1

            audio.tags.add(TIT2(encoding=3, text=tags.get("title", "")))
            audio.tags.add(TPE1(encoding=3, text=tags.get("artist", "")))
            audio.tags.add(TALB(encoding=3, text=tags.get("album", "")))
            audio.tags.add(TCON(encoding=3, text=tags.get("genre", "")))
            audio.tags.add(TDRC(encoding=3, text=tags.get("year", "")))
            audio.save()
        except Exception as exc:
            # Broad catch is deliberate: tags are nice-to-have (mutagen may
            # be absent), and the WAV itself is already valid — but say so
            # instead of hiding tagging regressions.
            print(f"warning: could not tag {path.name}: {exc}", file=sys.stderr)


def build_workspace(home: Path) -> Path:
    """Create the demo home directory tree and return the Downloads dir."""
    downloads = home / "Downloads"
    for sub in (
        downloads,
        home / "Documents" / "Finance",
        home / "Documents" / "Reports",
        home / "Pictures" / "2024",
        home / "Music" / "Recordings",
    ):
        sub.mkdir(parents=True, exist_ok=True)

    (downloads / "quarterly-report-Q4.md").write_text(
        "# Quarterly Report — Q4 2025\n\n"
        "## Highlights\n\n"
        "- Revenue up 14% quarter over quarter\n"
        "- Storage costs reduced by 22% after deduplication\n"
        "- 4,812 files organized automatically\n\n"
        "## Summary\n\n"
        "The automated organization pipeline handled Downloads, Documents\n"
        "and Pictures with zero manual intervention. Duplicate detection\n"
        "recovered 3.4 GB across 61 duplicate groups.\n",
        encoding="utf-8",
    )
    (downloads / "notes.txt").write_text(
        "TODO:\n- sort tax receipts into Documents/Finance\n"
        "- archive 2024 photos\n- delete duplicate downloads\n",
        encoding="utf-8",
    )
    (downloads / "budget-2026.csv").write_text(
        "category,jan,feb,mar\nrent,1450,1450,1450\ngroceries,410,385,442\n"
        "utilities,120,118,131\ntravel,0,260,90\n",
        encoding="utf-8",
    )
    (downloads / "cleanup_script.py").write_text(
        '"""Move stale downloads into an archive folder."""\n\n'
        "from pathlib import Path\n\n"
        "STALE_DAYS = 30\n\n\n"
        "def find_stale(root: Path) -> list[Path]:\n"
        "    return [p for p in root.iterdir() if p.is_file()]\n",
        encoding="utf-8",
    )

    _make_image(downloads / "vacation-beach-001.jpg", (1600, 1067), (222, 170, 90))
    _make_image(downloads / "vacation-beach-002.jpg", (1600, 1067), (90, 160, 220))
    _make_image(downloads / "screenshot-2026-01-12.png", (1280, 800), (60, 60, 70))
    _make_image(downloads / "IMG_2047.jpg", (1200, 900), (140, 190, 120))
    shutil.copy2(downloads / "IMG_2047.jpg", downloads / "IMG_2047 (copy).jpg")

    _make_image(downloads / "project-proposal.pdf", (1240, 1754), (240, 240, 245))
    shutil.copy2(
        downloads / "project-proposal.pdf",
        downloads / "project-proposal (1).pdf",
    )
    _make_image(downloads / "invoice-2026-0114.pdf", (1240, 1754), (250, 245, 230))

    _make_wav(
        downloads / "voice-memo-jan-15.wav",
        9.0,
        (220.0, 330.0),
        tags={
            "title": "Voice Memo Jan 15",
            "artist": "Field Recorder",
            "album": "Voice Memos",
            "genre": "Speech",
            "year": "2026",
        },
    )
    _make_wav(
        downloads / "podcast-episode-12.wav",
        14.0,
        (196.0, 294.0, 392.0),
        tags={
            "title": "Episode 12 — Tidy Files",
            "artist": "The Organizer Podcast",
            "album": "Season 2",
            "genre": "Podcast",
            "year": "2026",
        },
    )
    _make_wav(
        downloads / "guitar-riff-demo.wav",
        6.5,
        (82.4, 164.8, 246.9),
        tags={
            "title": "Riff Demo in E",
            "artist": "Home Studio",
            "album": "Sketches",
            "genre": "Rock",
            "year": "2026",
        },
    )
    shutil.copy2(
        downloads / "guitar-riff-demo.wav",
        downloads / "guitar-riff-demo (1).wav",
    )

    with zipfile.ZipFile(downloads / "photos-backup.zip", "w") as zf:
        zf.write(downloads / "vacation-beach-001.jpg", "vacation-beach-001.jpg")
        zf.write(downloads / "screenshot-2026-01-12.png", "screenshot-2026-01-12.png")

    return downloads


def seed_history(home: Path, downloads: Path) -> None:
    """Perform real file moves and log them through OperationHistory."""
    from file_organizer.history.models import OperationType
    from file_organizer.history.tracker import OperationHistory

    moves = [
        ("bank-statement-2026-02.pdf", home / "Documents" / "Finance"),
        ("receipts-january.csv", home / "Documents" / "Finance"),
        ("2025-annual-report.md", home / "Documents" / "Reports"),
        ("holiday-party-041.jpg", home / "Pictures" / "2024"),
        ("conference-talk.wav", home / "Music" / "Recordings"),
    ]
    # Create the files in Downloads first so each move is real.
    for name, _dest in moves:
        src = downloads / name
        if name.endswith((".jpg", ".png")):
            _make_image(src, (800, 600), (170, 120, 200))
        elif name.endswith(".wav"):
            _make_wav(src, 4.0, (261.6, 329.6))
        elif name.endswith(".pdf"):
            _make_image(src, (1240, 1754), (245, 235, 235))
        else:
            src.write_text(f"demo content for {name}\n", encoding="utf-8")

    history = OperationHistory()
    try:
        txn = history.start_transaction(metadata={"command": "organize ~/Downloads"})
        for name, dest_dir in moves:
            src = downloads / name
            dest = dest_dir / name
            # Mutate first, log after: an operation is recorded as
            # COMPLETED only once the move has actually happened, so a
            # failed move aborts the staging (exception propagates and
            # no capture is produced) instead of leaving a completed-
            # looking record for a move that never occurred. Tradeoff:
            # log_operation can no longer hash the (moved) source file;
            # the History view does not display that field.
            shutil.move(str(src), str(dest))
            history.log_operation(
                OperationType.MOVE,
                source_path=src,
                destination_path=dest,
                transaction_id=txn,
            )
        history.commit_transaction(txn)
    finally:
        history.close()


def write_config(home: Path) -> None:
    """Mark setup as completed so the app opens the main layout."""
    from file_organizer.config.manager import ConfigManager
    from file_organizer.config.schema import AppConfig

    config = AppConfig(setup_completed=True, default_methodology="para")
    ConfigManager().save(config, force=True)


def _write_svg(path: Path, svg: str) -> None:
    """Write an SVG normalized to pass the repo's whitespace hooks.

    Trailing whitespace only occurs on markup lines (never inside
    rendered ``<text>`` content, which the exporters escape), so
    stripping it does not affect how the capture renders.
    """
    lines = [line.rstrip() for line in svg.splitlines()]
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# TUI capture
# ---------------------------------------------------------------------------


async def capture_tui(out_dir: Path) -> list[tuple[str, int]]:
    """Drive the real app and export SVG screenshots; return GIF frames."""
    import time

    from textual.worker import WorkerState

    from file_organizer.tui.app import FileOrganizerApp

    frames: list[tuple[str, int]] = []
    app = FileOrganizerApp()

    async def settle(pilot, delay: float = 0.3, timeout: float = 20.0) -> None:
        # DirectoryTree owns a perpetual "_loader" worker, so waiting for
        # ALL workers never returns; wait for the finite ones instead.
        await pilot.pause(delay)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            busy = [
                w
                for w in app.workers
                if w.state in (WorkerState.PENDING, WorkerState.RUNNING) and w.name != "_loader"
            ]
            if not busy:
                break
            await pilot.pause(0.1)
        await pilot.pause(delay)

    def shot(name: str | None, title: str, duration: int = 1800) -> None:
        svg = app.export_screenshot(title=title)
        if name:
            _write_svg(out_dir / name, svg)
        frames.append((svg, duration))

    async with app.run_test(size=TERM_SIZE) as pilot:
        await settle(pilot, 0.5)

        # The hidden FilterInput takes initial focus and swallows keys;
        # focus the tree so navigation and the 1-8 bindings work.
        app.set_focus(app.query_one("#file-tree"))
        await pilot.pause(0.2)

        # Files view: highlight the markdown report so the preview panel
        # shows real text content (13th entry in sorted order).
        for _ in range(13):
            await pilot.press("down")
            await pilot.pause(0.05)
        await settle(pilot)
        shot("tui-overview.svg", "File Organizer — Files", 2600)

        await pilot.press("2")
        await settle(pilot, 0.5)
        shot("organization-preview.svg", "File Organizer — Organized (dry-run)", 2200)

        await pilot.press("3")
        await settle(pilot, 0.5)
        shot("analytics-dashboard.svg", "File Organizer — Analytics", 2600)

        await pilot.press("4")
        await settle(pilot)
        shot("methodology-view.svg", "File Organizer — Methodology", 2200)

        await pilot.press("5")
        await settle(pilot, 0.6)
        shot("audio-panel.svg", "File Organizer — Audio", 2400)

        await pilot.press("6")
        await settle(pilot, 0.5)
        shot("history-view.svg", "File Organizer — History", 2400)

        await pilot.press("8")
        await settle(pilot)
        frames.append((app.export_screenshot(title="File Organizer — Copilot"), 1400))

        for ch in "help":
            await pilot.press(ch)
        await pilot.pause(0.2)
        await pilot.press("enter")
        await settle(pilot, 0.5)

        for ch in "find invoice":
            await pilot.press("space" if ch == " " else ch)
        await pilot.pause(0.2)
        await pilot.press("enter")
        await settle(pilot, 0.5)
        shot("copilot-chat.svg", "File Organizer — Copilot", 3200)

    return frames


# ---------------------------------------------------------------------------
# Dedupe CLI capture
# ---------------------------------------------------------------------------


def capture_dedupe_svg(downloads: Path, out_dir: Path) -> None:
    """Run the real dedupe CLI (dry-run) and export its output as SVG."""
    from rich.console import Console
    from rich.text import Text

    from file_organizer.cli.dedupe import dedupe_command

    os.environ["FORCE_COLOR"] = "1"
    os.environ["COLUMNS"] = "100"
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        dedupe_command([str(downloads), "--dry-run", "--strategy", "oldest", "--batch"])
    os.environ.pop("FORCE_COLOR", None)

    console = Console(record=True, width=100, file=io.StringIO(), force_terminal=True)
    console.print(Text.from_ansi(buffer.getvalue()))
    # Title must state the exact command that produced this output.
    svg = console.export_svg(title="fo dedupe ~/Downloads --dry-run --strategy oldest --batch")
    _write_svg(out_dir / "dedupe-report.svg", svg)


# ---------------------------------------------------------------------------
# GIF assembly
# ---------------------------------------------------------------------------


def build_gif(frames: list[tuple[str, int]], out_path: Path) -> None:
    """Render SVG frames with Chromium and assemble an animated GIF."""
    from PIL import Image
    from playwright.sync_api import sync_playwright

    pngs: list[bytes] = []
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception:
            # Fall back to a system chromium when playwright's own
            # browser download is unavailable (e.g. sandboxed CI).
            browser = p.chromium.launch(
                executable_path=os.environ.get("CAPTURE_CHROMIUM", "/opt/pw-browsers/chromium")
            )
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 1200}, device_scale_factor=2)
            for svg, _duration in frames:
                page.set_content("<style>body{margin:0;background:#0f0f0f}</style>" + svg)
                element = page.query_selector("svg")
                pngs.append(element.screenshot())
        finally:
            browser.close()

    images = []
    for png in pngs:
        img = Image.open(io.BytesIO(png)).convert("RGB")
        ratio = GIF_WIDTH / img.width
        img = img.resize((GIF_WIDTH, int(img.height * ratio)), Image.Resampling.LANCZOS)
        images.append(img.quantize(colors=GIF_COLORS, method=Image.Quantize.MEDIANCUT))
    images[0].save(
        out_path,
        save_all=True,
        append_images=images[1:],
        duration=[d for _, d in frames],
        loop=0,
        optimize=True,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    """Stage the demo home, capture all assets, and report output paths."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--home",
        type=Path,
        default=Path(tempfile.gettempdir()) / "fo-demo-home",
        help="Demo home directory to stage (shown in screenshots)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "docs" / "assets",
        help="Directory to write captured assets into",
    )
    parser.add_argument("--skip-gif", action="store_true", help="Skip GIF rendering (no Chromium)")
    args = parser.parse_args()

    home: Path = args.home.resolve()
    out_dir: Path = args.out.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # The reset below is destructive and --home is user-controlled: only
    # delete a directory this script previously created (identified by its
    # marker file) or an empty one, so a typo like "--home ~" is refused
    # instead of wiping a real home directory.
    marker = home / ".fo-demo-home-marker"
    if home.exists():
        if not marker.exists() and any(home.iterdir()):
            parser.error(
                f"refusing to delete {home}: it is not a demo home created "
                "by this script; pass a new or empty directory"
            )
        shutil.rmtree(home)
    home.mkdir(parents=True)
    marker.write_text("created by scripts/capture_tui_assets.py\n", encoding="utf-8")

    # Isolate all app state under the demo home BEFORE importing the app.
    os.environ["HOME"] = str(home)
    os.environ["XDG_CONFIG_HOME"] = str(home / ".config")
    os.environ["XDG_DATA_HOME"] = str(home / ".local" / "share")
    os.environ["XDG_STATE_HOME"] = str(home / ".local" / "state")
    os.environ["FO_DISABLE_UPDATE_CHECK"] = "1"

    downloads = build_workspace(home)
    write_config(home)
    seed_history(home, downloads)
    os.chdir(downloads)

    # TUI first: the dedupe run creates .file_organizer_backups inside
    # Downloads, which would otherwise clutter the file browser capture.
    frames = asyncio.run(capture_tui(out_dir))
    capture_dedupe_svg(downloads, out_dir)
    if not args.skip_gif:
        build_gif(frames, out_dir / "tui-demo.gif")

    for asset in sorted(out_dir.iterdir()):
        print(f"{asset} ({asset.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
