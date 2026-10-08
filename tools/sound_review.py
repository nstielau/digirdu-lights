"""Analyze WAV fixtures through the production sound feature pipeline."""

import array
import json
import math
import sys
from pathlib import Path
import wave

from audio_events import SemanticEventDetector
from audio_features import Analyzer
from audio_spectrum import Spectrum
from config import Config
from tools.record_fixture import validate_wav


LABEL_TYPES = frozenset(("drone", "yell", "beat", "transient"))


def read_wav_hops(path, config):
    """Return validated WAV metadata and unmodified complete PCM hops."""
    validated = validate_wav(
        path, expected_rate=config.sample_rate, expected_duration_s=None
    )
    metadata = {
        "sample_rate_hz": validated["sample_rate_hz"],
        "channels": validated["channels"],
        "sample_width_bytes": validated["sample_width_bytes"],
        "frame_count": validated["frame_count"],
    }

    with wave.open(str(path), "rb") as source:
        raw = source.readframes(metadata["frame_count"])

    expected_bytes = metadata["frame_count"] * 2
    if len(raw) != expected_bytes:
        raise ValueError("Truncated PCM payload")
    values = array.array("h")
    values.frombytes(raw)
    if sys.byteorder != "little":
        values.byteswap()
    if len(values) % config.hop_size:
        raise ValueError("PCM length is not an integral hop count")

    metadata["duration_ms"] = round(
        metadata["frame_count"] * 1000 / config.sample_rate
    )
    hops = [
        array.array("h", values[offset : offset + config.hop_size])
        for offset in range(0, len(values), config.hop_size)
    ]
    return metadata, hops


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _integer_timestamp(value):
    return isinstance(value, int) and not isinstance(value, bool)


def load_labels(path, duration_ms, sample_rate_hz):
    """Load and strictly validate the human-authored label document."""
    if not _integer_timestamp(duration_ms) or duration_ms < 0:
        raise ValueError("duration_ms must be a non-negative integer")
    if not _integer_timestamp(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be a positive integer")

    document = json.loads(Path(path).read_text(), object_pairs_hook=_unique_object)
    if not isinstance(document, dict):
        raise ValueError("Label document must be an object")
    if set(document) != {"audio_file", "sample_rate_hz", "labels"}:
        raise ValueError("Label document has invalid fields")
    if not isinstance(document["audio_file"], str) or not document["audio_file"]:
        raise ValueError("Label audio_file must be a non-empty string")
    if not _integer_timestamp(document["sample_rate_hz"]):
        raise ValueError("Label sample rate must be an integer")
    if document["sample_rate_hz"] != sample_rate_hz:
        raise ValueError("Label sample rate does not match WAV")
    if not isinstance(document["labels"], list):
        raise ValueError("labels must be an array")

    labels = []
    for label in document["labels"]:
        if not isinstance(label, dict):
            raise ValueError("Each label must be an object")
        if not {"type", "start_ms"} <= set(label) <= {
            "type",
            "start_ms",
            "end_ms",
        }:
            raise ValueError("Label has invalid fields")
        if not isinstance(label["type"], str) or label["type"] not in LABEL_TYPES:
            raise ValueError("Unknown label type")
        start = label["start_ms"]
        end = label.get("end_ms", start)
        if not _integer_timestamp(start) or not _integer_timestamp(end):
            raise ValueError("Label timestamps must be integers")
        if start < 0 or end < start or end > duration_ms:
            raise ValueError("Label is outside audio duration")
        labels.append({"type": label["type"], "start_ms": start, "end_ms": end})

    return {
        "audio_file": document["audio_file"],
        "sample_rate_hz": sample_rate_hz,
        "labels": labels,
    }


def _normalized(value, name):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0.0 <= value <= 1.0
    ):
        raise ValueError(f"{name} must be a finite normalized number")
    return float(value)


def _finite_nonnegative(value, name):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError(f"{name} must be a finite non-negative number")
    return float(value)


def serialize_features(features, raw, time_ms):
    """Copy one producer feature frame into the review artifact schema."""
    if not _integer_timestamp(time_ms) or time_ms < 0:
        raise ValueError("time_ms must be a non-negative integer")
    if not isinstance(features.calibrating, bool) or not isinstance(
        features.active, bool
    ):
        raise ValueError("Feature state flags must be booleans")

    bands = tuple(
        _finite_nonnegative(value, f"band energy {index}")
        for index, value in enumerate(raw["bands"])
    )
    if len(bands) != 5:
        raise ValueError("Expected five band energies")
    total = sum(bands)
    ratios = tuple(value / total for value in bands) if total else (0.0,) * 5

    spectrum = tuple(
        _normalized(value, f"spectrum level {index}")
        for index, value in enumerate(features.spectrum)
    )
    if len(spectrum) != 8:
        raise ValueError("Expected eight spectrum levels")

    result = {
        "time_ms": time_ms,
        "calibrating": features.calibrating,
        "volume": _normalized(features.volume, "volume"),
        "drone": _normalized(features.drone, "drone"),
        "growl": _normalized(features.growl, "growl"),
        "vocal": _normalized(features.vocal, "vocal"),
        "transient_strength": _normalized(features.attack, "transient strength"),
        "low_energy": ratios[0],
        "mid_energy": sum(ratios[1:3]),
        "high_energy": sum(ratios[3:5]),
        "spectrum": spectrum,
        "active": features.active,
        "raw_rms": _finite_nonnegative(raw["rms"], "raw RMS"),
        "dominant_frequency_hz": _finite_nonnegative(
            raw["drone_hz"], "dominant frequency"
        ),
    }
    for name in ("low_energy", "mid_energy", "high_energy"):
        result[name] = _normalized(result[name], name)
    return result


def analyze_wav(audio_path, labels_path, config=None, fps=20):
    """Run a complete WAV through the same FFT and analyzer as the producer."""
    config = config or Config()
    info, hops = read_wav_hops(audio_path, config)
    labels = load_labels(labels_path, info["duration_ms"], config.sample_rate)
    if labels["audio_file"] != Path(audio_path).name:
        raise ValueError("Label audio_file does not match WAV")

    spectrum = Spectrum(config)
    analyzer = Analyzer(config)
    detector = SemanticEventDetector()
    features = []
    events = []
    for index, samples in enumerate(hops, 1):
        raw = spectrum.push(samples)
        if raw is None:
            continue
        time_ms = round(index * config.hop_size * 1000 / config.sample_rate)
        current = analyzer.update(raw, config.hop_size / config.sample_rate)
        features.append(serialize_features(current, raw, time_ms))
        events.extend(detector.update(current, time_ms))
    events.extend(detector.finish(info["duration_ms"]))
    return {
        "info": info,
        "labels": labels,
        "features": features,
        "events": list(events),
        "fps": fps,
    }
