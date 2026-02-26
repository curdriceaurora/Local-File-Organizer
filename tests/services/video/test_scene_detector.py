"""Tests for video scene detection service.

Covers SceneDetector, DetectionMethod, Scene, SceneDetectionResult, and static helpers.
All external dependencies (cv2, scenedetect) are mocked so tests run without video support.
"""

from __future__ import annotations

import csv
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.services.video.scene_detector import (
    DetectionMethod,
    Scene,
    SceneDetectionResult,
    SceneDetector,
)

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_scene(
    scene_number: int = 1,
    start_time: float = 0.0,
    end_time: float = 5.0,
    start_frame: int = 0,
    end_frame: int = 150,
    duration: float = 5.0,
    score: float = 0.9,
    frame_count: int = 150,
) -> Scene:
    """Create a Scene with sensible defaults."""
    return Scene(
        scene_number=scene_number,
        start_time=start_time,
        end_time=end_time,
        start_frame=start_frame,
        end_frame=end_frame,
        duration=duration,
        score=score,
        frame_count=frame_count,
    )


def _make_result(
    video_path: Path,
    scenes: list[Scene] | None = None,
    fps: float = 30.0,
    total_frames: int = 300,
    total_duration: float = 10.0,
    method: DetectionMethod = DetectionMethod.CONTENT,
) -> SceneDetectionResult:
    """Create a SceneDetectionResult with sensible defaults."""
    return SceneDetectionResult(
        video_path=video_path,
        scenes=scenes or [],
        total_duration=total_duration,
        fps=fps,
        total_frames=total_frames,
        method=method,
    )


# ---------------------------------------------------------------------------
# DetectionMethod enum
# ---------------------------------------------------------------------------


class TestDetectionMethod:
    """Tests for the DetectionMethod enum."""

    def test_values(self) -> None:
        assert DetectionMethod.CONTENT == "content"
        assert DetectionMethod.THRESHOLD == "threshold"
        assert DetectionMethod.ADAPTIVE == "adaptive"
        assert DetectionMethod.HISTOGRAM == "histogram"

    def test_members_count(self) -> None:
        assert len(DetectionMethod) == 4


# ---------------------------------------------------------------------------
# Scene dataclass
# ---------------------------------------------------------------------------


class TestScene:
    """Tests for the Scene dataclass."""

    def test_creation(self) -> None:
        scene = _make_scene()
        assert scene.scene_number == 1
        assert scene.start_time == 0.0
        assert scene.end_time == 5.0
        assert scene.start_frame == 0
        assert scene.end_frame == 150
        assert scene.duration == 5.0
        assert scene.score == 0.9
        assert scene.frame_count == 150


# ---------------------------------------------------------------------------
# SceneDetectionResult dataclass
# ---------------------------------------------------------------------------


class TestSceneDetectionResult:
    """Tests for the SceneDetectionResult dataclass."""

    def test_empty_result(self, tmp_path: Path) -> None:
        result = _make_result(tmp_path / "video.mp4")
        assert result.scenes == []
        assert result.fps == 30.0
        assert result.total_frames == 300
        assert result.total_duration == 10.0
        assert result.method == DetectionMethod.CONTENT
        assert result.parameters == {}

    def test_with_scenes(self, tmp_path: Path) -> None:
        scenes = [_make_scene(1), _make_scene(2, start_time=5.0, end_time=10.0)]
        result = _make_result(tmp_path / "v.mp4", scenes=scenes)
        assert len(result.scenes) == 2

    def test_custom_parameters(self, tmp_path: Path) -> None:
        result = SceneDetectionResult(
            video_path=tmp_path / "v.mp4",
            scenes=[],
            total_duration=10.0,
            fps=24.0,
            total_frames=240,
            method=DetectionMethod.ADAPTIVE,
            parameters={"threshold": 30.0},
        )
        assert result.parameters == {"threshold": 30.0}


# ---------------------------------------------------------------------------
# SceneDetector.__init__ and dependency checks
# ---------------------------------------------------------------------------


