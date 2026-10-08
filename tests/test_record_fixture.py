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


class RecordingBytesIO(io.BytesIO):
    def __init__(self, value=b""):
        super().__init__(value)
        self.read_sizes = []

    def read(self, size=-1):
        self.read_sizes.append(size)
        return super().read(size)


class FakeStreamProcess:
    def __init__(self, stdout=b"", stderr=b"", returncode=0, running=True):
        self.stdout = RecordingBytesIO(stdout)
        self.stderr_bytes = stderr
        self.returncode = returncode
        self.running = running
        self.terminated = False
        self.killed = False
        self.wait_calls = []

    def poll(self):
        return None if self.running else self.returncode

    def terminate(self):
        self.terminated = True
        self.running = False

    def kill(self):
        self.killed = True
        self.running = False

    def wait(self, timeout=None):
        self.wait_calls.append(timeout)
        self.running = False
        return self.returncode

class TimeoutStreamProcess(FakeStreamProcess):
    def wait(self, timeout=None):
        self.wait_calls.append(timeout)
        if timeout is not None:
            raise subprocess.TimeoutExpired(
                "ffmpeg", timeout, stderr=self.stderr_bytes
            )
        self.running = False
        return self.returncode


def fake_popen(process, commands=None):
    def launch(command, stdout, stderr):
        if commands is not None:
            commands.append(command)
        stderr.write(process.stderr_bytes)
        stderr.flush()
        return process

    return launch


