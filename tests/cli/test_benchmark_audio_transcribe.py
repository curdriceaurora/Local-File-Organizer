"""Test that fo benchmark run --transcribe-smoke exercises AudioModel.generate()."""

from __future__ import annotations

import struct
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

from file_organizer.cli.benchmark import (
    _bind_transcribe_smoke,
    _check_baseline_smoke_compatibility,
    _exit_if_transcribe_smoke_failed,
    _maybe_attach_comparison_output,
    _run_audio_suite,
    _validate_transcribe_smoke_preconditions,
)
from file_organizer.cli.main import app


def _generate_silence_wav(path: Path, seconds: float = 0.5) -> None:
    """Write a mono 16-bit 16kHz silent WAV file at ``path``."""
    sample_rate = 16000
    n_frames = int(seconds * sample_rate)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(struct.pack("<h", 0) * n_frames)


@pytest.mark.unit
@pytest.mark.ci
class TestBindTranscribeSmoke:
    """Direct coverage of the _bind_transcribe_smoke helper. Cheap unit tests
    so the CI diff-coverage gate sees the new branches without needing the
    full Typer/Click stack."""

    def test_returns_unchanged_runner_when_smoke_off(self) -> None:
        sentinel = MagicMock(name="default_runner")
        result = _bind_transcribe_smoke(sentinel, suite="audio", transcribe_smoke=False)
        assert result is sentinel

    def test_returns_unchanged_runner_when_non_audio_and_smoke_off(self) -> None:
        sentinel = MagicMock(name="io_runner")
        result = _bind_transcribe_smoke(sentinel, suite="io", transcribe_smoke=False)
        assert result is sentinel

    def test_raises_bad_parameter_for_smoke_on_non_audio(self) -> None:
        sentinel = MagicMock(name="io_runner")
        with pytest.raises(typer.BadParameter, match="audio"):
            _bind_transcribe_smoke(sentinel, suite="io", transcribe_smoke=True)

    def test_binds_transcribe_smoke_for_audio_suite(self) -> None:
        sentinel = MagicMock(name="default_audio_runner")
        result = _bind_transcribe_smoke(sentinel, suite="audio", transcribe_smoke=True)
        # Returns a functools.partial pre-bound to _run_audio_suite — not the
        # sentinel default audio runner.
        assert result is not sentinel
        assert getattr(result, "func", None) is _run_audio_suite
        assert result.keywords == {"transcribe_smoke": True}


@pytest.mark.unit
@pytest.mark.ci
class TestValidateTranscribeSmokePreconditions:
    """Direct coverage of the empty-input / no-audio-candidates fail-fast
    helper. Both paths used to short-circuit the benchmark before the
    smoke-failure exit guard ran, exiting 0 with no verification done."""

    def test_passes_silently_when_smoke_off(self) -> None:
        # No raise even with empty file list when smoke is off.
        _validate_transcribe_smoke_preconditions([], transcribe_smoke=False)

    def test_passes_when_smoke_on_and_audio_candidate_present(self, tmp_path: Path) -> None:
        audio = tmp_path / "a.wav"
        audio.touch()
        _validate_transcribe_smoke_preconditions([audio], transcribe_smoke=True)

    def test_raises_when_smoke_on_and_no_files(self) -> None:
        with pytest.raises(typer.BadParameter, match="empty"):
            _validate_transcribe_smoke_preconditions([], transcribe_smoke=True)

    def test_raises_when_smoke_on_but_no_audio_candidates(self, tmp_path: Path) -> None:
        text_file = tmp_path / "x.txt"
        text_file.touch()
        with pytest.raises(typer.BadParameter, match="audio file"):
            _validate_transcribe_smoke_preconditions([text_file], transcribe_smoke=True)


