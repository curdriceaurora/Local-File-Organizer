"""Benchmark command for performance measurement and regression detection.

Provides ``fo benchmark run`` with statistical output
(median, p95, p99, stddev, throughput), hardware profile inclusion,
warmup exclusion, suite selection, and baseline comparison with
regression flagging.
"""

from __future__ import annotations

import contextlib
import functools
import io
import json
import logging
import math
import shutil
import statistics
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, TypedDict, cast

import typer

from file_organizer.cli.path_validation import resolve_cli_path
from file_organizer.core.path_guard import safe_walk
from file_organizer.models.audio_model import AudioModel
from file_organizer.models.base import ModelConfig, ModelType

if TYPE_CHECKING:
    from file_organizer.services.audio.metadata_extractor import AudioMetadata

benchmark_app = typer.Typer(
    name="benchmark",
    help="Benchmark file processing performance.",
    no_args_is_help=True,
)
logger = logging.getLogger(__name__)


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


class BenchmarkPayload(TypedDict):
    """Canonical JSON payload emitted by benchmark CLI."""

    suite: str
    effective_suite: str
    degraded: bool
    degradation_reasons: list[str]
    runner_profile_version: str
    files_count: int
    hardware_profile: dict[str, Any]
    results: BenchmarkStats


@dataclass(frozen=True, slots=True)
class _SuiteExecutionClassification:
    """Runtime classification for one suite iteration."""

    effective_suite: str
    degraded: bool
    degradation_reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _SuiteIterationOutcome:
    """Per-iteration suite runner outcome consumed by classification.

    The smoke pair (``transcription_smoke_requested`` /
    ``transcription_smoke_passed``) lets ``_classify_audio_suite`` distinguish
    "smoke not asked for" from "smoke asked for but couldn't run" — required
    so ``--transcribe-smoke`` doesn't silently succeed when the ``[audio]``
    extra is missing.
    """

    processed_count: int
    used_synthetic_audio_metadata: bool = False
    transcription_smoke_requested: bool = False
    transcription_smoke_passed: bool = False


class _SuiteRunner(TypedDict):
    """Metadata for a benchmark suite runner."""

    run: Callable[[list[Path]], _SuiteIterationOutcome]
    classify: Callable[[list[Path], _SuiteIterationOutcome], _SuiteExecutionClassification]
    description: str


_RUNNER_PROFILE_VERSION = "2026-03-14-v1"

# Cap discovery so a pathologically large input tree can't exhaust memory
# before the suite-specific cap is applied. Chosen to exceed every real
# benchmark corpus we ship (<500 files) with comfortable headroom.
_MAX_BENCHMARK_FILES = 10_000


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