def read_wav_pcm(path):
    with wave.open(str(path), "rb") as wav:
        params = wav.getparams()
        pcm = wav.readframes(wav.getnframes())
    return params, pcm


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

    def test_validate_wav_rejects_nonpositive_expected_audio_integers(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "fixture.wav"
            write_wav(path, duration_s=1.0)

            cases = (
                ("expected_rate", 0),
                ("expected_rate", -1),
                ("expected_channels", 0),
                ("expected_channels", -1),
                ("expected_width", 0),
                ("expected_width", -1),
            )
            for name, value in cases:
                with self.subTest(name=name, value=value):
                    with self.assertRaisesRegex(ValueError, "positive integer"):
                        record_fixture.validate_wav(path, **{name: value})


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

    def test_build_ffmpeg_stream_command_writes_raw_pcm_to_stdout(self):
        command = record_fixture.build_ffmpeg_stream_command(3, 2.25, 16000, 1)

        self.assertEqual(command[:15], [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "avfoundation",
            "-i",
            ":3",
            "-t",
            "2.25",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-sample_fmt",
        ])
        self.assertEqual(command[14:16], ["-sample_fmt", "s16"])
        self.assertEqual(command[-3:], ["-f", "s16le", "pipe:1"])


class CliTests(unittest.TestCase):
    def setUp(self):
        self.select_patcher = patch.object(
            record_fixture.select,
            "select",
            side_effect=lambda readable, _, __, ___: (readable, [], []),
        )
        self.select_mock = self.select_patcher.start()
        self.addCleanup(self.select_patcher.stop)

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

    def test_sample_rate_and_channels_cli_reject_nonpositive_values(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "fixture.wav"
            for option in ("--sample-rate", "--channels"):
                for raw in ("0", "-1"):
                    with self.subTest(option=option, raw=raw), redirect_stderr(io.StringIO()):
                        try:
                            with patch.object(
                                record_fixture.subprocess,
                                "Popen",
                                side_effect=AssertionError("capture should not launch"),
                            ):
                                record_fixture.main(
                                    ["--output", str(output), option, raw]
                                )
                        except SystemExit as exc:
                            self.assertEqual(exc.code, 2)
                        else:
                            self.fail("invalid audio format integer was accepted")

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

    def test_exact_length_stream_writes_requested_pcm_and_discards_extra_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "fixture.wav"
            output.write_bytes(b"old recording")
            requested_pcm = b"\x01\x02" * 16000
            process = FakeStreamProcess(requested_pcm + b"extra samples")
            stdout = process.stdout

            with patch.object(record_fixture.subprocess, "Popen", return_value=process) as popen:
                result = record_fixture.main(
                    ["--input", "2", "--output", str(output), "--duration", "1"]
                )

            self.assertEqual(result, 0)
            params, pcm = read_wav_pcm(output)
            self.assertEqual(params.nchannels, 1)
            self.assertEqual(params.sampwidth, 2)
            self.assertEqual(params.framerate, 16000)
            self.assertEqual(params.nframes, 16000)
            self.assertEqual(pcm, requested_pcm)
            self.assertTrue(process.terminated)
            self.assertEqual(stdout.read_sizes, [len(requested_pcm)])
            self.assertIs(
                popen.call_args.kwargs["stdout"], record_fixture.subprocess.PIPE
            )
            self.assertIsNot(
                popen.call_args.kwargs["stderr"], record_fixture.subprocess.PIPE
            )

    def test_short_stream_preserves_existing_output_and_reports_stderr(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "fixture.wav"
            output.write_bytes(b"keep this recording")
            process = FakeStreamProcess(b"\0" * (16000 * 2 - 2), b"input stopped early")
            stderr = io.StringIO()

            with patch.object(record_fixture.subprocess, "Popen", side_effect=fake_popen(process)), \
                    redirect_stderr(stderr):
                result = record_fixture.main(
                    ["--output", str(output), "--duration", "1"]
                )

            self.assertEqual(result, 1)
            self.assertIn("ended before", stderr.getvalue())
            self.assertIn("input stopped early", stderr.getvalue())
            self.assertEqual(output.read_bytes(), b"keep this recording")
            self.assertEqual(list(root.glob(f".{output.name}.*")), [])

    def test_positive_ffmpeg_exit_after_exact_stream_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "fixture.wav"
            output.write_bytes(b"keep this recording")
            process = FakeStreamProcess(
                b"\0" * (16000 * 2),
                b"ffmpeg rejected the input",
                returncode=1,
                running=False,
            )
            stderr = io.StringIO()

            with patch.object(record_fixture.subprocess, "Popen", side_effect=fake_popen(process)), \
                    redirect_stderr(stderr):
                result = record_fixture.main(
                    ["--output", str(output), "--duration", "1"]
                )

            self.assertEqual(result, 1)
            self.assertIn("status 1", stderr.getvalue())
            self.assertIn("ffmpeg rejected the input", stderr.getvalue())
            self.assertEqual(output.read_bytes(), b"keep this recording")
            self.assertEqual(list(root.glob(f".{output.name}.*")), [])
            self.assertFalse(process.terminated)

    def test_intentional_termination_accepts_positive_ffmpeg_exit(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "fixture.wav"
            process = FakeStreamProcess(
                b"\0" * (16000 * 2), returncode=255, running=True
            )

            with patch.object(record_fixture.subprocess, "Popen", return_value=process):
                result = record_fixture.main(
                    ["--output", str(output), "--duration", "1"]
                )

            self.assertEqual(result, 0)
            self.assertTrue(process.terminated)
            self.assertEqual(
                record_fixture.validate_wav(output, expected_duration_s=1.0)["frame_count"],
                16000,
            )

    def test_stalled_stream_times_out_and_terminates_without_replacing_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "fixture.wav"
            output.write_bytes(b"keep this recording")
            process = FakeStreamProcess(b"", running=True)
            stderr = io.StringIO()

            with patch.object(record_fixture.subprocess, "Popen", side_effect=fake_popen(process)), \
                    patch.object(record_fixture.select, "select", return_value=([], [], [])) as select_mock, \
                    redirect_stderr(stderr):
                result = record_fixture.main(
                    ["--output", str(output), "--duration", "1"]
                )

            self.assertEqual(result, 1)
            self.assertIn("timed out", stderr.getvalue())
            self.assertTrue(process.terminated)
            self.assertTrue(process.wait_calls)
            self.assertTrue(select_mock.called)
            self.assertEqual(output.read_bytes(), b"keep this recording")
            self.assertEqual(list(root.glob(f".{output.name}.*")), [])

    def test_termination_timeout_kills_stream_and_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "fixture.wav"
            output.write_bytes(b"keep this recording")
            process = TimeoutStreamProcess(
                b"\0" * (16000 * 2), b"ffmpeg did not stop"
            )
            stderr = io.StringIO()

            with patch.object(record_fixture.subprocess, "Popen", side_effect=fake_popen(process)), \
                    redirect_stderr(stderr):
                result = record_fixture.main(
                    ["--output", str(output), "--duration", "1"]
                )

            self.assertEqual(result, 1)
            self.assertTrue(process.killed)
            self.assertIn("did not terminate", stderr.getvalue())
            self.assertIn("ffmpeg did not stop", stderr.getvalue())
            self.assertEqual(output.read_bytes(), b"keep this recording")
            self.assertEqual(list(root.glob(f".{output.name}.*")), [])

    def test_stream_launch_oserror_preserves_existing_output_cleanly(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "fixture.wav"
            output.write_bytes(b"keep this recording")
            stderr = io.StringIO()
            launch_error = OSError("cannot execute ffmpeg")

            with patch.object(record_fixture.subprocess, "Popen", side_effect=launch_error), \
                    redirect_stderr(stderr):
                result = record_fixture.main(["--output", str(output)])

            self.assertEqual(result, 1)
            self.assertIn("cannot execute ffmpeg", stderr.getvalue())
            self.assertEqual(output.read_bytes(), b"keep this recording")
            self.assertEqual(list(root.glob(f".{output.name}.*")), [])

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
            process = FakeStreamProcess(b"\0" * (16000 * 2))

            def popen_ffmpeg(command, stdout, stderr):
                commands.append(command)
                self.assertIs(stdout, record_fixture.subprocess.PIPE)
                self.assertIsNot(stderr, record_fixture.subprocess.PIPE)
                return process

            with patch.object(record_fixture.subprocess, "Popen", side_effect=popen_ffmpeg):
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
            self.assertEqual(commands[0][-1], "pipe:1")

    def test_record_keeps_mkstemp_path_until_atomic_cleanup(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "fixture.wav"
            unlink_calls = []
            real_unlink = record_fixture.os.unlink
            process = FakeStreamProcess(b"\0" * (16000 * 2))

            def unlink(path):
                unlink_calls.append(path)
                return real_unlink(path)

            with patch.object(record_fixture.subprocess, "Popen", return_value=process), \
                    patch.object(record_fixture.tempfile, "TemporaryFile", return_value=io.BytesIO()), \
                    patch.object(record_fixture.os, "unlink", side_effect=unlink):
                result = record_fixture.main(
                    ["--output", str(output), "--duration", "1"]
                )

            self.assertEqual(result, 0)
            self.assertEqual(len(unlink_calls), 1)

    def test_record_default_capture_pad_extends_ffmpeg_stream_duration(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "fixture.wav"
            commands = []
            process = FakeStreamProcess(b"\0" * (16000 * 2))

            def popen_ffmpeg(command, stdout, stderr):
                commands.append(command)
                return process

            with patch.object(record_fixture.subprocess, "Popen", side_effect=popen_ffmpeg):
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
            failure = OSError("ffmpeg launch failed")
            with patch.object(record_fixture.subprocess, "Popen", side_effect=failure):
                result = record_fixture.main(["--output", str(output)])

            self.assertEqual(result, 1)
            self.assertEqual(output.read_bytes(), b"keep this recording")
            self.assertEqual(list(root.glob(f".{output.name}.*")), [])

    def test_invalid_wav_preserves_existing_output_and_removes_temp_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "fixture.wav"
            output.write_bytes(b"keep this recording")
            stderr = io.StringIO()
            process = FakeStreamProcess(b"\0" * (16000 * 2))

            with patch.object(record_fixture.subprocess, "Popen", side_effect=fake_popen(process)), \
                    patch.object(record_fixture, "validate_wav", side_effect=ValueError("invalid WAV file")), \
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
            process = FakeStreamProcess(b"\0" * (16000 * 2))

            def unlink(path):
                unlink_calls.append(path)
                if len(unlink_calls) == 1:
                    return real_unlink(path)
                raise OSError("cannot remove temporary file")

            with patch.object(record_fixture.subprocess, "Popen", return_value=process), \
                    patch.object(record_fixture, "validate_wav", side_effect=ValueError("invalid WAV file")), \
                    patch.object(record_fixture.tempfile, "TemporaryFile", return_value=io.BytesIO()), \
                    patch.object(record_fixture.os, "unlink", side_effect=unlink), \
                    redirect_stderr(io.StringIO()) as stderr:
                result = record_fixture.main(["--output", str(output), "--duration", "1"])

            self.assertEqual(result, 1)
            self.assertIn("invalid WAV file", stderr.getvalue())
            self.assertEqual(output.read_bytes(), b"keep this recording")
            self.assertEqual(len(unlink_calls), 1)


if __name__ == "__main__":
    unittest.main()