@pytest.mark.unit
@pytest.mark.ci
class TestExitIfTranscribeSmokeFailed:
    """Direct coverage of the _exit_if_transcribe_smoke_failed helper."""

    def test_no_exit_when_reason_absent(self) -> None:
        console = MagicMock()
        # Should NOT raise when the smoke-skipped reason isn't present.
        _exit_if_transcribe_smoke_failed(console, ["audio-synthesized-metadata-fallback"])
        console.print.assert_not_called()

    def test_exits_nonzero_when_smoke_skipped_reason_present(self) -> None:
        console = MagicMock()
        with pytest.raises(typer.Exit) as exc_info:
            _exit_if_transcribe_smoke_failed(console, ["audio-transcribe-smoke-skipped"])
        assert exc_info.value.exit_code == 1
        # Error message goes to console so the human reader sees the cause.
        console.print.assert_called_once()
        msg = console.print.call_args.args[0]
        assert "transcribe-smoke" in msg.lower()
        assert "audio" in msg.lower()

    def test_json_mode_routes_error_to_stderr_keeping_stdout_console_silent(self) -> None:
        # When --json is requested, the JSON document is already on stdout by
        # the time the smoke-failure exit guard fires. Routing the error to
        # the stdout console would append non-JSON text and break consumers
        # that parse output on failure. The stdout console must NOT receive
        # the print; the message goes to a stderr-bound Rich console instead.
        stdout_console = MagicMock()
        with patch("rich.console.Console") as mock_console_cls:
            stderr_console = MagicMock()
            mock_console_cls.return_value = stderr_console
            with pytest.raises(typer.Exit):
                _exit_if_transcribe_smoke_failed(
                    stdout_console,
                    ["audio-transcribe-smoke-skipped"],
                    json_output=True,
                )
        stdout_console.print.assert_not_called()
        mock_console_cls.assert_called_once_with(stderr=True)
        stderr_console.print.assert_called_once()


@pytest.mark.integration
@pytest.mark.ci
class TestBenchmarkTranscribeSmoke:
    def test_transcribe_smoke_invokes_audio_model_once(self, tmp_path: Path) -> None:
        """With --transcribe-smoke, exactly one AudioModel.generate call
        happens regardless of the candidate count."""
        audio_dir = tmp_path / "audio"
        audio_dir.mkdir()
        _generate_silence_wav(audio_dir / "a.wav")
        _generate_silence_wav(audio_dir / "b.wav")

        runner = CliRunner()
        with patch("file_organizer.cli.benchmark.AudioModel") as mock_model_cls:
            instance = mock_model_cls.return_value
            instance.generate.return_value = ""
            result = runner.invoke(
                app,
                [
                    "benchmark",
                    "run",
                    str(audio_dir),
                    "--suite",
                    "audio",
                    "--transcribe-smoke",
                    "--iterations",
                    "1",
                    "--warmup",
                    "0",
                ],
            )

        assert result.exit_code == 0, result.output
        # Smoke contract: exactly one transcription per benchmark run, even
        # when multiple candidate audio files are present. Counts may exceed
        # 1 across iterations — for this test iterations=1 so the one call
        # is unambiguous.
        assert instance.generate.call_count == 1

    def test_no_transcribe_smoke_means_no_audio_model_call(self, tmp_path: Path) -> None:
        """Default benchmark (no flag) must not instantiate AudioModel."""
        audio_dir = tmp_path / "audio"
        audio_dir.mkdir()
        _generate_silence_wav(audio_dir / "a.wav")

        runner = CliRunner()
        with patch("file_organizer.cli.benchmark.AudioModel") as mock_model_cls:
            result = runner.invoke(
                app,
                [
                    "benchmark",
                    "run",
                    str(audio_dir),
                    "--suite",
                    "audio",
                    "--iterations",
                    "1",
                    "--warmup",
                    "0",
                ],
            )

        assert result.exit_code == 0, result.output
        mock_model_cls.assert_not_called()

    def test_transcribe_smoke_with_non_audio_suite_fails_fast(self, tmp_path: Path) -> None:
        """--transcribe-smoke without --suite audio must error, not silently
        no-op. Otherwise CI scripts that combine the wrong flags get a false
        positive (exit 0 with no smoke verification done)."""
        # Arrange a non-empty input dir so the early "no files" path doesn't
        # short-circuit before we hit the validation.
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        (input_dir / "x.txt").write_text("seed", encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "benchmark",
                "run",
                str(input_dir),
                "--suite",
                "io",
                "--transcribe-smoke",
                "--iterations",
                "1",
                "--warmup",
                "0",
            ],
        )

        assert result.exit_code != 0
        # Rich panels at the CI runner's narrower default width wrap
        # `--transcribe-smoke` mid-token in unpredictable spots (after the
        # dashes, between syllables). Asserting on individual word
        # components is wrap-immune.
        normalized = " ".join(result.output.lower().split())
        assert "transcribe" in normalized
        assert "smoke" in normalized
        assert "audio" in normalized

    def test_transcribe_smoke_exits_nonzero_when_audio_model_unavailable(
        self, tmp_path: Path
    ) -> None:
        """When --transcribe-smoke is requested but AudioModel raises
        ImportError (e.g. [audio] missing), the run must exit non-zero so
        CI doesn't treat the silently-skipped smoke as a passing audio
        benchmark."""
        audio_dir = tmp_path / "audio"
        audio_dir.mkdir()
        _generate_silence_wav(audio_dir / "a.wav")

        runner = CliRunner()
        with patch("file_organizer.cli.benchmark.AudioModel") as mock_model_cls:
            mock_model_cls.side_effect = ImportError("faster-whisper is not installed")
            result = runner.invoke(
                app,
                [
                    "benchmark",
                    "run",
                    str(audio_dir),
                    "--suite",
                    "audio",
                    "--transcribe-smoke",
                    "--iterations",
                    "1",
                    "--warmup",
                    "0",
                ],
            )

        assert result.exit_code != 0
        # Both the warning (from _run_audio_suite) and the failure error
        # (from run()) should appear so the user sees the cause and the
        # consequence. Normalize whitespace and use word-component
        # assertions to survive Rich panel wrap on narrow terminals.
        normalized = " ".join(result.output.lower().split())
        assert "transcribe" in normalized
        assert "smoke" in normalized
        assert "media" in normalized
        # The "Benchmark completed" success banner must NOT appear when
        # the smoke check failed — printing success and then exiting
        # non-zero produces contradictory output that misleads operators
        # and breaks any automation that scrapes the human log for
        # completion status.
        assert "benchmark completed" not in normalized