def _require_non_negative_numeric_field(value: Any, *, field: str) -> None:
    """Validate numeric payload field while rejecting bool coercion edge cases."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"Benchmark payload field '{field}' must be numeric.")
    if value < 0:
        raise ValueError(f"Benchmark payload field '{field}' must be non-negative.")


def _require_payload_fields(payload: dict[str, Any]) -> None:
    """Ensure all required top-level benchmark payload fields are present."""
    required_top_level = (
        "suite",
        "effective_suite",
        "degraded",
        "degradation_reasons",
        "runner_profile_version",
        "files_count",
        "hardware_profile",
        "results",
    )
    missing_top_level = [field for field in required_top_level if field not in payload]
    if missing_top_level:
        raise KeyError(f"Missing benchmark payload fields: {', '.join(sorted(missing_top_level))}")


def _validate_payload_identity_fields(payload: dict[str, Any]) -> None:
    """Validate top-level payload identity and suite execution metadata."""
    for key in ("suite", "effective_suite", "runner_profile_version"):
        value = payload[key]
        if not isinstance(value, str):
            raise TypeError(f"Benchmark payload field '{key}' must be a string.")
        if not value:
            raise ValueError(f"Benchmark payload field '{key}' must be non-empty.")


def _validate_payload_degradation_reasons(payload: dict[str, Any]) -> None:
    """Validate degradation reasons contract for degraded and non-degraded runs."""
    degraded = payload["degraded"]
    if not isinstance(degraded, bool):
        raise TypeError(
            "Benchmark payload fields 'degraded' and 'degradation_reasons' require "
            "'degraded' to be a bool."
        )

    degradation_reasons = payload["degradation_reasons"]
    if not isinstance(degradation_reasons, list):
        raise TypeError("Benchmark payload field 'degradation_reasons' must be a list.")
    for idx, reason in enumerate(degradation_reasons):
        if not isinstance(reason, str) or not reason:
            raise ValueError(
                f"Benchmark payload field 'degradation_reasons[{idx}]' must be a non-empty string."
            )

    if degraded and not degradation_reasons:
        raise ValueError(
            "Benchmark payload fields 'degraded' and 'degradation_reasons' are inconsistent: "
            "when 'degraded' is True, 'degradation_reasons' must be non-empty."
        )
    if not degraded and degradation_reasons:
        raise ValueError(
            "Benchmark payload fields 'degraded' and 'degradation_reasons' are inconsistent: "
            "when 'degraded' is False, 'degradation_reasons' must be empty."
        )


def _validate_payload_results(results: dict[str, Any]) -> None:
    """Validate benchmark result metrics contract for JSON payload output."""
    required_result_fields = (
        "median_ms",
        "p95_ms",
        "p99_ms",
        "stddev_ms",
        "throughput_fps",
        "iterations",
    )
    missing_result_fields = [field for field in required_result_fields if field not in results]
    if missing_result_fields:
        raise KeyError(
            f"Missing benchmark payload results fields: {', '.join(missing_result_fields)}"
        )

    for field in required_result_fields:
        _require_non_negative_numeric_field(results[field], field=f"results.{field}")

    if isinstance(results["iterations"], bool) or not isinstance(results["iterations"], int):
        raise TypeError("Benchmark payload field 'results.iterations' must be an int.")


def validate_benchmark_payload(payload: dict[str, Any]) -> None:
    """Validate the canonical benchmark JSON payload contract.

    Why this exists:
    - Benchmark JSON is consumed by CI contract tests and regression tooling.
    - A single validator prevents schema drift between runtime and tests.
    - Fail-fast validation makes regressions explicit instead of silently tolerated.
    """
    _require_payload_fields(payload)
    _validate_payload_identity_fields(payload)
    _validate_payload_degradation_reasons(payload)

    files_count = payload["files_count"]
    if isinstance(files_count, bool) or not isinstance(files_count, int):
        raise TypeError("Benchmark payload field 'files_count' must be an int.")
    if files_count < 0:
        raise ValueError("Benchmark payload field 'files_count' must be non-negative.")

    hardware_profile = payload["hardware_profile"]
    if not isinstance(hardware_profile, dict):
        raise TypeError("Benchmark payload field 'hardware_profile' must be a dict.")

    results = payload["results"]
    if not isinstance(results, dict):
        raise TypeError("Benchmark payload field 'results' must be a dict.")
    _validate_payload_results(results)


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


def _resolve_processed_count(
    processed_counts: list[int],
    warmup: int,
    *,
    suite: str,
    console: Any,
) -> int:
    """Return processed file count, failing fast when measured counts drift."""
    measured = processed_counts[warmup:]
    if measured:
        expected_count = measured[-1]
        if any(count != expected_count for count in measured):
            console.print(
                "[red]Benchmark suite "
                f"'{suite}' produced inconsistent processed counts across iterations: "
                f"{measured}[/red]"
            )
            raise typer.Exit(code=1)
        return expected_count
    if processed_counts:
        return processed_counts[-1]
    return 0


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
        model_type: ModelType,
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
        """Whether the stub reports itself as initialized."""
        return self._initialized

    def initialize(self) -> None:
        """Mark the stub as initialized (no real model is loaded)."""
        self._initialized = True

    def generate(self, prompt: str, **_: Any) -> str:
        """Return the canned response matching *prompt* (default if none match)."""
        lowered = prompt.lower()
        for needle, response in self._prompt_responses.items():
            if needle in lowered:
                return response
        return self._default_response

    def cleanup(self) -> None:
        """Mark the stub as torn down."""
        self._initialized = False

    def safe_cleanup(self) -> None:
        """Compatibility alias for processors expecting BaseModel.safe_cleanup()."""
        self.cleanup()


def _suite_candidates(
    files: list[Path],
    extensions: set[str],
    *,
    fallback_to_all: bool = False,
    cap: int = _MAX_SUITE_FILES,
) -> list[Path]:
    """Return a capped file list for a benchmark suite."""
    matches = [path for path in files if path.suffix.lower() in extensions]
    selected = matches if matches else files if fallback_to_all else []
    return selected[: min(cap, len(selected))]


def _run_io_suite(files: list[Path]) -> _SuiteIterationOutcome:
    """Baseline I/O benchmark: measures file stat access overhead."""
    candidates = _suite_candidates(files, set(), fallback_to_all=True)
    for file_path in candidates:
        try:
            _ = file_path.stat()
        except OSError:
            logger.debug("I/O benchmark failed to stat candidate %s", file_path, exc_info=True)
    return _SuiteIterationOutcome(processed_count=len(candidates))


def _run_text_suite(files: list[Path]) -> _SuiteIterationOutcome:
    """Benchmark text processing path via TextProcessor.process_file()."""
    candidates = _suite_candidates(files, _TEXT_EXTENSIONS)
    if not candidates:
        typer.echo("Warning: no text files found for text suite; skipping benchmark.", err=True)
        return _SuiteIterationOutcome(processed_count=0)

    from file_organizer.models.base import BaseModel, ModelType
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
    processor = TextProcessor(text_model=cast(BaseModel, model))
    try:
        for file_path in candidates:
            processor.process_file(file_path)
    finally:
        processor.cleanup()
    return _SuiteIterationOutcome(processed_count=len(candidates))


def _run_vision_suite(files: list[Path]) -> _SuiteIterationOutcome:
    """Benchmark vision processing path via VisionProcessor.process_file()."""
    candidates = _suite_candidates(files, _VISION_EXTENSIONS)
    if not candidates:
        typer.echo("Warning: no vision files found for vision suite; skipping benchmark.", err=True)
        return _SuiteIterationOutcome(processed_count=0)

    from file_organizer.models.base import BaseModel, ModelType
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
    processor = VisionProcessor(vision_model=cast(BaseModel, model))
    try:
        for file_path in candidates:
            processor.process_file(file_path, perform_ocr=False)
    finally:
        processor.cleanup()
    return _SuiteIterationOutcome(processed_count=len(candidates))


def _synthesized_audio_metadata(file_path: Path) -> AudioMetadata:
    """Return minimal audio metadata when optional extractors are unavailable."""
    from file_organizer.services.audio.metadata_extractor import AudioMetadata

    stat = file_path.stat()
    return AudioMetadata(
        file_path=file_path,
        file_size=stat.st_size,
        format=file_path.suffix[1:].upper() if file_path.suffix else "UNKNOWN",
        duration=0.0,
        bitrate=0,
        sample_rate=0,
        channels=0,
    )


def _run_audio_suite(
    files: list[Path],
    transcribe_smoke: bool = False,
) -> _SuiteIterationOutcome:
    """Benchmark audio metadata + classification path.

    With ``transcribe_smoke=True``, additionally runs ``AudioModel.generate()``
    on the first candidate file to prove end-to-end transcription works.
    Counted as a single smoke pass; not a per-file benchmark.
    """
    candidates = _suite_candidates(files, _AUDIO_EXTENSIONS, fallback_to_all=False)
    if not candidates:
        typer.echo("Warning: no audio files found; falling back to IO-only benchmark.", err=True)
        return _run_io_suite(files)

    from file_organizer.services.audio.classifier import AudioClassifier
    from file_organizer.services.audio.metadata_extractor import AudioMetadataExtractor

    extractor = AudioMetadataExtractor(use_fallback=True)
    classifier = AudioClassifier()
    used_synthetic_metadata = False
    for file_path in candidates:
        try:
            metadata = extractor.extract(file_path)
        except ImportError:
            used_synthetic_metadata = True
            metadata = _synthesized_audio_metadata(file_path)
        except Exception as exc:
            raise RuntimeError(f"Audio benchmark runner failed for {file_path}: {exc}") from exc
        _ = classifier.classify(metadata)

    transcription_smoke_passed = False
    if transcribe_smoke:
        try:
            config = ModelConfig(name="tiny", model_type=ModelType.AUDIO)
            model = AudioModel(config)
            try:
                model.initialize()
                _ = model.generate(str(candidates[0]))
                transcription_smoke_passed = True
            finally:
                model.safe_cleanup()
        except ImportError as exc:
            # The smoke check was requested but couldn't run. Leave
            # transcription_smoke_passed=False so _classify_audio_suite
            # marks the run degraded; run() will surface a non-zero exit
            # at the end. The warning is for the human reading stderr.
            typer.echo(
                f"Warning: --transcribe-smoke requires [audio] extra: {exc}",
                err=True,
            )

    return _SuiteIterationOutcome(
        processed_count=len(candidates),
        used_synthetic_audio_metadata=used_synthetic_metadata,
        transcription_smoke_requested=transcribe_smoke,
        transcription_smoke_passed=transcription_smoke_passed,
    )


def _run_pipeline_suite(files: list[Path]) -> _SuiteIterationOutcome:
    """Benchmark the PipelineOrchestrator stage path end-to-end."""
    candidates = _suite_candidates(files, set(), fallback_to_all=True)
    if not candidates:
        return _SuiteIterationOutcome(processed_count=0)

    from file_organizer.pipeline.config import PipelineConfig
    from file_organizer.pipeline.orchestrator import PipelineOrchestrator
    from file_organizer.pipeline.processor_pool import ProcessorPool
    from file_organizer.pipeline.router import FileRouter
    from file_organizer.pipeline.stages.analyzer import AnalyzerStage
    from file_organizer.pipeline.stages.postprocessor import PostprocessorStage
    from file_organizer.pipeline.stages.preprocessor import PreprocessorStage
    from file_organizer.pipeline.stages.writer import WriterStage

    with tempfile.TemporaryDirectory(prefix="fo-benchmark-pipeline-") as tmp:
        output_dir = Path(tmp) / "pipeline_output"
        output_dir.mkdir(parents=True, exist_ok=True)
        router = FileRouter()
        pool = ProcessorPool()
        orchestrator = PipelineOrchestrator(
            config=PipelineConfig(
                output_directory=output_dir,
                dry_run=True,
                auto_organize=False,
                max_concurrent=2,
            ),
            stages=[
                PreprocessorStage(),
                AnalyzerStage(router=router, processor_pool=pool),
                PostprocessorStage(output_dir),
                WriterStage(),
            ],
            prefetch_depth=1,
            prefetch_stages=1,
        )
        try:
            _ = orchestrator.process_batch(candidates)
        finally:
            orchestrator.stop()
            pool.cleanup()
    return _SuiteIterationOutcome(processed_count=len(candidates))


def _run_e2e_suite(files: list[Path]) -> _SuiteIterationOutcome:
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
        return _SuiteIterationOutcome(processed_count=0)

    from file_organizer.core.organizer import FileOrganizer

    with tempfile.TemporaryDirectory(prefix="fo-benchmark-e2e-") as tmp:
        workspace = Path(tmp)
        input_dir = workspace / "input"
        output_dir = workspace / "output"
        input_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        copied: list[Path] = []
        copy_failures: list[tuple[Path, str]] = []
        for index, source in enumerate(candidates):
            target = input_dir / f"{index:03d}_{source.name}"
            try:
                shutil.copy2(source, target)  # noqa: safedir-required  # benchmark — source/target are internally managed benchmark fixture paths
                copied.append(target)
            except OSError as exc:
                copy_failures.append((source, str(exc)))
                logger.debug(
                    "Skipping e2e benchmark candidate copy; source=%s error=%s",
                    source,
                    exc,
                )
                continue
        if copy_failures:
            logger.debug(
                "E2E benchmark setup skipped %d candidate copies out of %d",
                len(copy_failures),
                len(candidates),
            )

        if not copied:
            return _SuiteIterationOutcome(processed_count=0)

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
        except Exception as exc:
            raise RuntimeError(f"E2E benchmark runner failed: {exc}") from exc
    return _SuiteIterationOutcome(processed_count=len(copied))


def _classify_io_suite(
    _: list[Path], _outcome: _SuiteIterationOutcome
) -> _SuiteExecutionClassification:
    """IO suite never degrades — it has no model or candidate requirements."""
    return _SuiteExecutionClassification(effective_suite="io", degraded=False)


def _classify_text_suite(
    files: list[Path], _outcome: _SuiteIterationOutcome
) -> _SuiteExecutionClassification:
    """Mark the text suite degraded when no text candidates were found."""
    candidates = _suite_candidates(files, _TEXT_EXTENSIONS)
    if not candidates:
        return _SuiteExecutionClassification(
            effective_suite="text",
            degraded=True,
            degradation_reasons=("text-no-candidates-skip",),
        )
    return _SuiteExecutionClassification(effective_suite="text", degraded=False)


def _classify_vision_suite(
    files: list[Path], _outcome: _SuiteIterationOutcome
) -> _SuiteExecutionClassification:
    """Mark the vision suite degraded when no image candidates were found."""
    candidates = _suite_candidates(files, _VISION_EXTENSIONS)
    if not candidates:
        return _SuiteExecutionClassification(
            effective_suite="vision",
            degraded=True,
            degradation_reasons=("vision-no-candidates-skip",),
        )
    return _SuiteExecutionClassification(effective_suite="vision", degraded=False)


def _bind_transcribe_smoke(
    runner: Callable[[list[Path]], _SuiteIterationOutcome],
    *,
    suite: str,
    transcribe_smoke: bool,
) -> Callable[[list[Path]], _SuiteIterationOutcome]:
    """Validate ``--transcribe-smoke`` against ``suite`` and bind it to the runner.

    Raises ``typer.BadParameter`` if the flag is set with a non-audio suite —
    the flag becomes a silent no-op otherwise, which falsely reports a
    successful "smoke check" to CI/scripts. When set with ``--suite audio``,
    pre-binds ``transcribe_smoke=True`` to the audio runner so the dispatch
    surface in :func:`run` doesn't need a special case.
    """
    if transcribe_smoke and suite != "audio":
        raise typer.BadParameter("--transcribe-smoke is only supported with --suite audio")
    if suite == "audio" and transcribe_smoke:
        return functools.partial(_run_audio_suite, transcribe_smoke=True)
    return runner


def _validate_transcribe_smoke_preconditions(files: list[Path], *, transcribe_smoke: bool) -> None:
    """Fail fast when ``--transcribe-smoke`` can't possibly run end-to-end.

    Otherwise the empty-input and no-audio-candidates paths short-circuit
    the benchmark before the smoke check fires, but ``run()`` still exits 0 —
    a false-positive verification signal for CI/scripts that key off exit
    code.

    Raises ``typer.BadParameter`` when ``transcribe_smoke`` is set and either
    ``files`` is empty (no input at all) or the input has no audio candidates.
    """
    if not transcribe_smoke:
        return
    if not files:
        raise typer.BadParameter(
            "--transcribe-smoke requires at least one input file; the input directory is empty."
        )
    audio_candidates = _suite_candidates(files, _AUDIO_EXTENSIONS, fallback_to_all=False)
    if not audio_candidates:
        raise typer.BadParameter(
            "--transcribe-smoke requires at least one audio file in the input; none were found."
        )


def _exit_if_transcribe_smoke_failed(
    console: Any,
    degradation_reasons: Sequence[str],
    *,
    json_output: bool = False,
) -> None:
    """Exit non-zero when ``--transcribe-smoke`` ran but no smoke completed.

    Requested but couldn't run end-to-end (typically because the ``[audio]``
    extra is missing). The benchmark output is already emitted by the time
    this fires, so JSON/human consumers see the degradation classification;
    this just propagates the failure to the shell exit code.

    When ``json_output`` is true, the failure notice is routed to stderr so
    the JSON document already on stdout stays machine-parseable.
    """
    if "audio-transcribe-smoke-skipped" not in degradation_reasons:
        return
    error_msg = (
        "[red]Error: --transcribe-smoke was requested but could not run "
        "end-to-end (see warnings above). Install the [audio] extra "
        '(`pip install -e ".[audio]"`) and retry.[/red]'
    )
    if json_output:
        from rich.console import Console

        Console(stderr=True).print(error_msg)
    else:
        console.print(error_msg)
    raise typer.Exit(code=1)


def _classify_audio_suite(
    files: list[Path], outcome: _SuiteIterationOutcome
) -> _SuiteExecutionClassification:
    """Classify the audio run: no candidates → IO fallback; note metadata/smoke gaps."""
    candidates = _suite_candidates(files, _AUDIO_EXTENSIONS, fallback_to_all=False)
    if not candidates:
        return _SuiteExecutionClassification(
            effective_suite="io",
            degraded=True,
            degradation_reasons=("audio-no-candidates-fallback-to-io",),
        )
    reasons: list[str] = []
    if outcome.used_synthetic_audio_metadata:
        reasons.append("audio-synthesized-metadata-fallback")
    if outcome.transcription_smoke_requested and not outcome.transcription_smoke_passed:
        # --transcribe-smoke was requested but couldn't run end-to-end
        # (typically [audio] extra missing). Surface the gap to the JSON
        # consumer; run() will also exit non-zero so CI / scripts treat
        # this as a real failure rather than a successful audio benchmark.
        reasons.append("audio-transcribe-smoke-skipped")
    if reasons:
        return _SuiteExecutionClassification(
            effective_suite="audio",
            degraded=True,
            degradation_reasons=tuple(reasons),
        )
    return _SuiteExecutionClassification(effective_suite="audio", degraded=False)


def _classify_pipeline_suite(
    _: list[Path], _outcome: _SuiteIterationOutcome
) -> _SuiteExecutionClassification:
    """Pipeline suite never degrades — the orchestrator handles any file mix."""
    return _SuiteExecutionClassification(effective_suite="pipeline", degraded=False)


def _classify_e2e_suite(
    files: list[Path], outcome: _SuiteIterationOutcome
) -> _SuiteExecutionClassification:
    """Mark the e2e suite degraded when input files exist but none were processed."""
    if files and outcome.processed_count == 0:
        return _SuiteExecutionClassification(
            effective_suite="e2e",
            degraded=True,
            degradation_reasons=("e2e-no-candidates-processed",),
        )
    return _SuiteExecutionClassification(effective_suite="e2e", degraded=False)


_SUITE_RUNNERS: dict[str, _SuiteRunner] = {
    "io": {
        "run": _run_io_suite,
        "classify": _classify_io_suite,
        "description": "File stat/read overhead only.",
    },
    "text": {
        "run": _run_text_suite,
        "classify": _classify_text_suite,
        "description": "TextProcessor stack with deterministic benchmark model.",
    },
    "vision": {
        "run": _run_vision_suite,
        "classify": _classify_vision_suite,
        "description": "VisionProcessor stack with deterministic benchmark model.",
    },
    "audio": {
        "run": _run_audio_suite,
        "classify": _classify_audio_suite,
        "description": (
            "Audio metadata extraction + classification path "
            "(synthetic metadata fallback only when optional extractor deps are missing)."
        ),
    },
    "pipeline": {
        "run": _run_pipeline_suite,
        "classify": _classify_pipeline_suite,
        "description": "PipelineOrchestrator real staged processing path (pre/analyze/post/write).",
    },
    "e2e": {
        "run": _run_e2e_suite,
        "classify": _classify_e2e_suite,
        "description": "Full FileOrganizer run including output writes in temp workspace.",
    },
}


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _detect_hardware_profile() -> dict[str, Any]:
    """Return hardware profile dict with a stable fallback payload."""
    try:
        from file_organizer.core.hardware_profile import detect_hardware

        return detect_hardware().to_dict()
    except (ImportError, ModuleNotFoundError, OSError, RuntimeError):
        return {"error": "Hardware detection unavailable"}


def _check_baseline_profile_compatibility(
    baseline: dict[str, Any],
    *,
    suite: str,
    console: Any,
    json_output: bool,
) -> str | None:
    """Validate runner-profile compatibility between current and baseline output.

    Returns a warning string when the baseline declares a different profile
    version, otherwise ``None``.
    """
    baseline_profile = baseline.get("runner_profile_version")
    if baseline_profile is None or baseline_profile == _RUNNER_PROFILE_VERSION:
        return None

    warning = (
        "Baseline runner profile mismatch "
        f"(baseline={baseline_profile}, current={_RUNNER_PROFILE_VERSION}, suite={suite}). "
        "Comparisons may mix non-equivalent benchmark semantics."
    )
    if not json_output:
        console.print(f"[yellow]{warning}[/yellow]")
    return warning


def _check_baseline_smoke_compatibility(
    baseline: dict[str, Any],
    *,
    transcribe_smoke: bool,
    console: Any,
    json_output: bool,
) -> str | None:
    """Validate that current and baseline runs used the same smoke mode.

    A smoke run adds an ``AudioModel.generate()`` call per iteration and
    skews the per-iteration timings. Comparing a smoke run against a
    non-smoke baseline (or vice versa) yields misleading regression signals
    for non-equivalent workloads.

    Returns a warning string when the baseline's ``transcribe_smoke`` flag
    differs from the current run, otherwise ``None``. Treats a missing
    field on the baseline as ``False`` since older baselines predate the
    flag. A non-boolean value (e.g. the string ``"false"`` from a hand-
    edited or malformed baseline) is reported via a malformed-field warning
    instead of being coerced — ``bool("false")`` is ``True``, which would
    silently invert the mismatch signal.
    """
    raw = baseline.get("transcribe_smoke")
    if raw is None:
        baseline_smoke = False
    elif isinstance(raw, bool):
        baseline_smoke = raw
    else:
        warning = (
            "Baseline transcribe_smoke field is not a boolean "
            f"(got {type(raw).__name__}={raw!r}); treating as missing. "
            "The baseline file may be hand-edited or corrupted; "
            "smoke-mode mismatch detection is unreliable for this comparison."
        )
        if not json_output:
            console.print(f"[yellow]{warning}[/yellow]")
        return warning

    if baseline_smoke == transcribe_smoke:
        return None

    warning = (
        "Baseline smoke-mode mismatch "
        f"(baseline transcribe_smoke={baseline_smoke}, current={transcribe_smoke}). "
        "Smoke runs add an AudioModel.generate() call per iteration; the "
        "comparison may show misleading regressions or improvements."
    )
    if not json_output:
        console.print(f"[yellow]{warning}[/yellow]")
    return warning


def _execute_suite_iteration(
    *,
    runner: Callable[[list[Path]], _SuiteIterationOutcome],
    classifier: Callable[[list[Path], _SuiteIterationOutcome], _SuiteExecutionClassification],
    files: list[Path],
    suite: str,
    console: Any,
) -> tuple[float, int, _SuiteExecutionClassification]:
    """Run one suite iteration and validate returned processed count."""
    start = time.monotonic()
    try:
        outcome = runner(files)
    except Exception as e:
        console.print(f"[red]Benchmark suite '{suite}' failed: {e}[/red]")
        raise typer.Exit(code=1) from e
    if outcome.processed_count < 0:
        console.print(
            f"[red]Benchmark suite '{suite}' returned invalid processed count: "
            f"{outcome.processed_count}[/red]"
        )
        raise typer.Exit(code=1)
    elapsed_ms = (time.monotonic() - start) * 1000
    try:
        classification = classifier(files, outcome)
    except Exception as e:
        console.print(f"[red]Benchmark suite '{suite}' classification failed: {e}[/red]")
        raise typer.Exit(code=1) from e
    return elapsed_ms, outcome.processed_count, classification


def _summarize_suite_classifications(
    classifications: list[_SuiteExecutionClassification],
    *,
    warmup: int,
    requested_suite: str,
) -> tuple[str, bool, list[str]]:
    """Return effective suite, degraded flag, and unique degradation reasons."""
    measured = classifications[warmup:]
    degradation_reasons = sorted(
        {
            reason
            for classification in measured
            if classification.degraded
            for reason in classification.degradation_reasons
        }
    )
    degraded = any(classification.degraded for classification in measured)
    effective_suite_names = {classification.effective_suite for classification in measured}
    effective_suite = (
        measured[-1].effective_suite
        if len(effective_suite_names) == 1 and measured
        else "mixed"
        if measured
        else requested_suite
    )
    return effective_suite, degraded, degradation_reasons


def _print_table(
    console: Any, suite: str, warmup: int, stats: BenchmarkStats, file_count: int
) -> None:
    """Print benchmark results as a Rich table."""
    from rich.table import Table as RichTable

    table = RichTable(title=f"Benchmark Results (suite={suite})")
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


def _maybe_attach_comparison_output(
    *,
    output: dict[str, Any],
    compare_path: Path | None,
    suite: str,
    transcribe_smoke: bool,
    console: Any,
    json_output: bool,
) -> dict[str, Any]:
    """Attach baseline comparison fields when ``compare_path`` is provided."""
    if compare_path is None:
        return output
    try:
        baseline = json.loads(compare_path.read_text())
    except Exception as e:
        console.print(f"[red]Failed to read baseline: {e}[/red]")
        raise typer.Exit(code=1) from e

    profile_warning = _check_baseline_profile_compatibility(
        baseline,
        suite=suite,
        console=console,
        json_output=json_output,
    )
    smoke_warning = _check_baseline_smoke_compatibility(
        baseline,
        transcribe_smoke=transcribe_smoke,
        console=console,
        json_output=json_output,
    )
    comp = compare_results(output, baseline)
    output["comparison"] = comp
    if profile_warning is not None:
        output["comparison_profile_warning"] = profile_warning
    if smoke_warning is not None:
        output["comparison_smoke_warning"] = smoke_warning
    return output


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------


def _validate_compare_path(compare_path: Path | None) -> Path | None:
    """Resolve ``--compare`` and reject directories at the CLI boundary.

    ``resolve_cli_path(must_be_dir=False)`` accepts any existing FS object;
    an explicit ``is_file()`` guard catches directories so they fail with
    ``typer.BadParameter`` (exit 2) instead of later at ``read_text()``
    with ``IsADirectoryError`` (exit 1). Extracted to keep ``run()``'s
    cyclomatic complexity within the C901 limit.
    """
    if compare_path is None:
        return None
    resolved = resolve_cli_path(compare_path, must_exist=True, must_be_dir=False)
    if not resolved.is_file():
        raise typer.BadParameter(f"Baseline compare path is not a regular file: {resolved!s}")
    return resolved


@benchmark_app.command()
def run(
    input_path: Annotated[
        Path,
        typer.Argument(help="Path to files to benchmark."),
    ] = Path("tests/fixtures/"),
    iterations: Annotated[
        int,
        typer.Option(
            "--iterations",
            "-i",
            help="Number of measured iterations to run (excluding warmup). Total runs = warmup + iterations.",
            min=1,
        ),
    ] = 10,
    warmup: Annotated[
        int,
        typer.Option(
            "--warmup",
            "-w",
            help="Warmup iterations excluded from statistics.",
            min=0,
        ),
    ] = 3,
    suite: Annotated[
        str,
        typer.Option(
            "--suite",
            "-s",
            help=(
                "Benchmark suite to run (io, text, vision, audio, pipeline, e2e). "
                "Each suite executes a dedicated runner."
            ),
        ),
    ] = "io",
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output results as JSON."),
    ] = False,
    compare_path: Annotated[  # noqa: cli-path-validation
        Path | None,
        typer.Option("--compare", help="Path to baseline JSON file for regression comparison."),
    ] = None,
    transcribe_smoke: Annotated[
        bool,
        typer.Option(
            "--transcribe-smoke",
            help=(
                "Run AudioModel.generate() on one candidate file as an "
                "end-to-end smoke test. Only meaningful with --suite audio. "
                "Requires the [audio] extra. Off by default to keep "
                "benchmark runs fast."
            ),
        ),
    ] = False,
) -> None:
    """Run a performance benchmark with statistical output.

    Measures timing statistics across multiple iterations with warmup
    exclusion.  Supports suite selection and baseline comparison.
    """
    from rich.console import Console

    console = Console()
    # A.cli: resolve + validate the input tree. `--compare` points at a
    # JSON baseline (a file, not a dir); validate it separately via
    # _validate_compare_path so run()'s complexity stays within C901.
    input_path = resolve_cli_path(input_path, must_exist=True, must_be_dir=True)
    compare_path = _validate_compare_path(compare_path)

    # Collect files (capped to prevent OOM on pathologically large trees)
    try:
        files: list[Path] = []
        for f in safe_walk(input_path):
            files.append(f)
            if len(files) >= _MAX_BENCHMARK_FILES:
                logger.warning(
                    "Benchmark corpus capped at %d files for %s",
                    _MAX_BENCHMARK_FILES,
                    input_path,
                )
                break
    except Exception as e:
        console.print(f"[red]Error reading files: {e}[/red]")
        raise typer.Exit(code=1) from e

    # Select suite runner
    suite_spec = _SUITE_RUNNERS.get(suite)
    if suite_spec is None:
        console.print(f"[red]Unknown suite: {suite}[/red]")
        raise typer.Exit(code=1)
    runner = suite_spec["run"]
    classifier = suite_spec["classify"]
    runner = _bind_transcribe_smoke(runner, suite=suite, transcribe_smoke=transcribe_smoke)
    # Block the empty-input and no-audio-candidates paths from short-circuiting
    # past the smoke-failure exit guard, which would otherwise cause
    # `--transcribe-smoke` to exit 0 without verifying anything.
    _validate_transcribe_smoke_preconditions(files, transcribe_smoke=transcribe_smoke)

    if not files:
        if json_output:
            empty_outcome = _SuiteIterationOutcome(processed_count=0)
            classification = classifier([], empty_outcome)
            empty_output: dict[str, Any] = {
                "suite": suite,
                "effective_suite": classification.effective_suite,
                "degraded": classification.degraded,
                "degradation_reasons": sorted(set(classification.degradation_reasons)),
                "runner_profile_version": _RUNNER_PROFILE_VERSION,
                "transcribe_smoke": transcribe_smoke,
                "files_count": 0,
                "hardware_profile": _detect_hardware_profile(),
                "results": compute_stats([], 0),
            }
            validate_benchmark_payload(empty_output)
            empty_output = _maybe_attach_comparison_output(
                output=empty_output,
                compare_path=compare_path,
                suite=suite,
                transcribe_smoke=transcribe_smoke,
                console=console,
                json_output=json_output,
            )
            console.print(json.dumps(empty_output, indent=2))
        else:
            console.print("[yellow]No files found in the specified path.[/yellow]")
        return

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
    processed_counts: list[int] = []
    classifications: list[_SuiteExecutionClassification] = []
    for i in range(total_iterations):
        if not json_output:
            label = "warmup" if i < warmup else f"{i - warmup + 1}/{iterations}"
            console.print(f"[dim]Iteration {i + 1}/{total_iterations} ({label})...[/dim]")

        elapsed_ms, processed_count, classification = _execute_suite_iteration(
            runner=runner,
            classifier=classifier,
            files=files,
            suite=suite,
            console=console,
        )
        all_times_ms.append(elapsed_ms)
        processed_counts.append(processed_count)
        classifications.append(classification)

    # Exclude warmup
    measured = all_times_ms[warmup:]
    actual_processed_count = _resolve_processed_count(
        processed_counts,
        warmup,
        suite=suite,
        console=console,
    )
    effective_suite, degraded, degradation_reasons = _summarize_suite_classifications(
        classifications,
        warmup=warmup,
        requested_suite=suite,
    )

    # Statistics
    stats = compute_stats(measured, actual_processed_count)

    # Build output. `transcribe_smoke` is included so `--compare` can avoid
    # mixing smoke and non-smoke baselines (which would otherwise show
    # misleading regressions from the extra AudioModel.generate() call per
    # iteration).
    output: dict[str, Any] = {
        "suite": suite,
        "effective_suite": effective_suite,
        "degraded": degraded,
        "degradation_reasons": degradation_reasons,
        "runner_profile_version": _RUNNER_PROFILE_VERSION,
        "transcribe_smoke": transcribe_smoke,
        "files_count": actual_processed_count,
        "hardware_profile": _detect_hardware_profile(),
        "results": stats,
    }
    validate_benchmark_payload(output)

    output = _maybe_attach_comparison_output(
        output=output,
        compare_path=compare_path,
        suite=suite,
        transcribe_smoke=transcribe_smoke,
        console=console,
        json_output=json_output,
    )

    if json_output:
        # JSON consumers parse the document on stdout; the smoke-failure
        # exit fires after so they still get the full payload (including
        # `degraded` + `degradation_reasons`) before the non-zero exit.
        console.print(json.dumps(output, indent=2))
        _exit_if_transcribe_smoke_failed(console, degradation_reasons, json_output=json_output)
    else:
        if degraded:
            console.print(
                f"[yellow]Degraded suite mode:[/yellow] requested={suite}, "
                f"effective={effective_suite}"
            )
            for reason in degradation_reasons:
                console.print(f"[yellow]- {reason}[/yellow]")
        _print_table(console, suite, warmup, stats, actual_processed_count)
        if "comparison" in output:
            _print_comparison(console, output["comparison"], json_output=False)
        # In human mode, exit BEFORE the success banner — printing
        # "Benchmark completed" and then exiting non-zero produces
        # contradictory output that misleads operators and breaks any
        # automation that scrapes the human log for completion status.
        _exit_if_transcribe_smoke_failed(console, degradation_reasons, json_output=json_output)
        console.print("\n[bold green]Benchmark completed[/bold green]")