class TestSceneDetectorInit:
    """Tests for SceneDetector initialization."""

    @patch("file_organizer.services.video.scene_detector.SceneDetector._check_dependencies")
    def test_defaults(self, mock_deps: MagicMock) -> None:
        detector = SceneDetector()
        assert detector.method == DetectionMethod.CONTENT
        assert detector.threshold == 27.0
        assert detector.min_scene_length == 1.0
        mock_deps.assert_called_once()

    @patch("file_organizer.services.video.scene_detector.SceneDetector._check_dependencies")
    def test_custom_params(self, mock_deps: MagicMock) -> None:
        detector = SceneDetector(
            method=DetectionMethod.THRESHOLD,
            threshold=15.0,
            min_scene_length=2.5,
        )
        assert detector.method == DetectionMethod.THRESHOLD
        assert detector.threshold == 15.0
        assert detector.min_scene_length == 2.5

    def test_check_dependencies_missing_cv2(self) -> None:
        """When cv2 is missing, detector should still initialize."""
        with patch.dict("sys.modules", {"cv2": None}):
            with patch("builtins.__import__", side_effect=_import_side_effect(block={"cv2"})):
                # Should not raise
                detector = SceneDetector.__new__(SceneDetector)
                detector.method = DetectionMethod.CONTENT
                detector.threshold = 27.0
                detector.min_scene_length = 1.0
                detector._check_dependencies()

    def test_check_dependencies_missing_scenedetect(self) -> None:
        """When scenedetect is missing, detector should still initialize."""
        with patch.dict("sys.modules", {"scenedetect": None}):
            with patch(
                "builtins.__import__",
                side_effect=_import_side_effect(block={"scenedetect"}),
            ):
                detector = SceneDetector.__new__(SceneDetector)
                detector.method = DetectionMethod.CONTENT
                detector.threshold = 27.0
                detector.min_scene_length = 1.0
                detector._check_dependencies()


# ---------------------------------------------------------------------------
# detect_scenes
# ---------------------------------------------------------------------------


class TestDetectScenes:
    """Tests for SceneDetector.detect_scenes."""

    @patch("file_organizer.services.video.scene_detector.SceneDetector._check_dependencies")
    def test_file_not_found(self, mock_deps: MagicMock, tmp_path: Path) -> None:
        detector = SceneDetector()
        with pytest.raises(FileNotFoundError, match="Video file not found"):
            detector.detect_scenes(tmp_path / "no_such_video.mp4")

    @patch("file_organizer.services.video.scene_detector.SceneDetector._check_dependencies")
    def test_uses_default_method_and_threshold(self, mock_deps: MagicMock, tmp_path: Path) -> None:
        video = tmp_path / "video.mp4"
        video.write_bytes(b"\x00")

        detector = SceneDetector(method=DetectionMethod.ADAPTIVE, threshold=42.0)

        with patch.object(
            detector, "_detect_with_scenedetect", side_effect=ImportError("no scenedetect")
        ):
            with patch.object(detector, "_detect_with_opencv") as mock_cv:
                mock_cv.return_value = _make_result(video)
                detector.detect_scenes(video)
                # When scenedetect raises ImportError, it falls back to opencv with the threshold
                mock_cv.assert_called_once_with(video, 42.0)

    @patch("file_organizer.services.video.scene_detector.SceneDetector._check_dependencies")
    def test_override_method_and_threshold(self, mock_deps: MagicMock, tmp_path: Path) -> None:
        video = tmp_path / "video.mp4"
        video.write_bytes(b"\x00")

        detector = SceneDetector()
        with patch.object(detector, "_detect_with_scenedetect") as mock_sd:
            mock_sd.return_value = _make_result(video, method=DetectionMethod.THRESHOLD)
            detector.detect_scenes(
                video, method=DetectionMethod.THRESHOLD, threshold=10.0
            )
            mock_sd.assert_called_once_with(video, DetectionMethod.THRESHOLD, 10.0)

    @patch("file_organizer.services.video.scene_detector.SceneDetector._check_dependencies")
    def test_falls_back_to_opencv_on_import_error(
        self, mock_deps: MagicMock, tmp_path: Path
    ) -> None:
        video = tmp_path / "video.mp4"
        video.write_bytes(b"\x00")

        detector = SceneDetector()
        with patch.object(
            detector, "_detect_with_scenedetect", side_effect=ImportError("not installed")
        ):
            with patch.object(detector, "_detect_with_opencv") as mock_cv:
                mock_cv.return_value = _make_result(video)
                detector.detect_scenes(video)
                mock_cv.assert_called_once()

    @patch("file_organizer.services.video.scene_detector.SceneDetector._check_dependencies")
    def test_accepts_string_path(self, mock_deps: MagicMock, tmp_path: Path) -> None:
        video = tmp_path / "video.mp4"
        video.write_bytes(b"\x00")

        detector = SceneDetector()
        with patch.object(
            detector, "_detect_with_scenedetect", side_effect=ImportError
        ):
            with patch.object(detector, "_detect_with_opencv") as mock_cv:
                mock_cv.return_value = _make_result(video)
                detector.detect_scenes(str(video))
                mock_cv.assert_called_once()