@pytest.mark.unit
@pytest.mark.ci
class TestCheckBaselineSmokeCompatibility:
    """Direct coverage of the smoke-mode compatibility helper that gates
    ``--compare`` mixing of smoke and non-smoke baselines.

    A smoke run adds an ``AudioModel.generate()`` call per iteration, which
    skews the per-iteration timings. Comparing across smoke modes without
    surfacing the mismatch produces misleading regression signals.
    """

    def test_returns_none_when_modes_match_both_true(self) -> None:
        warning = _check_baseline_smoke_compatibility(
            {"transcribe_smoke": True},
            transcribe_smoke=True,
            console=MagicMock(),
            json_output=False,
        )
        assert warning is None

    def test_returns_none_when_modes_match_both_false(self) -> None:
        warning = _check_baseline_smoke_compatibility(
            {"transcribe_smoke": False},
            transcribe_smoke=False,
            console=MagicMock(),
            json_output=False,
        )
        assert warning is None

    def test_returns_none_when_baseline_missing_field_and_current_false(self) -> None:
        # Older baselines predate the transcribe_smoke field; treat as False.
        warning = _check_baseline_smoke_compatibility(
            {},
            transcribe_smoke=False,
            console=MagicMock(),
            json_output=False,
        )
        assert warning is None

    def test_returns_warning_when_current_smoke_baseline_not(self) -> None:
        console = MagicMock()
        warning = _check_baseline_smoke_compatibility(
            {"transcribe_smoke": False},
            transcribe_smoke=True,
            console=console,
            json_output=False,
        )
        assert warning is not None
        assert "smoke-mode mismatch" in warning.lower()
        assert "baseline transcribe_smoke=false" in warning.lower()
        # Human-mode prints to console; JSON-mode would suppress the print.
        console.print.assert_called_once()

    def test_returns_warning_when_baseline_smoke_current_not(self) -> None:
        warning = _check_baseline_smoke_compatibility(
            {"transcribe_smoke": True},
            transcribe_smoke=False,
            console=MagicMock(),
            json_output=False,
        )
        assert warning is not None
        assert "current=false" in warning.lower()

    def test_json_mode_returns_warning_but_does_not_print(self) -> None:
        # Under --json, the warning is attached to the output dict rather
        # than printed, so stdout stays valid JSON for downstream consumers.
        console = MagicMock()
        warning = _check_baseline_smoke_compatibility(
            {"transcribe_smoke": False},
            transcribe_smoke=True,
            console=console,
            json_output=True,
        )
        assert warning is not None
        console.print.assert_not_called()

    def test_returns_malformed_warning_when_baseline_field_is_string(self) -> None:
        # `bool("false")` is True — naive coercion would silently invert the
        # mismatch signal. The helper must detect non-bool values and warn
        # rather than fall through to a misleading "no mismatch" result.
        warning = _check_baseline_smoke_compatibility(
            {"transcribe_smoke": "false"},
            transcribe_smoke=False,
            console=MagicMock(),
            json_output=False,
        )
        assert warning is not None
        assert "not a boolean" in warning.lower()
        assert "str" in warning  # type name is surfaced

    def test_returns_malformed_warning_when_baseline_field_is_int(self) -> None:
        # Same defensive check for ints (0/1) — Python treats them as bools
        # in arithmetic but the schema requires the JSON boolean.
        warning = _check_baseline_smoke_compatibility(
            {"transcribe_smoke": 1},
            transcribe_smoke=True,
            console=MagicMock(),
            json_output=False,
        )
        assert warning is not None
        assert "not a boolean" in warning.lower()
        assert "int" in warning


