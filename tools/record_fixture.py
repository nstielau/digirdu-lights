"""Record and validate a mono WAV fixture from a Mac audio input."""

import argparse
import math
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import time
import wave


DEFAULT_DURATION_S = 10.0
DEFAULT_CAPTURE_PAD_S = 1.25
DEFAULT_SAMPLE_RATE_HZ = 16000
DEFAULT_CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2
STREAM_MIN_TIMEOUT_S = 5.0
STREAM_WAIT_TIMEOUT_S = 5.0


def _positive_finite_float(value):
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("must be a finite float greater than 0") from exc
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("must be finite and greater than 0")
    return parsed


def _nonnegative_finite_float(value):
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("must be a finite float at least 0") from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError("must be finite and at least 0")
    return parsed


def _positive_int(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _require_positive_int(value, name):
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def build_ffmpeg_command(input_device, output, duration_s, sample_rate_hz, channels):
    """Build the unfiltered ffmpeg command used for avfoundation capture."""
    return [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "avfoundation",
        "-i",
        f":{input_device}",
        "-t",
        str(duration_s),
        "-ar",
        str(sample_rate_hz),
        "-ac",
        str(channels),
        "-sample_fmt",
        "s16",
        str(output),
    ]


def build_ffmpeg_stream_command(
    input_device, capture_duration_s, sample_rate_hz, channels
):
    """Build an avfoundation command that streams raw signed 16-bit PCM."""
    return [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "avfoundation",
        "-i",
        f":{input_device}",
        "-t",
        str(capture_duration_s),
        "-ar",
        str(sample_rate_hz),
        "-ac",
        str(channels),
        "-sample_fmt",
        "s16",
        "-f",
        "s16le",
        "pipe:1",
    ]


def _validate_wav_handle(
    wav_file,
    label,
    expected_rate=DEFAULT_SAMPLE_RATE_HZ,
    expected_channels=DEFAULT_CHANNELS,
    expected_width=2,
    expected_duration_s=DEFAULT_DURATION_S,
    duration_tolerance_s=0.25,
):
    """Validate a WAV file handle and return its basic audio metadata."""
    _require_positive_int(expected_rate, "expected_rate")
    _require_positive_int(expected_channels, "expected_channels")
    _require_positive_int(expected_width, "expected_width")
    if expected_duration_s is not None:
        try:
            valid_expected_duration = (
                math.isfinite(expected_duration_s) and expected_duration_s > 0
            )
        except (TypeError, ValueError, OverflowError):
            valid_expected_duration = False
        if not valid_expected_duration:
            raise ValueError("expected_duration_s must be finite and greater than 0")

    try:
        valid_duration_tolerance = (
            math.isfinite(duration_tolerance_s) and duration_tolerance_s >= 0
        )
    except (TypeError, ValueError, OverflowError):
        valid_duration_tolerance = False
    if not valid_duration_tolerance:
        raise ValueError("duration_tolerance_s must be finite and at least 0")

    try:
        wav_file.seek(0)
        with wave.open(wav_file, "rb") as wav:
            sample_rate_hz = wav.getframerate()
            channels = wav.getnchannels()
            sample_width_bytes = wav.getsampwidth()
            frame_count = wav.getnframes()
            audio = wav.readframes(frame_count)
    except (EOFError, OSError, wave.Error) as exc:
        raise ValueError(f"invalid WAV file: {label}") from exc

    expected_bytes = frame_count * channels * sample_width_bytes
    if len(audio) != expected_bytes:
        raise ValueError(f"truncated WAV file: {label}")
    if sample_rate_hz != expected_rate:
        raise ValueError(
            f"unexpected sample rate: {sample_rate_hz} != {expected_rate}"
        )
    if channels != expected_channels:
        raise ValueError(f"unexpected channel count: {channels} != {expected_channels}")
    if sample_width_bytes != expected_width:
        raise ValueError(
            f"unexpected sample width: {sample_width_bytes} != {expected_width}"
        )

    duration_s = frame_count / sample_rate_hz
    if (
        expected_duration_s is not None
        and abs(duration_s - expected_duration_s) > duration_tolerance_s
    ):
        raise ValueError(
            f"unexpected duration: {duration_s} not within {duration_tolerance_s}"
        )

    return {
        "sample_rate_hz": sample_rate_hz,
        "channels": channels,
        "sample_width_bytes": sample_width_bytes,
        "frame_count": frame_count,
        "duration_s": duration_s,
    }


def validate_wav(
    path,
    expected_rate=DEFAULT_SAMPLE_RATE_HZ,
    expected_channels=DEFAULT_CHANNELS,
    expected_width=2,
    expected_duration_s=DEFAULT_DURATION_S,
    duration_tolerance_s=0.25,
    _file=None,
):
    """Validate a WAV file and return its basic audio metadata."""
    if _file is not None:
        return _validate_wav_handle(
            _file,
            path,
            expected_rate=expected_rate,
            expected_channels=expected_channels,
            expected_width=expected_width,
            expected_duration_s=expected_duration_s,
            duration_tolerance_s=duration_tolerance_s,
        )

    try:
        with open(path, "rb") as wav_file:
            return _validate_wav_handle(
                wav_file,
                path,
                expected_rate=expected_rate,
                expected_channels=expected_channels,
                expected_width=expected_width,
                expected_duration_s=expected_duration_s,
                duration_tolerance_s=duration_tolerance_s,
            )
    except OSError as exc:
        raise ValueError(f"invalid WAV file: {path}") from exc


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list-inputs", action="store_true")
    parser.add_argument("--input", default="0")
    parser.add_argument("--output")
    parser.add_argument(
        "--duration", type=_positive_finite_float, default=DEFAULT_DURATION_S
    )
    parser.add_argument(
        "--capture-pad-s",
        type=_nonnegative_finite_float,
        default=DEFAULT_CAPTURE_PAD_S,
        help="extra capture time to compensate for CoreAudio startup latency",
    )
    parser.add_argument(
        "--sample-rate", type=_positive_int, default=DEFAULT_SAMPLE_RATE_HZ
    )
    parser.add_argument("--channels", type=_positive_int, default=DEFAULT_CHANNELS)
    return parser


def _list_inputs():
    try:
        result = subprocess.run(
            ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
            check=False,
        )
    except OSError as exc:
        if isinstance(exc, FileNotFoundError):
            message = "ffmpeg not found"
        else:
            message = "unable to launch ffmpeg"
        print(f"{message}: {exc}", file=sys.stderr)
        return 1
    return result.returncode


def _stderr_text(stderr):
    if not stderr:
        return ""
    if isinstance(stderr, bytes):
        return stderr.decode("utf-8", errors="replace").strip()
    return str(stderr).strip()


def _close_stream_stdout(process):
    stdout = getattr(process, "stdout", None)
    if stdout is not None:
        try:
            stdout.close()
        finally:
            process.stdout = None


def _read_stderr(stderr_file):
    stderr_file.seek(0)
    return stderr_file.read()


def _finish_stream(process, stderr_file, terminate):
    was_running = process.poll() is None
    if terminate and was_running:
        process.terminate()
    _close_stream_stdout(process)
    try:
        process.wait(timeout=STREAM_WAIT_TIMEOUT_S)
    except subprocess.TimeoutExpired as exc:
        try:
            process.kill()
        except OSError:
            pass
        try:
            process.wait()
        except (OSError, subprocess.TimeoutExpired) as kill_exc:
            stderr = _read_stderr(stderr_file)
            diagnostic = _stderr_text(stderr) or _stderr_text(exc.stderr)
            if diagnostic:
                diagnostic = f": {diagnostic}"
            raise OSError(
                f"ffmpeg did not terminate after timeout{diagnostic}: {kill_exc}"
            ) from kill_exc
        stderr = _read_stderr(stderr_file)
        diagnostic = _stderr_text(stderr) or _stderr_text(exc.stderr)
        if diagnostic:
            diagnostic = f": {diagnostic}"
        raise OSError(f"ffmpeg did not terminate after timeout{diagnostic}") from exc
    stderr = _read_stderr(stderr_file)
    return stderr, was_running


def _read_stdout_chunk(process, remaining):
    try:
        file_descriptor = process.stdout.fileno()
    except (AttributeError, OSError, ValueError):
        return process.stdout.read(remaining)
    return os.read(file_descriptor, remaining)


def _read_requested_pcm(process, byte_count, deadline):
    pcm = bytearray()
    while len(pcm) < byte_count:
        remaining = byte_count - len(pcm)
        timeout = deadline - time.monotonic()
        if timeout <= 0:
            raise TimeoutError("ffmpeg PCM capture timed out before the requested length")
        ready, _, _ = select.select([process.stdout], [], [], timeout)
        if not ready:
            raise TimeoutError("ffmpeg PCM capture timed out before the requested length")
        chunk = _read_stdout_chunk(process, remaining)
        if not chunk:
            break
        pcm.extend(chunk[:remaining])
    return bytes(pcm)


def _record(args):
    output = Path(args.output)
    temporary_file = None
    descriptor = None
    temporary_name = None
    stderr_file = None
    replaced = False

    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{output.name}.",
            suffix=output.suffix or ".wav",
            dir=str(output.parent),
        )
        try:
            temporary_file = os.fdopen(descriptor, "w+b")
        except OSError:
            try:
                os.close(descriptor)
            except OSError:
                pass
            raise
        descriptor = None
        capture_duration_s = args.duration + args.capture_pad_s
        capture_deadline = time.monotonic() + max(
            capture_duration_s, STREAM_MIN_TIMEOUT_S
        )
        stderr_file = tempfile.TemporaryFile()
        process = subprocess.Popen(
            build_ffmpeg_stream_command(
                args.input,
                capture_duration_s,
                args.sample_rate,
                args.channels,
            ),
            stdout=subprocess.PIPE,
            stderr=stderr_file,
        )
        requested_frame_count = round(args.duration * args.sample_rate)
        requested_byte_count = (
            requested_frame_count * args.channels * SAMPLE_WIDTH_BYTES
        )
        try:
            pcm = _read_requested_pcm(process, requested_byte_count, capture_deadline)
        except TimeoutError as exc:
            stderr, _ = _finish_stream(process, stderr_file, terminate=True)
            diagnostic = _stderr_text(stderr)
            message = str(exc)
            if diagnostic:
                message = f"{message}: {diagnostic}"
            raise ValueError(message) from exc
        if len(pcm) != requested_byte_count:
            stderr, _ = _finish_stream(process, stderr_file, terminate=False)
            diagnostic = _stderr_text(stderr)
            message = (
                "ffmpeg stream ended before the requested PCM length "
                f"({len(pcm)} of {requested_byte_count} bytes)"
            )
            if diagnostic:
                message = f"{message}: {diagnostic}"
            raise ValueError(message)

        stderr, was_running = _finish_stream(process, stderr_file, terminate=True)
        returncode = process.returncode
        if not isinstance(returncode, int) or (not was_running and returncode != 0):
            message = f"ffmpeg exited with status {returncode}"
            diagnostic = _stderr_text(stderr)
            if diagnostic:
                message = f"{message}: {diagnostic}"
            raise ValueError(message)
        with wave.open(temporary_file, "wb") as wav:
            wav.setnchannels(args.channels)
            wav.setsampwidth(SAMPLE_WIDTH_BYTES)
            wav.setframerate(args.sample_rate)
            wav.writeframes(pcm)
        temporary_file.flush()
        os.fsync(temporary_file.fileno())
        validate_wav(
            temporary_name,
            expected_rate=args.sample_rate,
            expected_channels=args.channels,
            expected_width=SAMPLE_WIDTH_BYTES,
            expected_duration_s=args.duration,
            _file=temporary_file,
        )
        os.replace(temporary_name, output)
        replaced = True
        return 0
    except (OSError, ValueError) as exc:
        print(f"recording failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if stderr_file is not None:
            stderr_file.close()
        if temporary_file is not None:
            try:
                temporary_file.close()
            except OSError:
                pass
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if temporary_name is not None and not replaced:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass


def main(argv=None):
    args = _parser().parse_args(argv)
    if args.list_inputs:
        return _list_inputs()
    if not args.output:
        _parser().error("--output is required unless --list-inputs is used")
    return _record(args)


if __name__ == "__main__":
    raise SystemExit(main())
