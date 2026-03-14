"""Benchmark command for performance measurement and regression detection.

Provides ``file-organizer benchmark run`` with statistical output
(median, p95, p99, stddev, throughput), hardware profile inclusion,
warmup exclusion, suite selection, and baseline comparison with
regression flagging.
"""

from __future__ import annotations

import contextlib
import io
import json
import math
import shutil
import statistics
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict

import typer

benchmark_app = typer.Typer(
    name="benchmark",
    help="Benchmark file processing performance.",
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


class BenchmarkStats(TypedDict):
    """Statistical results from a benchmark run."""

    median_ms: float
    p95_ms: float
    p99_ms: float
    stddev_ms: float
    throughput_fps: float
    iterations: int


class ComparisonResult(TypedDict):
    """Baseline comparison output."""

    deltas_pct: dict[str, float]
    regression: bool
    threshold: float


class _SuiteRunner(TypedDict):
    """Metadata for a benchmark suite runner."""

    run: Callable[[list[Path]], None]
    description: str


# ---------------------------------------------------------------------------
# Statistical helpers
# ---------------------------------------------------------------------------


def _percentile(sorted_data: Sequence[float], pct: float) -> float:
    """Return the *pct*-th percentile from pre-sorted *sorted_data*.

    Uses the nearest-rank method.
    """
    if not sorted_data:
        return 0.0
    k = max(0, math.ceil(pct / 100.0 * len(sorted_data)) - 1)
    return sorted_data[k]


def compute_stats(times_ms: list[float], file_count: int) -> BenchmarkStats:
    """Return a statistics dict from a list of iteration times in ms.

    Keys: ``median_ms``, ``p95_ms``, ``p99_ms``, ``stddev_ms``,
    ``throughput_fps``, ``iterations``.
    """
    if not times_ms:
        return BenchmarkStats(
            median_ms=0.0,
            p95_ms=0.0,
            p99_ms=0.0,
            stddev_ms=0.0,
            throughput_fps=0.0,
            iterations=0,
        )

    sorted_t = sorted(times_ms)
    median = statistics.median(sorted_t)
    stddev = statistics.stdev(sorted_t) if len(sorted_t) >= 2 else 0.0
    p95 = _percentile(sorted_t, 95)
    p99 = _percentile(sorted_t, 99)

    # Throughput: files per second based on median iteration time
    throughput = (file_count / (median / 1000.0)) if median > 0 else 0.0

    return BenchmarkStats(
        median_ms=round(median, 3),
        p95_ms=round(p95, 3),
        p99_ms=round(p99, 3),
        stddev_ms=round(stddev, 3),
        throughput_fps=round(throughput, 2),
        iterations=len(sorted_t),
    )


def compare_results(
    current: dict[str, Any],
    baseline: dict[str, Any],
    threshold: float = 1.2,
) -> ComparisonResult:
    """Compare *current* results against *baseline*.

    Returns a dict with ``deltas_pct`` and a ``regression`` flag
    (True if p95 exceeds *threshold* x baseline p95).
    """
    cur = current.get("results", current)
    base = baseline.get("results", baseline)

    deltas: dict[str, float] = {}
    for key in ("median_ms", "p95_ms", "p99_ms", "stddev_ms", "throughput_fps"):
        cur_val = cur.get(key, 0.0)
        base_val = base.get(key, 0.0)
        if base_val != 0:
            deltas[key] = round((cur_val - base_val) / base_val * 100, 1)
        else:
            deltas[key] = 0.0

    regression = cur.get("p95_ms", 0.0) > threshold * base.get("p95_ms", 1.0)

    return ComparisonResult(
        deltas_pct=deltas,
        regression=regression,
        threshold=threshold,
    )


# ---------------------------------------------------------------------------
# Suite runners
# ---------------------------------------------------------------------------

_MAX_SUITE_FILES = 50
_MAX_E2E_FILES = 25

_TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".rst",
    ".pdf",
    ".doc",
    ".docx",
    ".csv",
    ".tsv",
    ".json",
    ".xml",
    ".yaml",
    ".yml",
}
_VISION_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff"}
_AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac", ".wma", ".opus"}
_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".webm"}


class _BenchmarkModelStub:
    """In-memory model stub used by benchmark suite runners.

    Why this exists:
    - Benchmark suite selection should exercise real processor code paths.
    - CI and local developer environments cannot assume Ollama/API backends.
    - A deterministic stub keeps suite behavior stable and comparable.
    """

    def __init__(
        self,
        *,
        model_type: Any,
        prompt_responses: dict[str, str],
        default_response: str,
    ) -> None:
        from file_organizer.models.base import ModelConfig

        self.config = ModelConfig(name="benchmark-stub", model_type=model_type)
        self._prompt_responses = prompt_responses
        self._default_response = default_response
        self._initialized = True

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    def initialize(self) -> None:
        self._initialized = True

    def generate(self, prompt: str, **_: Any) -> str:
        lowered = prompt.lower()
        for needle, response in self._prompt_responses.items():
            if needle in lowered:
                return response
        return self._default_response

    def cleanup(self) -> None:
        self._initialized = False