@pytest.mark.unit
@pytest.mark.ci
class TestMaybeAttachComparisonOutputSmokeWarning:
    """Coverage for the smoke-mode wiring inside ``_maybe_attach_comparison_output``.

    The helper attaches a ``comparison_smoke_warning`` field whenever the
    baseline's ``transcribe_smoke`` flag disagrees with the current run.
    The unit-level helper test pins the wording; this test pins the wiring
    so a future refactor can't silently drop the field.
    """

    def _write_baseline(self, tmp_path: Path, *, transcribe_smoke: bool) -> Path:
        import json as _json

        baseline_path = tmp_path / "baseline.json"
        baseline_path.write_text(
            _json.dumps(
                {
                    "suite": "audio",
                    "runner_profile_version": 1,
                    "transcribe_smoke": transcribe_smoke,
                    "results": {"p50_ms": 1.0, "p95_ms": 1.0, "files_processed": 0},
                }
            )
        )
        return baseline_path

    def test_attaches_smoke_warning_when_modes_differ(self, tmp_path: Path) -> None:
        baseline_path = self._write_baseline(tmp_path, transcribe_smoke=False)
        output: dict = {
            "suite": "audio",
            "runner_profile_version": 1,
            "transcribe_smoke": True,
            "results": {"p50_ms": 1.0, "p95_ms": 1.0, "files_processed": 0},
        }
        result = _maybe_attach_comparison_output(
            output=output,
            compare_path=baseline_path,
            suite="audio",
            transcribe_smoke=True,
            console=MagicMock(),
            json_output=True,
        )
        assert "comparison_smoke_warning" in result
        assert "smoke-mode mismatch" in result["comparison_smoke_warning"].lower()

    def test_no_smoke_warning_when_modes_match(self, tmp_path: Path) -> None:
        baseline_path = self._write_baseline(tmp_path, transcribe_smoke=True)
        output: dict = {
            "suite": "audio",
            "runner_profile_version": 1,
            "transcribe_smoke": True,
            "results": {"p50_ms": 1.0, "p95_ms": 1.0, "files_processed": 0},
        }
        result = _maybe_attach_comparison_output(
            output=output,
            compare_path=baseline_path,
            suite="audio",
            transcribe_smoke=True,
            console=MagicMock(),
            json_output=True,
        )
        assert "comparison_smoke_warning" not in result
