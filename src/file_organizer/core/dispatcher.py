"""File type dispatch and per-type processing pipelines.

Routes files to the appropriate processor (text, image, audio, video)
and handles progress display for each batch.  Extracted from
``organizer.py`` to separate processing logic from orchestration.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger
from rich.console import Console

from file_organizer.core.display import create_progress
from file_organizer.core.types import (
    AUDIO_FALLBACK_FOLDER,
    ERROR_FALLBACK_FOLDER,
    VIDEO_FALLBACK_FOLDER,
)
from file_organizer.parallel.processor import ParallelProcessor
from file_organizer.services import ProcessedFile, ProcessedImage, TextProcessor, VisionProcessor

if TYPE_CHECKING:
    from file_organizer.services.audio.metadata_extractor import AudioMetadataExtractor
    from file_organizer.services.video.metadata_extractor import VideoMetadataExtractor


def process_text_files(
    files: list[Path],
    text_processor: TextProcessor,
    parallel_processor: ParallelProcessor,
    console: Console,
) -> list[ProcessedFile]:
    """Process text files through the AI text model.

    Args:
        files: Text file paths to process.
        text_processor: Initialized text processor.
        parallel_processor: Parallel processing engine.
        console: Rich console for progress output.

    Returns:
        List of processed file results.
    """
    processed: list[ProcessedFile] = []

    with create_progress(console) as progress:
        task = progress.add_task("Processing files...", total=len(files))

        def _process_one(path: Path) -> ProcessedFile:
            return text_processor.process_file(path)

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
) -> list[ProcessedImage]:
    """Process image files through the AI vision model.

    Args:
        files: Image file paths to process.
        vision_processor: Initialized vision processor.
        parallel_processor: Parallel processing engine.
        console: Rich console for progress output.

    Returns:
        List of processed image results.
    """
    processed: list[ProcessedImage] = []

    with create_progress(console) as progress:
        task = progress.add_task("Processing images...", total=len(files))

        def _process_one_image(path: Path) -> ProcessedImage:
            return vision_processor.process_file(path)

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
                logger.error("Failed to process {}: {}", file_result.path, error_msg)
                processed.append(
                    ProcessedImage(
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


def process_audio_files(
    files: list[Path],
    *,
    extractor_cls: type[AudioMetadataExtractor] | None = None,
) -> list[ProcessedFile]:
    """Process audio files using the metadata pipeline (no AI model required).

    Args:
        files: Audio file paths to process.
        extractor_cls: Optional extractor class override so organizer-level
            patch targets continue to intercept metadata extraction in tests.

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
            classification = classifier.classify(metadata)
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
                )
            )
            logger.debug("Audio processed: {} → {}/{}", audio_path.name, folder_name, filename_stem)

        except Exception as exc:
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

        except FileNotFoundError:
            raise
        except Exception as exc:
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
