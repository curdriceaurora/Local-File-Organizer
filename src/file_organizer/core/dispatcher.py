"""File type dispatch and per-type processing pipelines.

Routes files to the appropriate processor (text, image, audio, video)
and handles progress display for each batch.  Extracted from
``organizer.py`` to separate processing logic from orchestration.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger
from rich.console import Console

from file_organizer.core.display import create_progress
from file_organizer.core.types import (
    AUDIO_FALLBACK_FOLDER,
    ERROR_FALLBACK_FOLDER,
    VIDEO_FALLBACK_FOLDER,
)
from file_organizer.parallel.config import ParallelConfig
from file_organizer.parallel.processor import ParallelProcessor
from file_organizer.services import ProcessedFile, ProcessedImage, TextProcessor, VisionProcessor
from file_organizer.services.vision_fallback import compute_fallback

if TYPE_CHECKING:
    from file_organizer.services.audio.metadata_extractor import (
        AudioMetadata,
        AudioMetadataExtractor,
    )
    from file_organizer.services.video.metadata_extractor import VideoMetadataExtractor


def _maybe_transcribe(
    audio_path: Path,
    *,
    metadata: AudioMetadata,
    transcriber: Any | None,
    max_transcribe_seconds: float | None,
) -> Any | None:
    """Return a transcription *result* when a transcriber is set and within cap.

    The returned object is the classifier-ready ``TranscriptionResult`` (with
    ``.text`` **and** ``.segments``) rather than a bare string, so the
    classifier's segment-based heuristics (speaker count, narrative length —
    see ``AudioClassifier._score_from_transcription``) receive the real
    segments instead of an empty list (#1288).

    - For the repo's ``AudioTranscriber.transcribe() -> TranscriptionResult``
      path, the result is returned as-is (segments intact).
    - For the ``generate(path) -> str`` duck-type fallback (text only), a
      segment-less ``TranscriptionResult`` is synthesized via
      ``_to_transcription_result`` so callers always get a uniform object.

    Returns ``None`` for any of:
    - No transcriber configured (the default; metadata-only categorization).
    - Duration exceeds ``max_transcribe_seconds`` (skip and warn — long files
      would dominate the organize wall-clock time).
    - The transcriber raises a recoverable exception (FileNotFound,
      RuntimeError, ImportError); we degrade to metadata-only categorization
      rather than aborting the entire organize batch on a single bad file.
    - The produced transcript is empty/missing.
    """
    if transcriber is None:
        return None
    # Accept the repo's ``AudioTranscriber`` (``transcribe(path) ->
    # TranscriptionResult``) as well as a ``generate(path) -> str`` duck-type
    # (#1287 review). A transcriber exposing neither is treated as invalid —
    # degrade to metadata-only with a warning rather than raising
    # AttributeError and aborting the per-file dispatcher loop.
    transcribe_fn = getattr(transcriber, "transcribe", None)
    generate_fn = getattr(transcriber, "generate", None)
    if not callable(transcribe_fn) and not callable(generate_fn):
        logger.warning(
            "Invalid transcriber for {} (no transcribe()/generate()); using metadata only.",
            audio_path.name,
        )
        return None
    duration = getattr(metadata, "duration", None)
    if (
        max_transcribe_seconds is not None
        and isinstance(duration, (int, float))
        and duration > max_transcribe_seconds
    ):
        logger.warning(
            "Audio {} exceeds transcribe cap ({:.1f}s > {:.1f}s); using metadata only.",
            audio_path.name,
            float(duration),
            float(max_transcribe_seconds),
        )
        return None
    try:
        if callable(transcribe_fn):
            # Repo's AudioTranscriber returns a TranscriptionResult (.text +
            # .segments). Preserve it whole so the classifier's segment
            # heuristics run. A duck-typed transcribe() may instead return a
            # bare str — synthesize a segment-less result for uniformity.
            result = transcribe_fn(str(audio_path))
            if isinstance(result, str):
                return _to_transcription_result(result, metadata)
            text = getattr(result, "text", None)
            if text is None or not str(text):
                return None
            # Only pass the object straight through if it's classify-ready:
            # AudioClassifier.classify() reads .segments and .duration. A
            # text-bearing object lacking those (e.g. a SimpleNamespace adapter
            # or a partial stub) would raise AttributeError downstream, so wrap
            # its text into a proper segment-less TranscriptionResult instead
            # (#1290 review). Genuine TranscriptionResults keep their segments.
            if hasattr(result, "segments") and hasattr(result, "duration"):
                return result
            return _to_transcription_result(str(text), metadata)
        elif callable(generate_fn):
            # generate() yields text only; wrap into a segment-less result.
            text = generate_fn(str(audio_path))
            if text is None:
                return None
            return _to_transcription_result(str(text), metadata)
        else:  # pragma: no cover - guarded above
            return None
    except (
        FileNotFoundError,
        OSError,
        ValueError,
        RuntimeError,
        ImportError,
        TypeError,
        AttributeError,
    ) as exc:
        # OSError + ValueError cover malformed / unsupported audio
        # (faster-whisper / ctranslate2 surface decode failures via these).
        # Without them the exception escapes to the outer per-file handler
        # and marks the file as failed in AUDIO_FALLBACK_FOLDER, regressing
        # a file that's otherwise classifiable from metadata alone. TypeError /
        # AttributeError cover a malformed or incompatible transcriber adapter
        # (e.g. a stub whose transcribe/generate has the wrong signature) so it
        # degrades to metadata-only instead of aborting the per-file loop. Treat
        # transcription as a best-effort enhancement: degrade to
        # metadata-only categorization on any recoverable failure.
        logger.warning("Audio transcription failed for {}: {}", audio_path.name, exc)
        return None


def _to_transcription_result(transcript: str | None, metadata: AudioMetadata) -> Any:
    """Wrap a plain transcript string for `AudioClassifier.classify(transcription=...)`.

    The classifier's keyword/speaker scoring expects a ``TranscriptionResult``
    dataclass with ``.text``, ``.duration``, and ``.segments``. The transcriber's
    ``generate`` returns a plain ``str``, so we construct a minimal stand-in here.
    ``segments=[]`` disables the segment-based speaker-count heuristic; that's
    intentional — without real word-level timestamps we'd be inventing signal.

    Returns ``None`` when ``transcript`` is missing/empty so the classifier's
    existing ``if transcription is not None`` guard skips the transcription
    phase cleanly.
    """
    if not transcript:
        return None
    from file_organizer.services.audio.transcriber import (
        TranscriptionOptions,
        TranscriptionResult,
    )

    return TranscriptionResult(
        text=transcript,
        segments=[],
        language="",
        language_confidence=0.0,
        duration=getattr(metadata, "duration", 0.0),
        options=TranscriptionOptions(),
    )


def _is_timeout_error(error_msg: str) -> bool:
    """Match the dispatcher's timeout-error sentinel.

    The parallel processor emits ``"Timed out after Xs"`` (see
    ``parallel/processor.py``) when it abandons a long-running task.
    Other errors (read failures, corrupt files) take the regular failure
    path. Match by prefix so the timing-suffix doesn't have to be exact.
    """
    return error_msg.startswith("Timed out after")


def process_text_files(
    files: list[Path],
    text_processor: TextProcessor,
    parallel_processor: ParallelProcessor,
    console: Console,
    *,
    scan_root: Path | None = None,
) -> list[ProcessedFile]:
    """Process text files through the AI text model.

    Args:
        files: Text file paths to process.
        text_processor: Initialized text processor.
        parallel_processor: Parallel processing engine.
        console: Rich console for progress output.
        scan_root: Trusted directory the files were discovered under. When
            supplied it is forwarded to ``process_file`` so content reads go
            through SafeDir anchored traversal (symlink-swap refusal, #264/#286).

    Returns:
        List of processed file results.
    """
    processed: list[ProcessedFile] = []

    with create_progress(console) as progress:
        task = progress.add_task("Processing files...", total=len(files))

        def _process_one(path: Path) -> ProcessedFile:
            """Process a single text file in the dispatcher thread pool."""
            return text_processor.process_file(path, scan_root=scan_root)

        for file_result in parallel_processor.process_batch_iter(files, _process_one):
            if file_result.success:
                result = file_result.result
                processed.append(result)
                if not result.error:
                    progress.update(
                        task,
                        advance=1,
                        description=f"[green]✓[/green] {file_result.path.name}",
                    )
                else:
                    progress.update(
                        task,
                        advance=1,
                        description=f"[red]✗[/red] {file_result.path.name} (Error)",
                    )
            else:
                error_msg = file_result.error or "Unknown error"
                logger.error("Failed to process {}: {}", file_result.path, error_msg)
                processed.append(
                    ProcessedFile(
                        file_path=file_result.path,
                        description="",
                        folder_name=ERROR_FALLBACK_FOLDER,
                        filename=file_result.path.stem,
                        error=error_msg,
                    )
                )
                progress.update(
                    task,
                    advance=1,
                    description=f"[red]✗[/red] {file_result.path.name} (Failed)",
                )

    return processed


def process_image_files(
    files: list[Path],
    vision_processor: VisionProcessor,
    parallel_processor: ParallelProcessor,
    console: Console,
    *,
    context_root: Path | None = None,
) -> list[ProcessedImage]:
    """Process image files through the AI vision model.

    Args:
        files: Image file paths to process.
        vision_processor: Initialized vision processor.
        parallel_processor: Parallel processing engine.
        console: Rich console for progress output.
        context_root: Optional directory path used exclusively for prompt
            context hints (relative path / parent folder).

    Returns:
        List of processed image results.
    """
    processed: list[ProcessedImage] = []
    # #432: track paths whose pool-saturation abort is retryable
    # (never-started; collateral damage) so we can run them sequentially
    # after the parallel pass finishes.
    retry_paths: list[Path] = []

    with create_progress(console) as progress:
        task = progress.add_task("Processing images...", total=len(files))

        def _process_one_image(path: Path) -> ProcessedImage:
            """Process a single image file in the dispatcher thread pool."""
            return vision_processor.process_file(path, context_root=context_root)

        for file_result in parallel_processor.process_batch_iter(files, _process_one_image):
            if file_result.success:
                result = file_result.result
                processed.append(result)
                if not result.error:
                    progress.update(
                        task,
                        advance=1,
                        description=f"[green]✓[/green] {file_result.path.name}",
                    )
                else:
                    progress.update(
                        task,
                        advance=1,
                        description=f"[red]✗[/red] {file_result.path.name} (Error)",
                    )
            else:
                error_msg = file_result.error or "Unknown error"
                # #406: vision timeouts go through the metadata fallback path
                # instead of being dropped into the error bucket. Other
                # failures (read error, corrupt image, …) still error-out.
                if _is_timeout_error(error_msg):
                    fb = compute_fallback(file_result.path)
                    logger.info(
                        "Vision timed out for {}; categorized via {} → {}",
                        file_result.path.name,
                        fb.source,
                        fb.folder,
                    )
                    # Per-source confidence (#409). The vision model never
                    # actually classified this file; we're going off metadata.
                    # EXIF dates are more trustworthy than pure filename
                    # heuristics, so they earn a slightly higher score.
                    _fallback_confidence = 0.5 if fb.source == "fallback_exif" else 0.3
                    processed.append(
                        ProcessedImage(
                            file_path=file_result.path,
                            description="",
                            folder_name=fb.folder,
                            filename=fb.filename,
                            source=fb.source,
                            # Carry the timeout's wall-clock through so the
                            # #410 summary's p95/p99 reflect this image's real
                            # worst-case latency.
                            inference_ms=file_result.duration_ms,
                            confidence=_fallback_confidence,
                            # NB: no `error` field — the file is not a failure
                        )
                    )
                    progress.update(
                        task,
                        advance=1,
                        description=f"[yellow]⚠[/yellow] {file_result.path.name} (fallback)",
                    )
                else:
                    # #432: pool-saturation aborts on never-started tasks
                    # carry ``non_retryable=False``. Queue them for a
                    # post-pass sequential retry instead of recording them as
                    # failures — they never actually ran, so marking them
                    # failed is collateral damage.
                    if (
                        error_msg.startswith("Aborted: worker pool saturated")
                        and not file_result.non_retryable
                    ):
                        retry_paths.append(file_result.path)
                        progress.update(
                            task,
                            advance=1,
                            description=f"[yellow]⟳[/yellow] {file_result.path.name} (will retry)",
                        )
                        continue
                    logger.error("Failed to process {}: {}", file_result.path, error_msg)
                    processed.append(
                        ProcessedImage(
                            file_path=file_result.path,
                            description="",
                            folder_name=ERROR_FALLBACK_FOLDER,
                            filename=file_result.path.stem,
                            error=error_msg,
                            # #409: dispatcher-built failures must surface in
                            # the "Review recommended" section.
                            confidence=0.0,
                        )
                    )
                    progress.update(
                        task,
                        advance=1,
                        description=f"[red]✗[/red] {file_result.path.name} (Failed)",
                    )

    # #432: Sequential retry for pool-saturation collateral. The parallel
    # processor marked these as never-started (non_retryable=False), so rerun
    # them one-at-a-time before reporting failure.
    #
    # The retry must run with ``max_workers=1`` and ``prefetch_depth=0`` —
    # reusing the caller's parallel_processor with its original multi-worker
    # config can re-saturate if a retried file hangs again. The single-worker
    # config gives deterministic degraded-mode recovery: each retry runs
    # alone, and a still-hung backend produces a clean per-file timeout
    # instead of cascade-failing other retry candidates.
    #
    # We inherit the operator-tunable ``timeout_per_file`` from the caller's
    # config so ``--timeout-per-file`` (#396) still applies.
    if retry_paths:
        logger.warning(
            "Pool aborted on hung tasks; retrying {} untried image(s) sequentially.",
            len(retry_paths),
        )

        retry_config = ParallelConfig(
            max_workers=1,
            prefetch_depth=0,
            timeout_per_file=parallel_processor.config.timeout_per_file,
            retry_count=0,  # no second-level retry
        )
        retry_processor = ParallelProcessor(config=retry_config)

        def _retry_one_image(path: Path) -> ProcessedImage:
            return vision_processor.process_file(path, context_root=context_root)

        for retry_result in retry_processor.process_batch_iter(retry_paths, _retry_one_image):
            if retry_result.success:
                processed.append(retry_result.result)
                continue
            # Retry also failed (timeout, vision error, …). Record as a
            # genuine failure now — there's no second-level retry.
            retry_err = retry_result.error or "Unknown error"
            # A timeout, OR a saturation abort on a still-never-started task
            # (the previous retry's thread is still hung on the single worker,
            # so this candidate never ran), both mean the vision model never
            # classified this file. With no second-level retry, degrade to
            # metadata fallback rather than the error folder — otherwise one
            # hung retry would cascade the remaining never-run candidates into
            # failures, reintroducing the very cascade this path prevents
            # (#1287 review).
            never_ran_saturation = (
                retry_err.startswith("Aborted: worker pool saturated")
                and not retry_result.non_retryable
            )
            if _is_timeout_error(retry_err) or never_ran_saturation:
                fb = compute_fallback(retry_result.path)
                _fallback_confidence = 0.5 if fb.source == "fallback_exif" else 0.3
                processed.append(
                    ProcessedImage(
                        file_path=retry_result.path,
                        description="",
                        folder_name=fb.folder,
                        filename=fb.filename,
                        source=fb.source,
                        inference_ms=retry_result.duration_ms,
                        confidence=_fallback_confidence,
                    )
                )
                continue
            logger.error("Sequential retry failed for {}: {}", retry_result.path, retry_err)
            processed.append(
                ProcessedImage(
                    file_path=retry_result.path,
                    description="",
                    folder_name=ERROR_FALLBACK_FOLDER,
                    filename=retry_result.path.stem,
                    error=retry_err,
                    confidence=0.0,
                )
            )

    return processed


def process_audio_files(
    files: list[Path],
    *,
    extractor_cls: type[AudioMetadataExtractor] | None = None,
    transcriber: Any | None = None,
    max_transcribe_seconds: float | None = None,
) -> list[ProcessedFile]:
    """Process audio files using the metadata pipeline (no AI model required).

    Args:
        files: Audio file paths to process.
        extractor_cls: Optional extractor class override so organizer-level
            patch targets continue to intercept metadata extraction in tests.
        transcriber: Optional transcriber object exposing
            ``generate(audio_path: str) -> str`` (typically ``AudioModel``).
            When provided, each file within the duration cap is transcribed
            and the result attached to ``ProcessedFile.transcript`` for the
            organizer's text-categorization path. ``None`` preserves the
            metadata-only behavior. Transcription is best-effort: a recoverable
            failure degrades to metadata-only categorization rather than
            failing the file (anti-cascade audio path).
        max_transcribe_seconds: Per-file duration cap; files longer than this
            skip transcription and fall back to metadata-only categorization.
            ``None`` (the default at this layer) means no cap — the
            CLI/organizer layer applies its policy default and threads it down.

    Returns:
        List of processed file results.
    """
    from file_organizer.services.audio.classifier import AudioClassifier
    from file_organizer.services.audio.metadata_extractor import AudioMetadataExtractor
    from file_organizer.services.audio.organizer import AudioOrganizer

    extractor_type = extractor_cls or AudioMetadataExtractor
    extractor = extractor_type()
    classifier = AudioClassifier()
    organizer = AudioOrganizer()
    processed: list[ProcessedFile] = []

    for audio_path in files:
        try:
            metadata = extractor.extract(audio_path)

            # Transcribe FIRST so the result can influence classification.
            # Otherwise the user pays transcription cost and gets the same
            # metadata-only folder routing — defeating the transcribe path.
            #
            # _maybe_transcribe now returns the full TranscriptionResult (with
            # .segments intact) so the classifier's segment-based heuristics run
            # (#1288). The ProcessedFile.transcript field stays a plain str, so
            # we project ``.text`` off the result for storage while passing the
            # whole object to classify().
            transcription = _maybe_transcribe(
                audio_path,
                metadata=metadata,
                transcriber=transcriber,
                max_transcribe_seconds=max_transcribe_seconds,
            )
            transcript = getattr(transcription, "text", None) if transcription is not None else None
            classification = classifier.classify(metadata, transcription=transcription)
            dest_path = organizer.generate_path(classification.audio_type, metadata)

            folder_name = dest_path.parent.as_posix()
            filename_stem = dest_path.stem

            parts = [classification.audio_type.value.capitalize()]
            if metadata.artist:
                parts.append(metadata.artist)
            if metadata.title:
                parts.append(metadata.title)
            description = (
                ": ".join(parts[:1]) + " " + " - ".join(parts[1:]) if len(parts) > 1 else parts[0]
            )

            processed.append(
                ProcessedFile(
                    file_path=audio_path,
                    description=description,
                    folder_name=folder_name,
                    filename=filename_stem,
                    error=None,
                    transcript=transcript,
                )
            )
            logger.debug("Audio processed: {} → {}/{}", audio_path.name, folder_name, filename_stem)

        except (OSError, ValueError, KeyError, RuntimeError, ImportError) as exc:
            logger.warning("Audio metadata extraction failed for {}: {}", audio_path.name, exc)
            processed.append(
                ProcessedFile(
                    file_path=audio_path,
                    description="",
                    folder_name=AUDIO_FALLBACK_FOLDER,
                    filename=audio_path.stem,
                    error=str(exc),
                )
            )

    return processed


def process_video_files(
    files: list[Path],
    *,
    extractor_cls: type[VideoMetadataExtractor] | None = None,
) -> list[ProcessedFile]:
    """Process video files using the metadata pipeline (no AI model required).

    Args:
        files: Video file paths to process.
        extractor_cls: Optional extractor class override so organizer-level
            patch targets continue to intercept metadata extraction in tests.

    Returns:
        List of processed file results.
    """
    from file_organizer.services.video.metadata_extractor import VideoMetadataExtractor
    from file_organizer.services.video.organizer import VideoOrganizer

    extractor_type = extractor_cls or VideoMetadataExtractor
    extractor = extractor_type()
    organizer = VideoOrganizer()
    processed: list[ProcessedFile] = []

    for video_path in files:
        try:
            metadata = extractor.extract(video_path)
            folder_name, filename_stem = organizer.generate_path(metadata)
            description = organizer.generate_description(metadata)

            processed.append(
                ProcessedFile(
                    file_path=video_path,
                    description=description,
                    folder_name=folder_name,
                    filename=filename_stem,
                    error=None,
                )
            )
            logger.debug("Video processed: {} → {}/{}", video_path.name, folder_name, filename_stem)

        except FileNotFoundError as exc:
            logger.warning("Video file not found: {}: {}", video_path.name, exc)
            processed.append(
                ProcessedFile(
                    file_path=video_path,
                    description="",
                    folder_name=VIDEO_FALLBACK_FOLDER,
                    filename=video_path.stem,
                    error=str(exc),
                )
            )
        except (OSError, ValueError, KeyError, RuntimeError) as exc:
            logger.warning("Video metadata extraction failed for {}: {}", video_path.name, exc)
            processed.append(
                ProcessedFile(
                    file_path=video_path,
                    description="",
                    folder_name=VIDEO_FALLBACK_FOLDER,
                    filename=video_path.stem,
                    error=str(exc),
                )
            )

    return processed
