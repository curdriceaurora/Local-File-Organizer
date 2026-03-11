from unittest.mock import MagicMock, patch

import pytest

from file_organizer.services.video.scene_detector import (
    DetectionMethod,
    Scene,
    SceneDetectionResult,
    SceneDetector,
)


@pytest.fixture
def mock_video_path(tmp_path):
    video = tmp_path / "test_video.mp4"
    video.write_bytes(b"dummy video data")
    return video


class TestSceneDetector:
    def test_init_defaults(self):
        detector = SceneDetector()
        assert detector.method == DetectionMethod.CONTENT
        assert detector.threshold == 27.0
        assert detector.min_scene_length == 1.0

    def test_detect_scenes_file_not_found(self):
        detector = SceneDetector()
        with pytest.raises(FileNotFoundError):
            detector.detect_scenes("non_existent_file.mp4")

    @patch("file_organizer.services.video.scene_detector.SceneDetector._detect_with_scenedetect")
    def test_detect_scenes_uses_scenedetect(self, mock_scenedetect, mock_video_path):
        detector = SceneDetector()
        mock_result = MagicMock(spec=SceneDetectionResult)
        mock_scenedetect.return_value = mock_result

        result = detector.detect_scenes(mock_video_path)
        assert result is mock_result
        mock_scenedetect.assert_called_once_with(mock_video_path, DetectionMethod.CONTENT, 27.0)

    @patch("file_organizer.services.video.scene_detector.SceneDetector._detect_with_opencv")
    def test_detect_scenes_fallback_to_opencv(self, mock_opencv, mock_video_path):
        detector = SceneDetector()
        mock_result = MagicMock(spec=SceneDetectionResult)
        mock_opencv.return_value = mock_result

        # Simulate scenedetect not being available
        with patch.dict("sys.modules", {"scenedetect": None}):
            result = detector.detect_scenes(mock_video_path)

        assert result is mock_result
        mock_opencv.assert_called_once_with(mock_video_path, 27.0)

    @patch("file_organizer.services.video.scene_detector.SceneDetector.detect_scenes")
    def test_detect_scenes_batch(self, mock_detect, mock_video_path):
        detector = SceneDetector()
        mock_result = MagicMock(spec=SceneDetectionResult)
        mock_detect.return_value = mock_result

        results = detector.detect_scenes_batch([mock_video_path, "missing.mp4"])
        # If second file raises exception, it should still return the first result
        assert len(results) == 2

    @patch("file_organizer.services.video.scene_detector.SceneDetector.detect_scenes")
    def test_detect_scenes_batch_skip_errors(self, mock_detect, mock_video_path):
        detector = SceneDetector()
        mock_result = MagicMock(spec=SceneDetectionResult)

        # Make the second call raise an exception
        mock_detect.side_effect = [mock_result, Exception("Test Error")]

        results = detector.detect_scenes_batch([mock_video_path, mock_video_path])
        assert len(results) == 1
        assert results[0] is mock_result

    @patch.dict("sys.modules", {"scenedetect": MagicMock(), "scenedetect.detectors": MagicMock()})
    def test_internal_detect_with_scenedetect(self, mock_video_path):
        import sys

        mock_sm = sys.modules["scenedetect"].SceneManager.return_value
        mock_vm = sys.modules["scenedetect"].VideoManager.return_value
        mock_vm.get_framerate.return_value = 30.0
        mock_vm.get_frame_number.return_value = 150
        mock_time = MagicMock()
        mock_time.get_seconds.return_value = 5.0
        mock_vm.get_duration.return_value = [mock_time]

        mock_start = MagicMock()
        mock_start.get_seconds.return_value = 0.0
        mock_start.get_frames.return_value = 0
        mock_end = MagicMock()
        mock_end.get_seconds.return_value = 5.0
        mock_end.get_frames.return_value = 150
        mock_sm.get_scene_list.return_value = [(mock_start, mock_end)]

        detector = SceneDetector()
        result = detector._detect_with_scenedetect(mock_video_path, DetectionMethod.CONTENT, 27.0)

        assert len(result.scenes) == 1
        assert result.scenes[0].duration == 5.0
        mock_vm.start.assert_called_once()
        mock_sm.detect_scenes.assert_called_once_with(frame_source=mock_vm)

    @patch.dict("sys.modules", {"cv2": MagicMock(), "numpy": MagicMock()})
    def test_internal_detect_with_opencv(self, mock_video_path):
        import sys

        mock_cv2 = sys.modules["cv2"]
        mock_cap = MagicMock()
        mock_cv2.VideoCapture.return_value = mock_cap
        mock_cap.isOpened.return_value = True

        def mock_get(prop):
            if prop == mock_cv2.CAP_PROP_FPS:
                return 30.0
            if prop == mock_cv2.CAP_PROP_FRAME_COUNT:
                return 150
            return 0

        mock_cap.get.side_effect = mock_get

        mock_cap.read.side_effect = [(True, MagicMock()), (True, MagicMock()), (False, None)]

        mock_cv2.absdiff.return_value = MagicMock()
        mock_np = sys.modules["numpy"]
        mock_np.mean.side_effect = [0, 50]

        detector = SceneDetector()
        result = detector._detect_with_opencv(mock_video_path, threshold=27.0)

        assert len(result.scenes) >= 1
        assert result.total_frames == 150

    def test_save_scene_list(self, mock_video_path, tmp_path):
        result = SceneDetectionResult(
            video_path=mock_video_path,
            scenes=[
                Scene(
                    scene_number=1,
                    start_time=0.0,
                    end_time=1.5,
                    start_frame=0,
                    end_frame=45,
                    duration=1.5,
                    score=1.0,
                    frame_count=45,
                ),
            ],
            total_duration=1.5,
            fps=30.0,
            total_frames=45,
            method=DetectionMethod.CONTENT,
            parameters={},
        )
        out_csv = tmp_path / "scenes.csv"
        SceneDetector.save_scene_list(result, out_csv)

        assert out_csv.exists()
        content = out_csv.read_text()
        assert "Scene,Start Time,End Time" in content
        assert "1,0.00,1.50,1.50,0,45,45,1.000" in content

    @patch.dict("sys.modules", {"cv2": MagicMock()})
    def test_extract_scene_thumbnails(self, mock_video_path, tmp_path):
        import sys

        mock_cv2 = sys.modules["cv2"]
        mock_cap = MagicMock()
        mock_cv2.VideoCapture.return_value = mock_cap
        mock_cap.get.return_value = 30.0  # fps
        mock_cap.read.return_value = (True, "mock_frame_data")
        mock_cv2.CAP_PROP_POS_FRAMES = 1
        mock_cv2.CAP_PROP_FPS = 5

        result = SceneDetectionResult(
            video_path=mock_video_path,
            scenes=[
                Scene(
                    scene_number=1,
                    start_time=0.0,
                    end_time=5.0,
                    start_frame=0,
                    end_frame=150,
                    duration=5.0,
                    score=1.0,
                    frame_count=150,
                ),
            ],
            total_duration=5.0,
            fps=30.0,
            total_frames=150,
            method=DetectionMethod.CONTENT,
            parameters={},
        )

        out_dir = tmp_path / "thumbs"
        SceneDetector.extract_scene_thumbnails(mock_video_path, result, out_dir, frame_offset=1.0)

        # Verify it seeks to 1.0s * 30fps = frame 30
        mock_cap.set.assert_called_with(1, 30)  # cv2.CAP_PROP_POS_FRAMES = 1
        mock_cv2.imwrite.assert_called_once()
        args, _ = mock_cv2.imwrite.call_args
        assert "scene_001.jpg" in str(args[0])