# ---------------------------------------------------------------------------
# _detect_with_scenedetect
# ---------------------------------------------------------------------------


class TestDetectWithScenedetect:
    """Tests for the scenedetect backend."""

    @patch("file_organizer.services.video.scene_detector.SceneDetector._check_dependencies")
    def test_content_detector(self, mock_deps: MagicMock, tmp_path: Path) -> None:
        video = tmp_path / "video.mp4"
        video.write_bytes(b"\x00")

        detector = SceneDetector()
        result = _run_scenedetect_mock(detector, video, DetectionMethod.CONTENT, 27.0)
        assert result.method == DetectionMethod.CONTENT
        assert len(result.scenes) == 1

    @patch("file_organizer.services.video.scene_detector.SceneDetector._check_dependencies")
    def test_threshold_detector(self, mock_deps: MagicMock, tmp_path: Path) -> None:
        video = tmp_path / "v.mp4"
        video.write_bytes(b"\x00")
        detector = SceneDetector()
        result = _run_scenedetect_mock(detector, video, DetectionMethod.THRESHOLD, 20.0)
        assert result.method == DetectionMethod.THRESHOLD

    @patch("file_organizer.services.video.scene_detector.SceneDetector._check_dependencies")
    def test_adaptive_detector(self, mock_deps: MagicMock, tmp_path: Path) -> None:
        video = tmp_path / "v.mp4"
        video.write_bytes(b"\x00")
        detector = SceneDetector()
        result = _run_scenedetect_mock(detector, video, DetectionMethod.ADAPTIVE, 27.0)
        assert result.method == DetectionMethod.ADAPTIVE

    @patch("file_organizer.services.video.scene_detector.SceneDetector._check_dependencies")
    def test_histogram_defaults_to_content(self, mock_deps: MagicMock, tmp_path: Path) -> None:
        video = tmp_path / "v.mp4"
        video.write_bytes(b"\x00")
        detector = SceneDetector()
        result = _run_scenedetect_mock(detector, video, DetectionMethod.HISTOGRAM, 27.0)
        # HISTOGRAM is not explicitly handled, so the default branch adds ContentDetector
        assert result.method == DetectionMethod.HISTOGRAM


# ---------------------------------------------------------------------------
# _detect_with_opencv
# ---------------------------------------------------------------------------


