"""Record and validate a mono WAV fixture from a Mac audio input."""

import argparse
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import wave


DEFAULT_DURATION_S = 10.0
DEFAULT_CAPTURE_PAD_S = 1.25
DEFAULT_SAMPLE_RATE_HZ = 16000
DEFAULT_CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2
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


def validate_wav(
    path,
    expected_rate=DEFAULT_SAMPLE_RATE_HZ,
    expected_channels=DEFAULT_CHANNELS,
    expected_width=2,
    expected_duration_s=DEFAULT_DURATION_S,
    duration_tolerance_s=0.25,
):
    """Validate a WAV file and return its basic audio metadata."""
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
        with wave.open(str(path), "rb") as wav:
            sample_rate_hz = wav.getframerate()
            channels = wav.getnchannels()
            sample_width_bytes = wav.getsampwidth()
            frame_count = wav.getnframes()
            audio = wav.readframes(frame_count)
    except (EOFError, OSError, wave.Error) as exc:
        raise ValueError(f"invalid WAV file: {path}") from exc

    expected_bytes = frame_count * channels * sample_width_bytes
    if len(audio) != expected_bytes:
        raise ValueError(f"truncated WAV file: {path}")
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
    parser.add_argument("--sample-rate", type=int, default=DEFAULT_SAMPLE_RATE_HZ)
    parser.add_argument("--channels", type=int, default=DEFAULT_CHANNELS)
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


def _finish_stream(process, terminate):
    if terminate:
        process.terminate()
    _close_stream_stdout(process)
    try:
        _, stderr = process.communicate(timeout=STREAM_WAIT_TIMEOUT_S)
    except subprocess.TimeoutExpired as exc:
        try:
            process.kill()
        except OSError:
            pass
        try:
            _, stderr = process.communicate()
        except OSError as kill_exc:
            diagnostic = _stderr_text(exc.stderr)
            if diagnostic:
                diagnostic = f": {diagnostic}"
            raise OSError(
                f"ffmpeg did not terminate after timeout{diagnostic}: {kill_exc}"
            ) from kill_exc
        diagnostic = _stderr_text(exc.stderr) or _stderr_text(stderr)
        if diagnostic:
            diagnostic = f": {diagnostic}"
        raise OSError(f"ffmpeg did not terminate after timeout{diagnostic}") from exc
    return stderr


def _read_requested_pcm(process, byte_count):
    pcm = bytearray()
    while len(pcm) < byte_count:
        remaining = byte_count - len(pcm)
        chunk = process.stdout.read(remaining)
        if not chunk:
            break
        pcm.extend(chunk[:remaining])
    return bytes(pcm)


def _record(args):
    output = Path(args.output)
    temporary_name = None

    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{output.name}.",
            suffix=output.suffix or ".wav",
            dir=str(output.parent),
        )
        os.close(descriptor)
        os.unlink(temporary_name)
        process = subprocess.Popen(
            build_ffmpeg_stream_command(
                args.input,
                args.duration + args.capture_pad_s,
                args.sample_rate,
                args.channels,
            ),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        requested_frame_count = round(args.duration * args.sample_rate)
        requested_byte_count = (
            requested_frame_count * args.channels * SAMPLE_WIDTH_BYTES
        )
        pcm = _read_requested_pcm(process, requested_byte_count)
        if len(pcm) != requested_byte_count:
            stderr = _finish_stream(process, terminate=False)
            diagnostic = _stderr_text(stderr)
            message = (
                "ffmpeg stream ended before the requested PCM length "
                f"({len(pcm)} of {requested_byte_count} bytes)"
            )
            if diagnostic:
                message = f"{message}: {diagnostic}"
            raise ValueError(message)

        _finish_stream(process, terminate=True)
        with wave.open(temporary_name, "wb") as wav:
            wav.setnchannels(args.channels)
            wav.setsampwidth(SAMPLE_WIDTH_BYTES)
            wav.setframerate(args.sample_rate)
            wav.writeframes(pcm)
        validate_wav(
            temporary_name,
            expected_rate=args.sample_rate,
            expected_channels=args.channels,
            expected_width=SAMPLE_WIDTH_BYTES,
            expected_duration_s=args.duration,
        )
        os.replace(temporary_name, output)
        return 0
    except subprocess.CalledProcessError as exc:
        return exc.returncode or 1
    except (OSError, ValueError) as exc:
        print(f"recording failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if temporary_name is not None:
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
