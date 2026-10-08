"""Record and validate a mono WAV fixture from a Mac audio input."""

import argparse
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


def validate_wav(
    path,
    expected_rate=DEFAULT_SAMPLE_RATE_HZ,
    expected_channels=DEFAULT_CHANNELS,
    expected_width=2,
    expected_duration_s=DEFAULT_DURATION_S,
    duration_tolerance_s=0.25,
):
    """Validate a WAV file and return its basic audio metadata."""
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
    parser.add_argument("--duration", type=float, default=DEFAULT_DURATION_S)
    parser.add_argument(
        "--capture-pad-s",
        type=float,
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
        subprocess.run(
            build_ffmpeg_command(
                args.input,
                temporary_name,
                args.duration + args.capture_pad_s,
                args.sample_rate,
                args.channels,
            ),
            check=True,
        )
        validate_wav(
            temporary_name,
            expected_rate=args.sample_rate,
            expected_channels=args.channels,
            expected_width=2,
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