class TestDetectWithOpencv:
    """Tests for the OpenCV fallback backend."""

    @patch("file_organizer.services.video.scene_detector.SceneDetector._check_dependencies")
    def test_basic_detection(self, mock_deps: MagicMock, tmp_path: Path) -> None:
        video = tmp_path / "v.mp4"
        video.write_bytes(b"\x00")

        detector = SceneDetector(min_scene_length=0.0)
        result = _run_opencv_mock(detector, video, threshold=10.0, scene_changes=[5])
        assert result.method == DetectionMethod.THRESHOLD
        assert len(result.scenes) >= 1

    @patch("file_organizer.services.video.scene_detector.SceneDetector._check_dependencies")
    def test_no_scene_changes(self, mock_deps: MagicMock, tmp_path: Path) -> None:
        video = tmp_path / "v.mp4"
        video.write_bytes(b"\x00")

        detector = SceneDetector(min_scene_length=0.0)
        result = _run_opencv_mock(detector, video, threshold=10.0, scene_changes=[])
        # Should still have the single initial scene
        assert len(result.scenes) == 1

    @patch("file_organizer.services.video.scene_detector.SceneDetector._check_dependencies")
    def test_opencv_video_open_failure(self, mock_deps: MagicMock, tmp_path: Path) -> None:
        video = tmp_path / "v.mp4"
        video.write_bytes(b"\x00")

        detector = SceneDetector()
        mock_cv2 = MagicMock()
        cap = MagicMock()
        cap.isOpened.return_value = False
        mock_cv2.VideoCapture.return_value = cap

        with patch.dict("sys.modules", {"cv2": mock_cv2, "numpy": MagicMock()}):
            with pytest.raises(ValueError, match="Failed to open video"):
                detector._detect_with_opencv(video, 27.0)


# ---------------------------------------------------------------------------
# detect_scenes_batch
# ---------------------------------------------------------------------------


class TestDetectScenesBatch:
    """Tests for batch scene detection."""

    @patch("file_organizer.services.video.scene_detector.SceneDetector._check_dependencies")
    def test_batch_success(self, mock_deps: MagicMock, tmp_path: Path) -> None:
        v1 = tmp_path / "v1.mp4"
        v2 = tmp_path / "v2.mp4"
        v1.write_bytes(b"\x00")
        v2.write_bytes(b"\x00")

        detector = SceneDetector()
        with patch.object(detector, "detect_scenes") as mock_detect:
            mock_detect.side_effect = [
                _make_result(v1),
                _make_result(v2),
            ]
            results = detector.detect_scenes_batch([v1, v2])
            assert len(results) == 2

    @patch("file_organizer.services.video.scene_detector.SceneDetector._check_dependencies")
    def test_batch_partial_failure(self, mock_deps: MagicMock, tmp_path: Path) -> None:
        v1 = tmp_path / "v1.mp4"
        v2 = tmp_path / "v2.mp4"
        v1.write_bytes(b"\x00")
        v2.write_bytes(b"\x00")

        detector = SceneDetector()
        with patch.object(detector, "detect_scenes") as mock_detect:
            mock_detect.side_effect = [
                _make_result(v1),
                FileNotFoundError("gone"),
            ]
            results = detector.detect_scenes_batch([v1, v2])
            assert len(results) == 1

    @patch("file_organizer.services.video.scene_detector.SceneDetector._check_dependencies")
    def test_batch_empty(self, mock_deps: MagicMock) -> None:
        detector = SceneDetector()
        results = detector.detect_scenes_batch([])
        assert results == []

    @patch("file_organizer.services.video.scene_detector.SceneDetector._check_dependencies")
    def test_batch_with_method_override(self, mock_deps: MagicMock, tmp_path: Path) -> None:
        v1 = tmp_path / "v1.mp4"
        v1.write_bytes(b"\x00")

        detector = SceneDetector()
        with patch.object(detector, "detect_scenes") as mock_detect:
            mock_detect.return_value = _make_result(v1)
            detector.detect_scenes_batch([v1], method=DetectionMethod.THRESHOLD)
            mock_detect.assert_called_once_with(v1, DetectionMethod.THRESHOLD)


# ---------------------------------------------------------------------------
# save_scene_list
# ---------------------------------------------------------------------------


