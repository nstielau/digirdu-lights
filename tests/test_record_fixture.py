import io
import math
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path
from contextlib import redirect_stderr
from unittest.mock import patch

from tools import record_fixture


def write_wav(path, sample_rate=16000, channels=1, sample_width=2, duration_s=1.0):
    frame_count = int(sample_rate * duration_s)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(sample_width)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\0" * frame_count * channels * sample_width)


class WavValidationTests(unittest.TestCase):
    def test_validate_wav_returns_audio_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "fixture.wav"
            write_wav(path, duration_s=10.0)

            self.assertEqual(
                record_fixture.validate_wav(path),
                {
                    "sample_rate_hz": 16000,
                    "channels": 1,
                    "sample_width_bytes": 2,
                    "frame_count": 160000,
                    "duration_s": 10.0,
                },
            )

    def test_validate_wav_rejects_wrong_format(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cases = (
                ("rate.wav", {"sample_rate": 8000}),
                ("channels.wav", {"channels": 2}),
                ("width.wav", {"sample_width": 1}),
                ("duration.wav", {"duration_s": 2.0}),
            )
            for name, kwargs in cases:
                with self.subTest(name=name):
                    path = root / name
                    write_wav(path, **kwargs)
                    with self.assertRaises(ValueError):
                        record_fixture.validate_wav(path)

    def test_validate_wav_rejects_malformed_and_truncated_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            malformed = root / "malformed.wav"
            malformed.write_bytes(b"not a wav")
            with self.assertRaises(ValueError):
                record_fixture.validate_wav(malformed)

            complete = root / "complete.wav"
            write_wav(complete, duration_s=1.0)
            truncated = root / "truncated.wav"
            truncated.write_bytes(complete.read_bytes()[:-10])
            with self.assertRaises(ValueError):
                record_fixture.validate_wav(truncated)

    def test_validate_wav_can_disable_duration_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "short.wav"
            write_wav(path, duration_s=1.0)

            metadata = record_fixture.validate_wav(path, expected_duration_s=None)

            self.assertEqual(metadata["frame_count"], 16000)
            self.assertEqual(metadata["duration_s"], 1.0)

    def test_validate_wav_rejects_invalid_duration_constraints(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "fixture.wav"
            write_wav(path, duration_s=1.0)

            cases = (
                {"expected_duration_s": math.nan},
                {"expected_duration_s": math.inf},
                {"expected_duration_s": -1.0},
                {"duration_tolerance_s": math.nan},
                {"duration_tolerance_s": math.inf},
                {"duration_tolerance_s": -1.0},
            )
            for kwargs in cases:
                with self.subTest(kwargs=kwargs):
                    with self.assertRaises(ValueError):
                        record_fixture.validate_wav(path, **kwargs)


class FfmpegCommandTests(unittest.TestCase):
    def test_build_ffmpeg_command_has_expected_avfoundation_shape(self):
        command = record_fixture.build_ffmpeg_command(
            3, Path("out.wav"), 10.0, 16000, 1
        )

        self.assertEqual(
            command,
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "avfoundation",
                "-i",
                ":3",
                "-t",
                "10.0",
                "-ar",
                "16000",
                "-ac",
                "1",
                "-sample_fmt",
                "s16",
                "out.wav",
            ],
        )


class CliTests(unittest.TestCase):
    def test_duration_cli_rejects_nonfinite_and_nonpositive_values(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "fixture.wav"
            for raw in ("nan", "inf", "-inf", "0", "-1"):
                with self.subTest(raw=raw), redirect_stderr(io.StringIO()):
                    try:
                        record_fixture.main(
                            ["--output", str(output), "--duration", raw]
                        )
                    except SystemExit as exc:
                        self.assertEqual(exc.code, 2)
                    else:
                        self.fail("invalid duration was accepted")

    def test_capture_pad_cli_rejects_nonfinite_and_negative_values(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "fixture.wav"
            for raw in ("nan", "inf", "-inf", "-1"):
                with self.subTest(raw=raw), redirect_stderr(io.StringIO()):
                    try:
                        record_fixture.main(
                            ["--output", str(output), "--capture-pad-s", raw]
                        )
                    except SystemExit as exc:
                        self.assertEqual(exc.code, 2)
                    else:
                        self.fail("invalid capture pad was accepted")

    def test_list_inputs_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "should-not-exist.wav"
            completed = subprocess.CompletedProcess([], 1)
            with patch.object(record_fixture.subprocess, "run", return_value=completed) as run:
                result = record_fixture.main(["--list-inputs", "--output", str(output)])

            self.assertEqual(result, 1)
            run.assert_called_once_with(
                ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
                check=False,
            )
            self.assertFalse(output.exists())

    def test_parent_setup_error_returns_nonzero_and_preserves_output(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "fixture.wav"
            output.write_bytes(b"keep this recording")
            stderr = io.StringIO()
            with patch.object(Path, "mkdir", side_effect=OSError("cannot create directory")), \
                    redirect_stderr(stderr):
                result = record_fixture.main(["--output", str(output)])

            self.assertEqual(result, 1)
            self.assertIn("recording failed", stderr.getvalue())
            self.assertIn("cannot create directory", stderr.getvalue())
            self.assertEqual(output.read_bytes(), b"keep this recording")

    def test_temp_file_setup_error_returns_nonzero_and_preserves_output(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "fixture.wav"
            output.write_bytes(b"keep this recording")
            stderr = io.StringIO()
            with patch.object(record_fixture.tempfile, "mkstemp",
                              side_effect=OSError("cannot create temp file")), \
                    redirect_stderr(stderr):
                result = record_fixture.main(["--output", str(output)])

            self.assertEqual(result, 1)
            self.assertIn("recording failed", stderr.getvalue())
            self.assertIn("cannot create temp file", stderr.getvalue())
            self.assertEqual(output.read_bytes(), b"keep this recording")

    def test_list_inputs_missing_ffmpeg_returns_nonzero_with_diagnostic(self):
        stderr = io.StringIO()
        missing = FileNotFoundError(2, "No such file or directory", "ffmpeg")
        with patch.object(record_fixture.subprocess, "run", side_effect=missing), \
                redirect_stderr(stderr):
            result = record_fixture.main(["--list-inputs"])

        self.assertEqual(result, 1)
        self.assertIn("ffmpeg", stderr.getvalue())
        self.assertIn("not found", stderr.getvalue())

    def test_list_inputs_launch_oserror_returns_nonzero_with_diagnostic(self):
        stderr = io.StringIO()
        launch_error = OSError("cannot execute ffmpeg")
        with patch.object(record_fixture.subprocess, "run", side_effect=launch_error), \
                redirect_stderr(stderr):
            result = record_fixture.main(["--list-inputs"])

        self.assertEqual(result, 1)
        self.assertIn("ffmpeg", stderr.getvalue())
        self.assertIn("cannot execute ffmpeg", stderr.getvalue())

    def test_successful_record_replaces_output_atomically_after_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "fixture.wav"
            output.write_bytes(b"old recording")
            commands = []

            def run_ffmpeg(command, check):
                self.assertTrue(check)
                commands.append(command)
                write_wav(Path(command[-1]), duration_s=1.0)
                return subprocess.CompletedProcess(command, 0)

            with patch.object(record_fixture.subprocess, "run", side_effect=run_ffmpeg):
                result = record_fixture.main(
                    [
                        "--input",
                        "2",
                        "--output",
                        str(output),
                        "--duration",
                        "1",
                    ]
                )

            self.assertEqual(result, 0)
            self.assertEqual(record_fixture.validate_wav(output, expected_duration_s=1.0)["frame_count"], 16000)
            self.assertEqual(len(commands), 1)
            self.assertEqual(commands[0][7], ":2")
            self.assertEqual(Path(commands[0][-1]).parent, root)
            self.assertNotEqual(Path(commands[0][-1]), output)

    def test_record_default_capture_pad_extends_ffmpeg_duration(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "fixture.wav"
            commands = []

            def run_ffmpeg(command, check):
                self.assertTrue(check)
                commands.append(command)
                write_wav(Path(command[-1]), duration_s=1.0)
                return subprocess.CompletedProcess(command, 0)

            with patch.object(record_fixture.subprocess, "run", side_effect=run_ffmpeg):
                result = record_fixture.main(
                    ["--output", str(output), "--duration", "1"]
                )

            self.assertEqual(result, 0)
            self.assertEqual(len(commands), 1)
            self.assertEqual(commands[0][commands[0].index("-t") + 1], "2.25")

    def test_failed_record_preserves_existing_output_and_removes_temp_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "fixture.wav"
            output.write_bytes(b"keep this recording")
            failure = subprocess.CalledProcessError(2, ["ffmpeg"])
            with patch.object(record_fixture.subprocess, "run", side_effect=failure):
                result = record_fixture.main(["--output", str(output)])

            self.assertEqual(result, 2)
            self.assertEqual(output.read_bytes(), b"keep this recording")
            self.assertEqual(list(root.glob(f".{output.name}.*")), [])

    def test_invalid_wav_preserves_existing_output_and_removes_temp_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "fixture.wav"
            output.write_bytes(b"keep this recording")
            stderr = io.StringIO()

            def run_ffmpeg(command, check):
                self.assertTrue(check)
                Path(command[-1]).write_bytes(b"not a wav")
                return subprocess.CompletedProcess(command, 0)

            with patch.object(record_fixture.subprocess, "run", side_effect=run_ffmpeg), \
                    redirect_stderr(stderr):
                result = record_fixture.main(["--output", str(output), "--duration", "1"])

            self.assertEqual(result, 1)
            self.assertIn("invalid WAV file", stderr.getvalue())
            self.assertEqual(output.read_bytes(), b"keep this recording")
            self.assertEqual(list(root.glob(f".{output.name}.*")), [])

    def test_cleanup_oserror_does_not_replace_invalid_wav_error(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "fixture.wav"
            output.write_bytes(b"keep this recording")
            temporary_names = []
            unlink_calls = []
            real_unlink = record_fixture.os.unlink

            def run_ffmpeg(command, check):
                self.assertTrue(check)
                temporary_names.append(command[-1])
                Path(command[-1]).write_bytes(b"not a wav")
                return subprocess.CompletedProcess(command, 0)

            def unlink(path):
                unlink_calls.append(path)
                if len(unlink_calls) == 1:
                    return real_unlink(path)
                raise OSError("cannot remove temporary file")

            with patch.object(record_fixture.subprocess, "run", side_effect=run_ffmpeg), \
                    patch.object(record_fixture.os, "unlink", side_effect=unlink), \
                    redirect_stderr(io.StringIO()) as stderr:
                result = record_fixture.main(["--output", str(output), "--duration", "1"])

            self.assertEqual(result, 1)
            self.assertIn("invalid WAV file", stderr.getvalue())
            self.assertEqual(output.read_bytes(), b"keep this recording")
            self.assertEqual(len(unlink_calls), 2)
            real_unlink(temporary_names[0])


if __name__ == "__main__":
    unittest.main()
