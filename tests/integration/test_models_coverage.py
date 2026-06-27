"""Integration tests targeting coverage gaps in local and API model providers.

Files covered:
- file_organizer/models/_llama_cpp_helpers.py
- file_organizer/models/_vision_helpers.py
- file_organizer/models/_claude_client.py
- file_organizer/models/_claude_response.py
- file_organizer/models/llama_cpp_text_model.py
- file_organizer/models/mlx_text_model.py
- file_organizer/models/claude_text_model.py
- file_organizer/models/claude_vision_model.py
- file_organizer/models/openai_text_model.py
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.models._claude_client import create_claude_client
from file_organizer.models._claude_response import extract_claude_text, is_claude_token_exhausted
from file_organizer.models._llama_cpp_helpers import (
    extract_llama_cpp_text,
    is_llama_cpp_token_exhausted,
)
from file_organizer.models._vision_helpers import (
    bytes_to_data_url,
    image_to_data_url,
    split_data_url,
)
from file_organizer.models.base import DeviceType, ModelConfig, ModelType, TokenExhaustionError
from file_organizer.models.claude_text_model import ClaudeTextModel
from file_organizer.models.claude_vision_model import ClaudeVisionModel
from file_organizer.models.llama_cpp_text_model import LlamaCppTextModel
from file_organizer.models.mlx_text_model import MLXTextModel
from file_organizer.models.openai_text_model import OpenAITextModel

pytestmark = pytest.mark.integration


# ===========================================================================
# 1. _llama_cpp_helpers.py Tests
# ===========================================================================


def test_llama_cpp_helpers_variations() -> None:
    # 1. is_llama_cpp_token_exhausted
    assert is_llama_cpp_token_exhausted({}) is False
    assert is_llama_cpp_token_exhausted({"choices": []}) is False

    # finish_reason != length
    response_ok = {"choices": [{"finish_reason": "stop", "text": "hello"}]}
    assert is_llama_cpp_token_exhausted(response_ok) is False

    # finish_reason == length, text long enough
    response_long = {"choices": [{"finish_reason": "length", "text": "a" * 100}]}
    assert is_llama_cpp_token_exhausted(response_long) is False

    # finish_reason == length, text too short
    response_exhausted = {"choices": [{"finish_reason": "length", "text": "short"}]}
    assert is_llama_cpp_token_exhausted(response_exhausted, min_length=20) is True

    # 2. extract_llama_cpp_text
    assert extract_llama_cpp_text({}) == ""
    assert extract_llama_cpp_text({"choices": []}) == ""
    assert extract_llama_cpp_text({"choices": [{"text": " hello "}]}) == "hello"
    assert extract_llama_cpp_text({"choices": [{"text": None}]}) == ""


# ===========================================================================
# 2. _vision_helpers.py Tests
# ===========================================================================


def test_vision_helpers_variations(tmp_path: Path) -> None:
    # 1. image_to_data_url
    img_file = tmp_path / "test.png"
    img_file.write_bytes(b"png-bytes")

    # png extension guess
    url_png = image_to_data_url(img_file)
    assert url_png.startswith("data:image/png;base64,")

    # unknown extension fallback
    unknown_file = tmp_path / "test.unknown_ext_xyz_123"
    unknown_file.write_bytes(b"xyz-bytes")
    url_xyz = image_to_data_url(unknown_file)
    assert url_xyz.startswith("data:image/jpeg;base64,")

    # 2. bytes_to_data_url
    url_bytes = bytes_to_data_url(b"raw-data", mime_type="image/gif")
    assert url_bytes.startswith("data:image/gif;base64,")

    # 3. split_data_url
    mime, b64 = split_data_url("data:image/png;base64,cG5n")
    assert mime == "image/png"
    assert b64 == "cG5n"

    # Default mime split
    mime_def, b64_def = split_data_url("data:;base64,cG5n")
    assert mime_def == "image/jpeg"
    assert b64_def == "cG5n"

    # Malformed data URL raises ValueError
    with pytest.raises(ValueError) as exc:
        split_data_url("http://not-a-data-url")
    assert "Not a valid base64 data URL" in str(exc.value)


# ===========================================================================
# 3. _claude_client.py & _claude_response.py Tests
# ===========================================================================


class TestClaudeClientAndResponse:
    def test_create_claude_client_success(self) -> None:
        config = ModelConfig(
            name="claude-3-5-sonnet",
            model_type=ModelType.TEXT,
            provider="claude",
            api_key="sk-ant-test",
        )
        with (
            patch("file_organizer.models._claude_client.ANTHROPIC_AVAILABLE", True, create=True),
            patch("file_organizer.models._claude_client.Anthropic", create=True) as mock_anthropic,
        ):
            client = create_claude_client(config, "text")
            assert client is not None
            mock_anthropic.assert_called_once_with(api_key="sk-ant-test")

    def test_create_claude_client_warnings_and_errors(self) -> None:
        config = ModelConfig(
            name="claude-3",
            model_type=ModelType.TEXT,
            provider="claude",
            api_base_url="https://ignored.api",
        )
        with (
            patch("file_organizer.models._claude_client.ANTHROPIC_AVAILABLE", True, create=True),
            patch("file_organizer.models._claude_client.Anthropic", create=True) as mock_anthropic,
        ):
            # Should log a warning and proceed without base_url
            client = create_claude_client(config, "text")
            assert client is not None
            mock_anthropic.assert_called_once_with()

            # Constructor error handling
            mock_anthropic.side_effect = ValueError("invalid client setup")
            with pytest.raises(ValueError):
                create_claude_client(config, "text")

    def test_create_claude_client_import_error(self) -> None:
        config = ModelConfig(name="claude", model_type=ModelType.TEXT, provider="claude")
        with patch("file_organizer.models._claude_client.ANTHROPIC_AVAILABLE", False):
            with pytest.raises(ImportError) as exc:
                create_claude_client(config, "text")
            assert "The 'anthropic' package is not installed" in str(exc.value)

    def test_claude_response_helpers(self) -> None:
        # Mock Response object
        mock_resp = MagicMock()

        # extract_claude_text variations
        mock_resp.content = []
        assert extract_claude_text(mock_resp) == ""

        mock_content = MagicMock()
        mock_content.text = " hello claude "
        mock_resp.content = [mock_content]
        assert extract_claude_text(mock_resp) == "hello claude"

        # is_claude_token_exhausted variations
        mock_resp.stop_reason = "end_turn"
        assert is_claude_token_exhausted(mock_resp) is False

        mock_resp.stop_reason = "max_tokens"
        # content length is 12 (useful), min_length=50 -> exhausted
        assert is_claude_token_exhausted(mock_resp, min_length=50) is True
        # content length is 12, min_length=5 -> not exhausted
        assert is_claude_token_exhausted(mock_resp, min_length=5) is False


# ===========================================================================
# 4. llama_cpp_text_model.py Tests
# ===========================================================================


class TestLlamaCppTextModel:
    def test_llama_cpp_constructor_validations(self) -> None:
        # 1. Missing package ImportError
        with patch("file_organizer.models.llama_cpp_text_model.LLAMA_CPP_AVAILABLE", False):
            config = ModelConfig(name="m", model_type=ModelType.TEXT, provider="llama_cpp")
            with pytest.raises(ImportError) as exc:
                LlamaCppTextModel(config)
            assert "llama-cpp-python" in str(exc.value)

        # 2. Invalid model type
        with patch("file_organizer.models.llama_cpp_text_model.LLAMA_CPP_AVAILABLE", True):
            config = ModelConfig(name="m", model_type=ModelType.VISION, provider="llama_cpp")
            with pytest.raises(ValueError) as exc:
                LlamaCppTextModel(config)
            assert "only supports ModelType.TEXT" in str(exc.value)

        # 3. Missing model_path
        with patch("file_organizer.models.llama_cpp_text_model.LLAMA_CPP_AVAILABLE", True):
            config = ModelConfig(
                name="m", model_type=ModelType.TEXT, provider="llama_cpp", model_path=""
            )
            with pytest.raises(ValueError) as exc:
                LlamaCppTextModel(config)
            assert "model_path must be a non-empty path" in str(exc.value)

    @patch("file_organizer.models.llama_cpp_text_model.Llama")
    def test_llama_cpp_initialize_and_device_mappings(self, mock_llama: MagicMock) -> None:
        with patch("file_organizer.models.llama_cpp_text_model.LLAMA_CPP_AVAILABLE", True):
            # MPS GPU Device offloading mapping
            c_mps = ModelConfig(
                name="m",
                model_type=ModelType.TEXT,
                provider="llama_cpp",
                model_path="model.gguf",
                device=DeviceType.MPS,
            )
            m_mps = LlamaCppTextModel(c_mps)
            m_mps.initialize()
            mock_llama.assert_called_once_with(
                model_path="model.gguf",
                n_ctx=4096,
                n_gpu_layers=-1,
                verbose=False,
            )

            # CPU / AUTO mappings with extra_params override
            mock_llama.reset_mock()
            c_cpu = ModelConfig(
                name="m",
                model_type=ModelType.TEXT,
                provider="llama_cpp",
                model_path="model.gguf",
                device=DeviceType.CPU,
                extra_params={"n_gpu_layers": 12},
            )
            m_cpu = LlamaCppTextModel(c_cpu)
            m_cpu.initialize()
            mock_llama.assert_called_once_with(
                model_path="model.gguf",
                n_ctx=4096,
                n_gpu_layers=12,
                verbose=False,
            )

            # Load exception handling
            mock_llama.side_effect = RuntimeError("binary load error")
            m_err = LlamaCppTextModel(c_mps)
            with pytest.raises(RuntimeError) as exc:
                m_err.initialize()
            assert "Could not load GGUF model" in str(exc.value)

    @patch("file_organizer.models.llama_cpp_text_model.Llama")
    def test_llama_cpp_generation_and_retries(self, mock_llama: MagicMock) -> None:
        mock_client = MagicMock()
        mock_llama.return_value = mock_client

        config = ModelConfig(
            name="m",
            model_type=ModelType.TEXT,
            provider="llama_cpp",
            model_path="model.gguf",
            max_tokens=100,
            top_k=40,
            top_p=0.9,
        )
        with patch("file_organizer.models.llama_cpp_text_model.LLAMA_CPP_AVAILABLE", True):
            model = LlamaCppTextModel(config)

        # Guard check before init
        with pytest.raises(RuntimeError) as exc_init:
            model.generate("test")
        assert "Model not initialized" in str(exc_init.value)

        model.initialize()

        # Case 1: Simple successful generation
        mock_client.return_value = {"choices": [{"finish_reason": "stop", "text": " Hello Local "}]}
        res = model.generate("test")
        assert res == "Hello Local"
        mock_client.assert_called_once_with(
            "test",
            temperature=0.5,
            max_tokens=100,
            top_k=40,
            top_p=0.9,
        )

        # Case 2: Token exhaustion retry success
        mock_client.reset_mock()
        # First call returns token exhausted (finish_reason=length, short text)
        exhausted_choice = {"choices": [{"finish_reason": "length", "text": "short"}]}
        # Second call (retry) returns successful stop
        ok_choice = {"choices": [{"finish_reason": "stop", "text": "successful retry text"}]}
        mock_client.side_effect = [exhausted_choice, ok_choice]

        res_retry = model.generate("test")
        assert res_retry == "successful retry text"
        assert mock_client.call_count == 2

        # Verify the retry max_tokens was multiplied
        mock_client.assert_any_call(
            "test",
            temperature=0.5,
            max_tokens=200,  # 100 * RETRY_MULTIPLIER (2)
            top_k=40,
            top_p=0.9,
        )

        # Case 3: Double token exhaustion raises TokenExhaustionError
        mock_client.reset_mock()
        mock_client.side_effect = None
        mock_client.return_value = exhausted_choice

        with pytest.raises(TokenExhaustionError) as exc_exhaust:
            model.generate("test")
        assert "exhausted token budget on retry" in str(exc_exhaust.value)

        # Cleanup
        mock_client.close.side_effect = RuntimeError("close error")
        model.cleanup()
        assert model.client is None
        assert model._initialized is False


# ===========================================================================
# 5. mlx_text_model.py Tests
# ===========================================================================


class TestMLXTextModel:
    def test_mlx_constructor_validations(self) -> None:
        # 1. Missing package ImportError
        with patch("file_organizer.models.mlx_text_model.MLX_LM_AVAILABLE", False):
            config = ModelConfig(name="m", model_type=ModelType.TEXT, provider="mlx")
            with pytest.raises(ImportError) as exc:
                MLXTextModel(config)
            assert "mlx-lm" in str(exc.value)

        # 2. Invalid model type
        with patch("file_organizer.models.mlx_text_model.MLX_LM_AVAILABLE", True):
            config = ModelConfig(name="m", model_type=ModelType.VISION, provider="mlx")
            with pytest.raises(ValueError) as exc:
                MLXTextModel(config)
            assert "only supports ModelType.TEXT" in str(exc.value)

        # 3. Missing model_path
        with patch("file_organizer.models.mlx_text_model.MLX_LM_AVAILABLE", True):
            config = ModelConfig(name="m", model_type=ModelType.TEXT, provider="mlx", model_path="")
            with pytest.raises(ValueError) as exc:
                MLXTextModel(config)
            assert "model_path must be a non-empty path" in str(exc.value)

    @patch("file_organizer.models.mlx_text_model.mlx_load")
    def test_mlx_initialize_and_locking(self, mock_load: MagicMock) -> None:
        mock_load.return_value = ("mock_model", "mock_tokenizer")
        config = ModelConfig(
            name="m",
            model_type=ModelType.TEXT,
            provider="mlx",
            model_path="mlx-community/Llama-3",
        )
        with patch("file_organizer.models.mlx_text_model.MLX_LM_AVAILABLE", True):
            model = MLXTextModel(config)

            # Initialize
            model.initialize()
            assert model._initialized is True
            assert model._model == "mock_model"
            assert model._tokenizer == "mock_tokenizer"
            mock_load.assert_called_once_with("mlx-community/Llama-3")

            # Double initialization is a noop
            model.initialize()
            assert mock_load.call_count == 1

            # Load returning bad tuple shape
            mock_load.return_value = "not-a-tuple"
            model_bad = MLXTextModel(config)
            with pytest.raises(RuntimeError) as exc:
                model_bad.initialize()
            assert "expected (model, tokenizer)" in str(exc.value)

    @patch("file_organizer.models.mlx_text_model.mlx_generate")
    @patch("file_organizer.models.mlx_text_model.mlx_load")
    def test_mlx_generation_and_signature_fallbacks(
        self, mock_load: MagicMock, mock_generate: MagicMock
    ) -> None:
        mock_load.return_value = ("mock_model", "mock_tokenizer")
        config = ModelConfig(
            name="m",
            model_type=ModelType.TEXT,
            provider="mlx",
            model_path="mlx-community/Llama-3",
            top_k=40,
            top_p=0.9,
        )
        with patch("file_organizer.models.mlx_text_model.MLX_LM_AVAILABLE", True):
            model = MLXTextModel(config)
            model.initialize()

        # Variant 1 (most expressive) fails with unexpected keyword TypeError,
        # Variant 2 succeeds.
        mock_generate.side_effect = [
            TypeError("got an unexpected keyword argument 'temp'"),
            " Generated Text ",
        ]

        res = model.generate("hello")
        assert res == "Generated Text"
        assert mock_generate.call_count == 2

        # Succeeded variant index should be cached (variant index 1)
        assert model._working_variant_idx == 1

        # Subsequent call uses fast path directly with cached variant parameters
        mock_generate.reset_mock()
        mock_generate.side_effect = None
        mock_generate.return_value = "Cached Fast Path"

        res_fast = model.generate("hello")
        assert res_fast == "Cached Fast Path"
        mock_generate.assert_called_once_with(
            "mock_model",
            "mock_tokenizer",
            "hello",
            max_tokens=3000,
            temperature=0.5,
            top_p=0.9,
            top_k=40,
        )

        # Fatal TypeErrors that are NOT signature mismatch should raise directly
        mock_generate.reset_mock()
        mock_generate.side_effect = TypeError("argument must be string, got int")
        model._working_variant_idx = None  # reset
        with pytest.raises(TypeError) as exc:
            model.generate("hello")
        assert "argument must be string" in str(exc.value)

        # Cleanup
        model.cleanup()
        assert model._model is None
        assert model._tokenizer is None
        assert model._initialized is False


# ===========================================================================
# 6. ClaudeTextModel & ClaudeVisionModel Tests
# ===========================================================================


class TestClaudeModels:
    @patch("file_organizer.models.claude_text_model.create_claude_client")
    def test_claude_text_generation_and_token_exhaustion(self, mock_create: MagicMock) -> None:
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        config = ModelConfig(
            name="claude-3-5",
            model_type=ModelType.TEXT,
            provider="claude",
            max_tokens=150,
        )
        with patch("file_organizer.models.claude_text_model.ANTHROPIC_AVAILABLE", True):
            model = ClaudeTextModel(config)
        model.initialize()

        # Mock token exhausted response, then success response on retry
        mock_exhausted = MagicMock()
        mock_exhausted.stop_reason = "max_tokens"
        mock_content_exhausted = MagicMock()
        mock_content_exhausted.text = "short"
        mock_exhausted.content = [mock_content_exhausted]

        mock_ok = MagicMock()
        mock_ok.stop_reason = "end_turn"
        mock_content_ok = MagicMock()
        mock_content_ok.text = "successful text generation on retry path"
        mock_ok.content = [mock_content_ok]

        mock_client.messages.create.side_effect = [mock_exhausted, mock_ok]

        res = model.generate("hello prompt")
        assert res == "successful text generation on retry path"
        assert mock_client.messages.create.call_count == 2

        # Verify the retry max_tokens was multiplied
        mock_client.messages.create.assert_any_call(
            model="claude-3-5",
            max_tokens=300,  # 150 * RETRY_MULTIPLIER (2)
            messages=[{"role": "user", "content": "hello prompt"}],
            temperature=0.5,
        )

        # Cleanup
        model.cleanup()
        assert model.client is None
        assert model._initialized is False

    @patch("file_organizer.models.claude_vision_model.create_claude_client")
    def test_claude_vision_image_payload_and_errors(
        self, mock_create: MagicMock, tmp_path: Path
    ) -> None:
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        config = ModelConfig(
            name="claude-3-5-sonnet",
            model_type=ModelType.VISION,
            provider="claude",
        )
        with patch("file_organizer.models.claude_vision_model.ANTHROPIC_AVAILABLE", True):
            model = ClaudeVisionModel(config)
            model.initialize()

            # Mock successful message response
            mock_resp = MagicMock()
            mock_resp.stop_reason = "end_turn"
            mock_content = MagicMock()
            mock_content.text = "A descriptive image analysis response."
            mock_resp.content = [mock_content]
            mock_client.messages.create.return_value = mock_resp

            # Create dummy image
            img_file = tmp_path / "vision.png"
            img_file.write_bytes(b"dummy-png-data")

            res = model.analyze_image(img_file, task="describe")
            assert res == "A descriptive image analysis response."

            # Verify client messages payload structure matches Claude requirements (base64 image block + text block)
            mock_client.messages.create.assert_called_once()
            call_kwargs = mock_client.messages.create.call_args[1]
            assert call_kwargs["model"] == "claude-3-5-sonnet"
            messages = call_kwargs["messages"]
            assert len(messages) == 1
            assert messages[0]["role"] == "user"
            content_blocks = messages[0]["content"]
            assert len(content_blocks) == 2
            assert content_blocks[0]["type"] == "image"
            assert content_blocks[0]["source"]["type"] == "base64"
            assert content_blocks[0]["source"]["media_type"] == "image/png"
            assert content_blocks[1]["type"] == "text"

            # Mutually exclusive paths validation
            with pytest.raises(ValueError) as exc_excl:
                model.generate("prompt", image_path=img_file, image_data=b"bytes")
            assert "Provide exactly one of image_path or image_data" in str(exc_excl.value)

            # Vision constructor type validation
            config_text = ModelConfig(name="claude-3", model_type=ModelType.TEXT, provider="claude")
            with pytest.raises(ValueError) as exc_type:
                ClaudeVisionModel(config_text)
            assert "Expected VISION or VIDEO" in str(exc_type.value)


# ===========================================================================
# 7. openai_text_model.py Tests
# ===========================================================================


class TestOpenAITextModel:
    @patch("file_organizer.models.openai_text_model.create_openai_client")
    def test_openai_text_generation_exhaustion_and_empty_choices(
        self, mock_create: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        config = ModelConfig(
            name="gpt-4",
            model_type=ModelType.TEXT,
            provider="openai",
        )
        with patch("file_organizer.models.openai_text_model.OPENAI_AVAILABLE", True):
            model = OpenAITextModel(config)
            model.initialize()

            # Case 1: Empty choices response handling
            mock_resp_empty = MagicMock()
            mock_resp_empty.choices = []
            mock_client.chat.completions.create.return_value = mock_resp_empty

            res_empty = model.generate("prompt")
            assert res_empty == ""

            # Case 2: Token exhaustion and API errors raising
            mock_choice = MagicMock()
            mock_choice.finish_reason = "length"
            mock_choice.message.content = "short"
            mock_resp_exhausted = MagicMock()
            mock_resp_exhausted.choices = [mock_choice]

            mock_client.chat.completions.create.return_value = mock_resp_exhausted

            with pytest.raises(TokenExhaustionError):
                model.generate("prompt")

            # Cleanup
            model.cleanup()
            assert model.client is None
            assert model._initialized is False


# ===========================================================================
# 8. audio_transcriber.py Tests
# ===========================================================================


class TestAudioTranscriber:
    def test_audio_transcriber_constructor_validations(self) -> None:
        from file_organizer.models.audio_transcriber import AudioTranscriber

        # 1. ImportError when faster-whisper is not available
        with patch("file_organizer.models.audio_transcriber._FASTER_WHISPER_AVAILABLE", False):
            with pytest.raises(ImportError) as exc:
                AudioTranscriber()
            assert "faster-whisper is required" in str(exc.value)

        # 2. Invalid model size
        with patch("file_organizer.models.audio_transcriber._FASTER_WHISPER_AVAILABLE", True):
            with pytest.raises(ValueError) as exc:
                AudioTranscriber(model_size="invalid-size")
            assert "Invalid model size" in str(exc.value)

            # 3. Invalid compute type
            with pytest.raises(ValueError) as exc:
                AudioTranscriber(compute_type="invalid-compute")
            assert "Invalid compute type" in str(exc.value)

    @patch("file_organizer.models.audio_transcriber.WhisperModel")
    def test_audio_transcriber_device_detection(self, mock_whisper_cls: MagicMock) -> None:
        from file_organizer.models.audio_transcriber import AudioTranscriber

        with patch("file_organizer.models.audio_transcriber._FASTER_WHISPER_AVAILABLE", True):
            # Test explicit device
            transcriber = AudioTranscriber(device="cpu")
            assert transcriber.device == "cpu"

            # Test CUDA GPU detection
            mock_torch = MagicMock()
            mock_torch.cuda.is_available.return_value = True
            with patch.dict("sys.modules", {"torch": mock_torch}):
                transcriber_cuda = AudioTranscriber(device="auto")
                assert transcriber_cuda.device == "cuda"

            # Test MPS GPU detection
            mock_torch_mps = MagicMock()
            mock_torch_mps.cuda.is_available.return_value = False
            mock_torch_mps.backends.mps.is_available.return_value = True
            with patch.dict("sys.modules", {"torch": mock_torch_mps}):
                transcriber_mps = AudioTranscriber(device="auto")
                assert transcriber_mps.device == "mps"

            # Test CPU fallback
            mock_torch_cpu = MagicMock()
            mock_torch_cpu.cuda.is_available.return_value = False
            mock_torch_cpu.backends.mps.is_available.return_value = False
            with patch.dict("sys.modules", {"torch": mock_torch_cpu}):
                transcriber_cpu = AudioTranscriber(device="auto")
                assert transcriber_cpu.device == "cpu"

            # Test torch ImportError fallback for CPU
            with patch.dict("sys.modules", {"torch": None}):
                transcriber_no_torch = AudioTranscriber(device="auto")
                assert transcriber_no_torch.device == "cpu"

    @patch("file_organizer.models.audio_transcriber.WhisperModel")
    def test_audio_transcriber_transcribe_and_language_detection(
        self, mock_whisper_cls: MagicMock, tmp_path: Path
    ) -> None:
        from file_organizer.models.audio_transcriber import (
            AudioTranscriber,
            ComputeType,
            ModelSize,
            TranscriptionOptions,
        )

        mock_whisper = MagicMock()
        mock_whisper_cls.return_value = mock_whisper

        # Set up mock segments and info
        mock_seg = MagicMock()
        mock_seg.text = " Hello world segment "
        mock_seg.start = 0.0
        mock_seg.end = 2.0
        mock_seg.avg_logprob = -0.1
        mock_word = MagicMock()
        mock_word.word = "Hello"
        mock_word.start = 0.0
        mock_word.end = 1.0
        mock_word.probability = 0.95
        mock_seg.words = [mock_word]

        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.language_probability = 0.99
        mock_info.duration = 10.0

        mock_whisper.transcribe.return_value = ([mock_seg], mock_info)

        dummy_audio = tmp_path / "audio.wav"
        dummy_audio.write_bytes(b"dummy wav data")

        with patch("file_organizer.models.audio_transcriber._FASTER_WHISPER_AVAILABLE", True):
            transcriber = AudioTranscriber(
                model_size=ModelSize.TINY,
                compute_type=ComputeType.FLOAT32,
                cache_dir=tmp_path,
            )

            # 1. Language detection
            lang_res = transcriber.detect_language(dummy_audio)
            assert lang_res.language == "en"
            assert lang_res.language_name == "English"
            assert lang_res.confidence == 0.99

            # Language detection exception path
            mock_whisper.transcribe.side_effect = ValueError("transcribe crash")
            with pytest.raises(RuntimeError) as exc:
                transcriber.detect_language(dummy_audio)
            assert "Language detection failed" in str(exc.value)
            mock_whisper.transcribe.side_effect = None  # reset

            # File not found error
            with pytest.raises(FileNotFoundError):
                transcriber.detect_language(tmp_path / "missing.wav")

            # 2. Transcription
            options = TranscriptionOptions(language="en", word_timestamps=True)
            res = transcriber.transcribe(dummy_audio, options=options)

            assert res.text == "Hello world segment"
            assert res.language == "en"
            assert res.language_confidence == 0.99
            assert len(res.segments) == 1
            assert res.segments[0].text == "Hello world segment"
            assert res.segments[0].words is not None
            assert res.segments[0].words[0]["word"] == "Hello"
            assert res.duration == 10.0

            # Transcription missing file
            with pytest.raises(FileNotFoundError):
                transcriber.transcribe(tmp_path / "missing_transcribe.wav")

            # Transcription model is None
            transcriber.model = None
            with pytest.raises(RuntimeError) as exc:
                transcriber.transcribe(dummy_audio)
            assert "Model not loaded" in str(exc.value)
            # reload model
            transcriber.model = transcriber._load_model()

            # 3. Model cache hit
            mock_whisper_cls.reset_mock()
            cached_model = transcriber._load_model()
            assert cached_model is mock_whisper
            mock_whisper_cls.assert_not_called()

            # 4. Processing time <= 0
            with patch("time.time", side_effect=[100.0, 100.0]):
                res_time = transcriber.transcribe(dummy_audio)
                assert res_time.processing_time == 0.0

            # Test static methods and cache clearing
            assert "wav" in AudioTranscriber.get_supported_formats()

            transcriber.clear_cache()
            assert transcriber.model is None
            assert transcriber._model_loaded is False

            # Test model cache class-level
            AudioTranscriber.clear_all_caches()

            # Test model load failure
            mock_whisper_cls.side_effect = RuntimeError("Failed to load weight binary")
            transcriber_err = AudioTranscriber(model_size=ModelSize.TINY, device="cpu")
            with pytest.raises(RuntimeError) as exc:
                transcriber_err.transcribe(dummy_audio)
            assert "Model loading failed" in str(exc.value)

            # Test transcription failure
            mock_whisper_cls.side_effect = None
            mock_whisper_cls.return_value = mock_whisper
            mock_whisper.transcribe.side_effect = ValueError("Inference crash")
            transcriber_crash = AudioTranscriber(model_size=ModelSize.TINY, device="cpu")
            with pytest.raises(RuntimeError) as exc:
                transcriber_crash.transcribe(dummy_audio)
            assert "Transcription failed" in str(exc.value)