class TestSaveSceneList:
    """Tests for saving scene lists to CSV."""

    def test_save_creates_csv(self, tmp_path: Path) -> None:
        scenes = [
            _make_scene(1, 0.0, 5.0, 0, 150, 5.0, 0.9, 150),
            _make_scene(2, 5.0, 10.0, 150, 300, 5.0, 0.8, 150),
        ]
        result = _make_result(tmp_path / "v.mp4", scenes=scenes)
        output = tmp_path / "scenes.csv"

        SceneDetector.save_scene_list(result, output)

        assert output.exists()
        with open(output) as f:
            reader = csv.reader(f)
            rows = list(reader)
        # Header + 2 data rows
        assert len(rows) == 3
        assert rows[0][0] == "Scene"
        assert rows[1][0] == "1"
        assert rows[2][0] == "2"

    def test_save_empty_scenes(self, tmp_path: Path) -> None:
        result = _make_result(tmp_path / "v.mp4", scenes=[])
        output = tmp_path / "scenes.csv"
        SceneDetector.save_scene_list(result, output)
        assert output.exists()
        with open(output) as f:
            reader = csv.reader(f)
            rows = list(reader)
        assert len(rows) == 1  # Header only

    def test_save_accepts_string_path(self, tmp_path: Path) -> None:
        result = _make_result(tmp_path / "v.mp4", scenes=[_make_scene()])
        output = str(tmp_path / "scenes.csv")
        SceneDetector.save_scene_list(result, output)
        assert Path(output).exists()


# ---------------------------------------------------------------------------
# extract_scene_thumbnails
# ---------------------------------------------------------------------------


class TestExtractSceneThumbnails:
    """Tests for thumbnail extraction."""

    def test_extract_thumbnails(self, tmp_path: Path) -> None:
        video = tmp_path / "v.mp4"
        video.write_bytes(b"\x00")
        output_dir = tmp_path / "thumbs"

        scenes = [_make_scene(1, 0.0, 5.0), _make_scene(2, 5.0, 10.0)]
        result = _make_result(video, scenes=scenes)

        mock_cv2 = MagicMock()
        cap = MagicMock()
        mock_cv2.VideoCapture.return_value = cap
        cap.get.return_value = 30.0
        cap.read.return_value = (True, MagicMock())

        with patch.dict("sys.modules", {"cv2": mock_cv2}):
            SceneDetector.extract_scene_thumbnails(video, result, output_dir)

        assert output_dir.exists()
        assert cap.set.call_count == 2  # Seek for each scene
        assert mock_cv2.imwrite.call_count == 2

    def test_extract_thumbnails_read_failure(self, tmp_path: Path) -> None:
        video = tmp_path / "v.mp4"
        video.write_bytes(b"\x00")
        output_dir = tmp_path / "thumbs"

        scenes = [_make_scene(1, 0.0, 5.0)]
        result = _make_result(video, scenes=scenes)

        mock_cv2 = MagicMock()
        cap = MagicMock()
        mock_cv2.VideoCapture.return_value = cap
        cap.get.return_value = 30.0
        cap.read.return_value = (False, None)

        with patch.dict("sys.modules", {"cv2": mock_cv2}):
            SceneDetector.extract_scene_thumbnails(video, result, output_dir)

        # No thumbnails written when read fails
        mock_cv2.imwrite.assert_not_called()

    def test_extract_thumbnails_custom_offset(self, tmp_path: Path) -> None:
        video = tmp_path / "v.mp4"
        video.write_bytes(b"\x00")
        output_dir = tmp_path / "thumbs"

        scenes = [_make_scene(1, 2.0, 7.0)]
        result = _make_result(video, scenes=scenes)

        mock_cv2 = MagicMock()
        cap = MagicMock()
        mock_cv2.VideoCapture.return_value = cap
        cap.get.return_value = 30.0
        cap.read.return_value = (True, MagicMock())
        mock_cv2.CAP_PROP_FPS = 5
        mock_cv2.CAP_PROP_POS_FRAMES = 1

        with patch.dict("sys.modules", {"cv2": mock_cv2}):
            SceneDetector.extract_scene_thumbnails(
                video, result, output_dir, frame_offset=1.0
            )

        # target_time = 2.0 + 1.0 = 3.0, target_frame = 3.0 * 30 = 90
        cap.set.assert_called_once_with(mock_cv2.CAP_PROP_POS_FRAMES, 90)


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def _import_side_effect(block: set[str]):
    """Return a side_effect function for __import__ that blocks certain modules."""
    real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

    def _import(name, *args, **kwargs):
        if name in block:
            raise ImportError(f"Mocked missing: {name}")
        return real_import(name, *args, **kwargs)

    return _import


