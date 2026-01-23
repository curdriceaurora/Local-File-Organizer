"""
Video Scene Detection Service

Detects scene changes in video files using content-aware and threshold-based algorithms.
Supports multiple detection methods and provides detailed scene metadata.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional, Union
import logging

logger = logging.getLogger(__name__)


class DetectionMethod(str, Enum):
    """Scene detection methods."""
    CONTENT = "content"  # Content-aware detection
    THRESHOLD = "threshold"  # Simple threshold-based
    ADAPTIVE = "adaptive"  # Adaptive threshold
    HISTOGRAM = "histogram"  # Histogram comparison


@dataclass
class Scene:
    """Represents a detected scene in a video."""
    scene_number: int
    start_time: float  # seconds
    end_time: float  # seconds
    start_frame: int
    end_frame: int
    duration: float  # seconds
    score: float  # Detection confidence score
    frame_count: int


@dataclass
class SceneDetectionResult:
    """Complete scene detection result."""
    video_path: Path
    scenes: List[Scene]
    total_duration: float  # seconds
    fps: float
    total_frames: int
    method: DetectionMethod
    parameters: dict = field(default_factory=dict)


class SceneDetector:
    """
    Video scene detection service.

    Detects scene changes in video files using various algorithms:
    - Content-aware detection: Analyzes visual content changes
    - Threshold-based: Uses simple threshold on pixel differences
    - Adaptive: Automatically adjusts threshold based on video characteristics
    - Histogram: Compares color histograms between frames

    Features:
    - Multiple detection methods
    - Configurable sensitivity
    - Scene metadata extraction
    - Support for various video formats

    Example:
        >>> detector = SceneDetector()
        >>> result = detector.detect_scenes("video.mp4")
        >>> print(f"Found {len(result.scenes)} scenes")
        >>> for scene in result.scenes:
        ...     print(f"Scene {scene.scene_number}: {scene.start_time:.2f}s - {scene.end_time:.2f}s")
    """

    def __init__(
        self,
        method: DetectionMethod = DetectionMethod.CONTENT,
        threshold: float = 27.0,
        min_scene_length: float = 1.0,  # seconds
    ):
        """
        Initialize scene detector.

        Args:
            method: Detection method to use
            threshold: Detection threshold (lower = more sensitive)
            min_scene_length: Minimum scene length in seconds
        """
        self.method = method
        self.threshold = threshold
        self.min_scene_length = min_scene_length
        self._check_dependencies()

    def _check_dependencies(self):
        """Check if required dependencies are available."""
        try:
            import cv2
        except ImportError:
            logger.warning(
                "opencv-python not found. Install with: pip install opencv-python"
            )

        try:
            import scenedetect
        except ImportError:
            logger.info(
                "scenedetect not found. Some features may be limited. "
                "Install with: pip install scenedetect[opencv]"
            )

    def detect_scenes(
        self,
        video_path: Union[str, Path],
        method: Optional[DetectionMethod] = None,
        threshold: Optional[float] = None,
    ) -> SceneDetectionResult:
        """
        Detect scenes in a video file.

        Args:
            video_path: Path to video file
            method: Detection method (None = use default)
            threshold: Detection threshold (None = use default)

        Returns:
            SceneDetectionResult with detected scenes

        Raises:
            FileNotFoundError: If video file doesn't exist
            ImportError: If required libraries are not available
        """
        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        method = method or self.method
        threshold = threshold if threshold is not None else self.threshold

        logger.info(f"Detecting scenes in {video_path} using {method.value} method")

        # Try scenedetect library first (more sophisticated)
        try:
            return self._detect_with_scenedetect(video_path, method, threshold)
        except ImportError:
            logger.info("scenedetect not available, falling back to OpenCV")
            return self._detect_with_opencv(video_path, threshold)

    def _detect_with_scenedetect(
        self,
        video_path: Path,
        method: DetectionMethod,
        threshold: float,
    ) -> SceneDetectionResult:
        """Detect scenes using PySceneDetect library."""
        from scenedetect import VideoManager, SceneManager
        from scenedetect.detectors import ContentDetector, ThresholdDetector, AdaptiveDetector

        # Create video manager
        video_manager = VideoManager([str(video_path)])
        scene_manager = SceneManager()

        # Add detector based on method
        if method == DetectionMethod.CONTENT:
            scene_manager.add_detector(ContentDetector(threshold=threshold))
        elif method == DetectionMethod.THRESHOLD:
            scene_manager.add_detector(ThresholdDetector(threshold=threshold))
        elif method == DetectionMethod.ADAPTIVE:
            scene_manager.add_detector(AdaptiveDetector())
        else:
            # Default to content detector
            scene_manager.add_detector(ContentDetector(threshold=threshold))

        # Start video manager
        video_manager.set_downscale_factor()
        video_manager.start()

        # Detect scenes
        scene_manager.detect_scenes(frame_source=video_manager)

        # Get scene list
        scene_list = scene_manager.get_scene_list()
        fps = video_manager.get_framerate()
        total_frames = video_manager.get_frame_number(0)
        duration = video_manager.get_duration()[0].get_seconds()

        # Convert to Scene objects
        scenes = []
        for i, (start_time, end_time) in enumerate(scene_list, 1):
            start_frame = start_time.get_frames()
            end_frame = end_time.get_frames()

            scene = Scene(
                scene_number=i,
                start_time=start_time.get_seconds(),
                end_time=end_time.get_seconds(),
                start_frame=start_frame,
                end_frame=end_frame,
                duration=end_time.get_seconds() - start_time.get_seconds(),
                score=1.0,  # SceneDetect doesn't provide scores
                frame_count=end_frame - start_frame,
            )
            scenes.append(scene)

        # Release resources
        video_manager.release()

        result = SceneDetectionResult(
            video_path=video_path,
            scenes=scenes,
            total_duration=duration,
            fps=fps,
            total_frames=total_frames,
            method=method,
            parameters={"threshold": threshold, "min_scene_length": self.min_scene_length},
        )

        logger.info(f"Detected {len(scenes)} scenes using scenedetect")
        return result

    def _detect_with_opencv(
        self,
        video_path: Path,
        threshold: float,
    ) -> SceneDetectionResult:
        """Fallback scene detection using OpenCV."""
        import cv2
        import numpy as np

        # Open video
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise ValueError(f"Failed to open video: {video_path}")

        # Get video properties
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0.0

        scenes = []
        scene_number = 1
        scene_start_frame = 0
        scene_start_time = 0.0
        prev_frame = None

        frame_idx = 0
        min_scene_frames = int(self.min_scene_length * fps)

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # Convert to grayscale for comparison
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            if prev_frame is not None:
                # Calculate frame difference
                diff = cv2.absdiff(gray, prev_frame)
                mean_diff = np.mean(diff)

                # Detect scene change
                if mean_diff > threshold and (frame_idx - scene_start_frame) >= min_scene_frames:
                    # Save previous scene
                    scene_end_frame = frame_idx - 1
                    scene_end_time = scene_end_frame / fps

                    scene = Scene(
                        scene_number=scene_number,
                        start_time=scene_start_time,
                        end_time=scene_end_time,
                        start_frame=scene_start_frame,
                        end_frame=scene_end_frame,
                        duration=scene_end_time - scene_start_time,
                        score=min(mean_diff / threshold, 1.0),
                        frame_count=scene_end_frame - scene_start_frame,
                    )
                    scenes.append(scene)

                    # Start new scene
                    scene_start_frame = frame_idx
                    scene_start_time = frame_idx / fps
                    scene_number += 1

            prev_frame = gray
            frame_idx += 1

        # Add final scene
        if scene_start_frame < total_frames:
            scene_end_frame = total_frames - 1
            scene_end_time = duration

            scene = Scene(
                scene_number=scene_number,
                start_time=scene_start_time,
                end_time=scene_end_time,
                start_frame=scene_start_frame,
                end_frame=scene_end_frame,
                duration=scene_end_time - scene_start_time,
                score=1.0,
                frame_count=scene_end_frame - scene_start_frame,
            )
            scenes.append(scene)

        cap.release()

        result = SceneDetectionResult(
            video_path=video_path,
            scenes=scenes,
            total_duration=duration,
            fps=fps,
            total_frames=total_frames,
            method=DetectionMethod.THRESHOLD,  # OpenCV fallback uses threshold
            parameters={"threshold": threshold, "min_scene_length": self.min_scene_length},
        )

        logger.info(f"Detected {len(scenes)} scenes using OpenCV")
        return result

    def detect_scenes_batch(
        self,
        video_paths: List[Union[str, Path]],
        method: Optional[DetectionMethod] = None,
    ) -> List[SceneDetectionResult]:
        """
        Detect scenes in multiple video files.

        Args:
            video_paths: List of video file paths
            method: Detection method (None = use default)

        Returns:
            List of SceneDetectionResult objects
        """
        results = []
        for video_path in video_paths:
            try:
                result = self.detect_scenes(video_path, method)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to detect scenes in {video_path}: {e}")
                # Continue with other files

        return results

    @staticmethod
    def save_scene_list(result: SceneDetectionResult, output_path: Union[str, Path]):
        """
        Save scene detection result to a file.

        Args:
            result: SceneDetectionResult to save
            output_path: Output file path (CSV format)
        """
        import csv

        output_path = Path(output_path)

        with open(output_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                "Scene", "Start Time", "End Time", "Duration",
                "Start Frame", "End Frame", "Frame Count", "Score"
            ])

            for scene in result.scenes:
                writer.writerow([
                    scene.scene_number,
                    f"{scene.start_time:.2f}",
                    f"{scene.end_time:.2f}",
                    f"{scene.duration:.2f}",
                    scene.start_frame,
                    scene.end_frame,
                    scene.frame_count,
                    f"{scene.score:.3f}",
                ])

        logger.info(f"Scene list saved to: {output_path}")

    @staticmethod
    def extract_scene_thumbnails(
        video_path: Union[str, Path],
        result: SceneDetectionResult,
        output_dir: Union[str, Path],
        frame_offset: float = 0.5,  # Extract frame at 0.5s into scene
    ):
        """
        Extract thumbnail for each detected scene.

        Args:
            video_path: Path to video file
            result: SceneDetectionResult with scenes
            output_dir: Directory to save thumbnails
            frame_offset: Time offset into scene to extract frame (seconds)
        """
        import cv2

        video_path = Path(video_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        cap = cv2.VideoCapture(str(video_path))
        fps = cap.get(cv2.CAP_PROP_FPS)

        for scene in result.scenes:
            # Calculate frame to extract
            target_time = scene.start_time + frame_offset
            target_frame = int(target_time * fps)

            # Seek to frame
            cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            ret, frame = cap.read()

            if ret:
                thumbnail_path = output_dir / f"scene_{scene.scene_number:03d}.jpg"
                cv2.imwrite(str(thumbnail_path), frame)

        cap.release()
        logger.info(f"Extracted {len(result.scenes)} scene thumbnails to {output_dir}")