def _suite_candidates(
    files: list[Path],
    extensions: set[str],
    *,
    fallback_to_all: bool,
    cap: int = _MAX_SUITE_FILES,
) -> list[Path]:
    """Return a capped file list for a benchmark suite."""
    matches = [path for path in files if path.suffix.lower() in extensions]
    selected = matches if matches else files if fallback_to_all else []
    return selected[: min(cap, len(selected))]


def _run_io_suite(files: list[Path]) -> None:
    """Baseline I/O benchmark: measures file stat access overhead."""
    for file_path in _suite_candidates(files, set(), fallback_to_all=True):
        try:
            _ = file_path.stat()
        except OSError:
            pass


def _run_text_suite(files: list[Path]) -> None:
    """Benchmark text processing path via TextProcessor.process_file()."""
    candidates = _suite_candidates(files, _TEXT_EXTENSIONS, fallback_to_all=True)
    if not candidates:
        return

    from file_organizer.models.base import ModelType
    from file_organizer.services import TextProcessor

    model = _BenchmarkModelStub(
        model_type=ModelType.TEXT,
        prompt_responses={
            "summary:": "Synthetic benchmark summary for deterministic text runs.",
            "category:": "benchmark_docs",
            "filename:": "benchmark_text_file",
        },
        default_response="Synthetic benchmark response",
    )
    processor = TextProcessor(text_model=model)
    try:
        for file_path in candidates:
            try:
                processor.process_file(file_path)
            except Exception:
                _ = file_path.stat()
    finally:
        processor.cleanup()


def _run_vision_suite(files: list[Path]) -> None:
    """Benchmark vision processing path via VisionProcessor.process_file()."""
    candidates = _suite_candidates(files, _VISION_EXTENSIONS, fallback_to_all=True)
    if not candidates:
        return

    from file_organizer.models.base import ModelType
    from file_organizer.services import VisionProcessor

    model = _BenchmarkModelStub(
        model_type=ModelType.VISION,
        prompt_responses={
            "extract all visible text": "NO_TEXT",
            "category:": "benchmark_images",
            "filename:": "benchmark_image_file",
        },
        default_response="Synthetic benchmark image description.",
    )
    processor = VisionProcessor(vision_model=model)
    try:
        for file_path in candidates:
            try:
                processor.process_file(file_path, perform_ocr=False)
            except Exception:
                _ = file_path.stat()
    finally:
        processor.cleanup()


def _run_audio_suite(files: list[Path]) -> None:
    """Benchmark audio metadata + classification path."""
    candidates = _suite_candidates(files, _AUDIO_EXTENSIONS, fallback_to_all=False)
    if not candidates:
        _run_io_suite(files)
        return

    from file_organizer.services.audio.classifier import AudioClassifier
    from file_organizer.services.audio.metadata_extractor import AudioMetadataExtractor

    extractor = AudioMetadataExtractor(use_fallback=True)
    classifier = AudioClassifier()
    for file_path in candidates:
        try:
            metadata = extractor.extract(file_path)
            _ = classifier.classify(metadata)
        except Exception:
            try:
                _ = file_path.stat()
            except OSError:
                pass