def _run_scenedetect_mock(
    detector: SceneDetector,
    video_path: Path,
    method: DetectionMethod,
    threshold: float,
) -> SceneDetectionResult:
    """Run _detect_with_scenedetect with a fully mocked scenedetect stack."""
    mock_time = MagicMock()
    mock_time.get_frames.return_value = 0
    mock_time.get_seconds.return_value = 0.0

    mock_end_time = MagicMock()
    mock_end_time.get_frames.return_value = 150
    mock_end_time.get_seconds.return_value = 5.0

    mock_duration = MagicMock()
    mock_duration.get_seconds.return_value = 10.0

    mock_video_manager = MagicMock()
    mock_video_manager.get_framerate.return_value = 30.0
    mock_video_manager.get_frame_number.return_value = 300
    mock_video_manager.get_duration.return_value = (mock_duration,)

    mock_scene_manager = MagicMock()
    mock_scene_manager.get_scene_list.return_value = [(mock_time, mock_end_time)]

    mock_scenedetect = MagicMock()
    mock_scenedetect.VideoManager.return_value = mock_video_manager
    mock_scenedetect.SceneManager.return_value = mock_scene_manager

    mock_detectors = MagicMock()

    with patch.dict(
        "sys.modules",
        {
            "scenedetect": mock_scenedetect,
            "scenedetect.detectors": mock_detectors,
        },
    ):
        return detector._detect_with_scenedetect(video_path, method, threshold)


def _run_opencv_mock(
    detector: SceneDetector,
    video_path: Path,
    threshold: float,
    scene_changes: list[int],
    total_frames: int = 10,
    fps: float = 30.0,
) -> SceneDetectionResult:
    """Run _detect_with_opencv with a fully mocked cv2 stack."""
    import numpy as np

    mock_cv2 = MagicMock()
    mock_cv2.CAP_PROP_FPS = 5
    mock_cv2.CAP_PROP_FRAME_COUNT = 7
    mock_cv2.COLOR_BGR2GRAY = 6

    cap = MagicMock()
    mock_cv2.VideoCapture.return_value = cap
    cap.isOpened.return_value = True

    def _get(prop):
        if prop == mock_cv2.CAP_PROP_FPS:
            return fps
        if prop == mock_cv2.CAP_PROP_FRAME_COUNT:
            return total_frames
        return 0

    cap.get.side_effect = _get

    frame_idx = [0]

    def _read():
        if frame_idx[0] >= total_frames:
            return False, None
        frame_idx[0] += 1
        return True, np.zeros((100, 100, 3), dtype=np.uint8)

    cap.read.side_effect = _read

    # Make cvtColor return frames that trigger scene changes at specified indices
    call_count = [0]

    def _cvtColor(frame, code):
        idx = call_count[0]
        call_count[0] += 1
        if idx in scene_changes:
            # Return a very different frame to trigger scene change
            return np.full((100, 100), 255, dtype=np.uint8)
        return np.zeros((100, 100), dtype=np.uint8)

    mock_cv2.cvtColor.side_effect = _cvtColor
    mock_cv2.absdiff.side_effect = lambda a, b: np.abs(a.astype(float) - b.astype(float)).astype(
        np.uint8
    )

    mock_np = MagicMock()
    mock_np.mean = np.mean

    with patch.dict("sys.modules", {"cv2": mock_cv2}):
        with patch("numpy.mean", np.mean):
            return detector._detect_with_opencv(video_path, threshold)