def _suite_category_for(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in _TEXT_EXTENSIONS:
        return "documents"
    if suffix in _VISION_EXTENSIONS:
        return "images"
    if suffix in _AUDIO_EXTENSIONS:
        return "audio"
    if suffix in _VIDEO_EXTENSIONS:
        return "video"
    return "other"


class _BenchmarkPreprocessStage:
    @property
    def name(self) -> str:
        return "benchmark.preprocess"

    def process(self, context: Any) -> Any:
        context.metadata["file_size"] = context.file_path.stat().st_size
        context.metadata["extension"] = context.file_path.suffix.lower()
        return context


class _BenchmarkAnalyzeStage:
    @property
    def name(self) -> str:
        return "benchmark.analyze"

    def process(self, context: Any) -> Any:
        context.category = _suite_category_for(context.file_path)
        context.filename = context.file_path.stem or "benchmark_file"
        return context


@dataclass
class _BenchmarkPostprocessStage:
    output_directory: Path

    @property
    def name(self) -> str:
        return "benchmark.postprocess"

    def process(self, context: Any) -> Any:
        context.destination = (
            self.output_directory
            / context.category
            / f"{context.filename}{context.file_path.suffix}"
        )
        return context


def _run_pipeline_suite(files: list[Path]) -> None:
    """Benchmark the PipelineOrchestrator stage path end-to-end."""
    candidates = _suite_candidates(files, set(), fallback_to_all=True)
    if not candidates:
        return

    from file_organizer.pipeline.config import PipelineConfig
    from file_organizer.pipeline.orchestrator import PipelineOrchestrator

    with tempfile.TemporaryDirectory(prefix="fo-benchmark-pipeline-") as tmp:
        output_dir = Path(tmp) / "pipeline_output"
        output_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = PipelineOrchestrator(
            config=PipelineConfig(
                output_directory=output_dir,
                dry_run=True,
                auto_organize=False,
                max_concurrent=2,
            ),
            stages=[
                _BenchmarkPreprocessStage(),
                _BenchmarkAnalyzeStage(),
                _BenchmarkPostprocessStage(output_dir),
            ],
            prefetch_depth=1,
            prefetch_stages=1,
        )
        try:
            _ = orchestrator.process_batch(candidates)
        finally:
            orchestrator.stop()


def _run_e2e_suite(files: list[Path]) -> None:
    """Benchmark full organizer flow including file writes."""
    preferred_extensions = _VISION_EXTENSIONS | _AUDIO_EXTENSIONS
    preferred = _suite_candidates(
        files,
        preferred_extensions,
        fallback_to_all=False,
        cap=_MAX_E2E_FILES,
    )
    candidates = preferred or _suite_candidates(
        files,
        set(),
        fallback_to_all=True,
        cap=_MAX_E2E_FILES,
    )
    if not candidates:
        return

    from file_organizer.core.organizer import FileOrganizer

    with tempfile.TemporaryDirectory(prefix="fo-benchmark-e2e-") as tmp:
        workspace = Path(tmp)
        input_dir = workspace / "input"
        output_dir = workspace / "output"
        input_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        copied: list[Path] = []
        for index, source in enumerate(candidates):
            target = input_dir / f"{index:03d}_{source.name}"
            try:
                shutil.copy2(source, target)
                copied.append(target)
            except OSError:
                continue

        if not copied:
            return

        organizer = FileOrganizer(
            dry_run=False,
            use_hardlinks=False,
            parallel_workers=1,
            no_prefetch=True,
            prefetch_depth=0,
            enable_vision=False,
        )
        try:
            with (
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                organizer.organize(input_dir, output_dir, skip_existing=False)
        except Exception:
            _run_io_suite(copied)


_SUITE_RUNNERS: dict[str, _SuiteRunner] = {
    "io": {
        "run": _run_io_suite,
        "description": "File stat/read overhead only.",
    },
    "text": {
        "run": _run_text_suite,
        "description": "TextProcessor stack with deterministic benchmark model.",
    },
    "vision": {
        "run": _run_vision_suite,
        "description": "VisionProcessor stack with deterministic benchmark model.",
    },
    "audio": {
        "run": _run_audio_suite,
        "description": "Audio metadata extraction + classification path.",
    },
    "pipeline": {
        "run": _run_pipeline_suite,
        "description": "PipelineOrchestrator staged processing path.",
    },
    "e2e": {
        "run": _run_e2e_suite,
        "description": "Full FileOrganizer run including output writes in temp workspace.",
    },
}


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _print_table(
    console: Any, suite: str, warmup: int, stats: BenchmarkStats, file_count: int
) -> None:
    """Print benchmark results as a Rich table."""
    from rich.table import Table

    table = Table(title=f"Benchmark Results (suite={suite})")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Files", str(file_count))
    table.add_row("Iterations (measured)", str(stats["iterations"]))
    table.add_row("Warmup (excluded)", str(warmup))
    table.add_row("Median (ms)", f"{stats['median_ms']:.3f}")
    table.add_row("P95 (ms)", f"{stats['p95_ms']:.3f}")
    table.add_row("P99 (ms)", f"{stats['p99_ms']:.3f}")
    table.add_row("Stddev (ms)", f"{stats['stddev_ms']:.3f}")
    table.add_row("Throughput (files/s)", f"{stats['throughput_fps']:.2f}")

    console.print(table)


def _print_comparison(console: Any, comp: dict[str, Any], *, json_output: bool) -> None:
    """Print baseline comparison results."""
    if json_output:
        console.print(json.dumps({"comparison": comp}, indent=2))
        return

    console.print("\n[bold]Comparison vs baseline:[/bold]")
    for key, delta in comp["deltas_pct"].items():
        # For throughput, higher is better; for latency metrics, lower is better
        if key == "throughput_fps":
            color = "green" if delta > 5 else "red" if delta < -20 else "yellow"
        else:
            color = "red" if delta > 20 else "green" if delta < -5 else "yellow"
        console.print(f"  {key}: [{color}]{delta:+.1f}%[/{color}]")

    if comp["regression"]:
        console.print(
            "\n[bold red]REGRESSION DETECTED[/bold red]: "
            f"p95 exceeds {comp['threshold']:.0%} of baseline"
        )
    else:
        console.print("\n[bold green]No regression detected[/bold green]")


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------


@benchmark_app.command()
def run(
    input_path: Path = typer.Argument(
        Path("tests/fixtures/"),
        help="Path to files to benchmark.",
    ),
    iterations: int = typer.Option(
        10,
        "--iterations",
        "-i",
        help="Number of measured iterations to run (excluding warmup). Total runs = warmup + iterations.",
        min=1,
    ),
    warmup: int = typer.Option(
        3,
        "--warmup",
        "-w",
        help="Warmup iterations excluded from statistics.",
        min=0,
    ),
    suite: str = typer.Option(
        "io",
        "--suite",
        "-s",
        help=(
            "Benchmark suite to run (io, text, vision, audio, pipeline, e2e). "
            "Each suite executes a dedicated runner."
        ),
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output results as JSON.",
    ),
    compare_path: Path | None = typer.Option(
        None,
        "--compare",
        help="Path to baseline JSON file for regression comparison.",
    ),
) -> None:
    """Run a performance benchmark with statistical output.

    Measures timing statistics across multiple iterations with warmup
    exclusion.  Supports suite selection and baseline comparison.
    """
    from rich.console import Console

    console = Console()
    input_path = input_path.resolve()

    if not input_path.exists():
        console.print(f"[red]Error: Path does not exist: {input_path}[/red]")
        raise typer.Exit(code=1)

    # Collect files
    try:
        files = [f for f in input_path.rglob("*") if f.is_file()]
    except Exception as e:
        console.print(f"[red]Error reading files: {e}[/red]")
        raise typer.Exit(code=1) from e

    if not files:
        if json_output:
            hw_profile_empty: dict[str, Any] = {}
            try:
                from file_organizer.core.hardware_profile import detect_hardware

                hw_profile_empty = detect_hardware().to_dict()
            except Exception:
                hw_profile_empty = {"error": "Hardware detection unavailable"}
            console.print(
                json.dumps(
                    {
                        "suite": suite,
                        "files_count": 0,
                        "hardware_profile": hw_profile_empty,
                        "results": compute_stats([], 0),
                    },
                    indent=2,
                )
            )
        else:
            console.print("[yellow]No files found in the specified path.[/yellow]")
        return

    # Select suite runner
    suite_spec = _SUITE_RUNNERS.get(suite)
    if suite_spec is None:
        console.print(f"[red]Unknown suite: {suite}[/red]")
        raise typer.Exit(code=1)
    runner = suite_spec["run"]

    # Ensure we have enough iterations
    total_iterations = warmup + iterations
    if not json_output:
        console.print(
            f"[bold]Benchmarking[/bold] {len(files)} files, "
            f"suite={suite}, {iterations} iterations + {warmup} warmup"
        )
        console.print(f"[dim]Suite profile: {suite_spec['description']}[/dim]")

    # Run iterations
    all_times_ms: list[float] = []
    for i in range(total_iterations):
        if not json_output:
            label = "warmup" if i < warmup else f"{i - warmup + 1}/{iterations}"
            console.print(f"[dim]Iteration {i + 1}/{total_iterations} ({label})...[/dim]")

        start = time.monotonic()
        runner(files)
        elapsed_ms = (time.monotonic() - start) * 1000
        all_times_ms.append(elapsed_ms)

    # Exclude warmup
    measured = all_times_ms[warmup:]

    # Statistics
    stats = compute_stats(measured, len(files))

    # Hardware profile
    hw_profile: dict[str, Any] = {}
    try:
        from file_organizer.core.hardware_profile import detect_hardware

        hw = detect_hardware()
        hw_profile = hw.to_dict()
    except Exception:
        hw_profile = {"error": "Hardware detection unavailable"}

    # Build output
    output: dict[str, Any] = {
        "suite": suite,
        "files_count": len(files),
        "hardware_profile": hw_profile,
        "results": stats,
    }

    # Comparison (must be built before JSON print to emit a single document)
    if compare_path is not None:
        try:
            baseline = json.loads(compare_path.read_text())
        except Exception as e:
            console.print(f"[red]Failed to read baseline: {e}[/red]")
            raise typer.Exit(code=1) from e

        comp = compare_results(output, baseline)
        output["comparison"] = comp

    if json_output:
        console.print(json.dumps(output, indent=2))
    else:
        _print_table(console, suite, warmup, stats, len(files))
        if compare_path is not None:
            _print_comparison(console, output["comparison"], json_output=False)
        console.print("\n[bold green]Benchmark completed[/bold green]")
