"""Analyze WAV fixtures through the production sound feature pipeline."""

import array
import json
import math
import os
import sys
from pathlib import Path
import wave

from audio_events import SemanticEventDetector
from audio_features import Analyzer
from audio_spectrum import Spectrum
from config import Config
from tools.record_fixture import validate_wav


RANGE_LABEL_TYPES = frozenset(("drone", "yell"))
POINT_LABEL_TYPES = frozenset(("beat", "transient"))
LABEL_TYPES = RANGE_LABEL_TYPES | POINT_LABEL_TYPES


def read_wav_hops(path, config):
    """Return validated WAV metadata and unmodified complete PCM hops."""
    path = Path(path)
    with path.open("rb") as retained:
        retained_stat = os.fstat(retained.fileno())
        validated = validate_wav(
            path, expected_rate=config.sample_rate, expected_duration_s=None
        )
        try:
            current_stat = path.stat()
        except OSError as exc:
            raise ValueError("WAV file changed during validation") from exc
        if not os.path.samestat(retained_stat, current_stat):
            raise ValueError("WAV file changed during validation")

        validated_metadata = {
            name: validated[name]
            for name in (
                "sample_rate_hz",
                "channels",
                "sample_width_bytes",
                "frame_count",
            )
        }
        retained.seek(0)
        try:
            with wave.open(retained, "rb") as source:
                metadata = {
                    "sample_rate_hz": source.getframerate(),
                    "channels": source.getnchannels(),
                    "sample_width_bytes": source.getsampwidth(),
                    "frame_count": source.getnframes(),
                }
                if metadata != validated_metadata:
                    raise ValueError("WAV metadata changed during validation")
                raw = source.readframes(metadata["frame_count"])
        except (EOFError, OSError, wave.Error) as exc:
            raise ValueError("WAV file changed during validation") from exc

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
        if label["type"] in RANGE_LABEL_TYPES and (
            "end_ms" not in label or end <= start
        ):
            raise ValueError("Range labels require a positive duration")
        if label["type"] in POINT_LABEL_TYPES and end != start:
            raise ValueError("Point labels cannot have a duration")
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


def _metric_timestamp(row, field):
    value = row.get(field)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError(f"{field} must be a finite non-negative number")
    return value


def _metric_tolerance(value):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError("tolerance_ms must be a finite non-negative number")
    return value


def compare_labels(labels, events, tolerance_ms=250):
    """Compare discrete human labels and detected events one-to-one."""
    tolerance_ms = _metric_tolerance(tolerance_ms)
    ignored_label_types = frozenset(("drone",))
    ignored_event_types = frozenset(("drone_start", "drone_stop"))
    expected_types = {
        row["type"] for row in labels if row["type"] not in ignored_label_types
    }
    detected_types = {
        row["type"] for row in events if row["type"] not in ignored_event_types
    }
    report = {}

    for event_type in sorted(expected_types | detected_types):
        expected = sorted(
            (
                row
                for row in labels
                if row["type"] == event_type
                and row["type"] not in ignored_label_types
            ),
            key=lambda row: _metric_timestamp(row, "start_ms"),
        )
        available = sorted(
            (
                row
                for row in events
                if row["type"] == event_type
                and row["type"] not in ignored_event_types
            ),
            key=lambda row: _metric_timestamp(row, "time_ms"),
        )
        unmatched_events = list(available)
        unmatched_labels = []
        timing_errors = []
        for label in expected:
            label_start = _metric_timestamp(label, "start_ms")
            label_end = _metric_timestamp(
                {"end_ms": label.get("end_ms", label_start)}, "end_ms"
            )
            index = next(
                (
                    index
                    for index, event in enumerate(unmatched_events)
                    if label_start - tolerance_ms
                    <= _metric_timestamp(event, "time_ms")
                    <= label_end + tolerance_ms
                ),
                None,
            )
            if index is None:
                unmatched_labels.append(dict(label))
                continue
            event = unmatched_events.pop(index)
            timing_errors.append(_metric_timestamp(event, "time_ms") - label_start)

        true_positive = len(timing_errors)
        false_positive = len(unmatched_events)
        false_negative = len(unmatched_labels)
        precision = true_positive / (true_positive + false_positive) if (
            true_positive + false_positive
        ) else 0.0
        recall = true_positive / (true_positive + false_negative) if (
            true_positive + false_negative
        ) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (
            precision + recall
        ) else 0.0
        report[event_type] = {
            "true_positive": true_positive,
            "false_positive": false_positive,
            "false_negative": false_negative,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "timing_error_ms": timing_errors,
            "absolute_timing_error_ms": [abs(value) for value in timing_errors],
            "unmatched_labels": unmatched_labels,
            "unmatched_events": [dict(row) for row in unmatched_events],
        }
    return report


def compare_drone(label, events, duration_ms):
    """Compare a human drone interval with its detected start and stop bounds."""
    duration_ms = _metric_timestamp({"duration_ms": duration_ms}, "duration_ms")
    label_start = _metric_timestamp(label, "start_ms")
    label_end = _metric_timestamp(
        {"end_ms": label.get("end_ms", label_start)}, "end_ms"
    )
    if label_end < label_start:
        raise ValueError("Drone label end must not precede its start")

    starts = sorted(
        _metric_timestamp(row, "time_ms")
        for row in events
        if row["type"] == "drone_start"
    )
    stops = sorted(
        _metric_timestamp(row, "time_ms")
        for row in events
        if row["type"] == "drone_stop"
    )
    detected_start = max(0, min(duration_ms, starts[0])) if starts else None
    detected_stop = max(0, min(duration_ms, stops[-1])) if stops else None
    active_start = detected_start if detected_start is not None else duration_ms
    active_stop = detected_stop if detected_stop is not None else active_start
    detected_duration = max(0, active_stop - active_start)
    expected_duration = label_end - label_start
    intersection = max(
        0,
        min(label_end, active_stop) - max(label_start, active_start),
    )
    intersection = min(intersection, expected_duration, detected_duration)
    union = expected_duration + detected_duration - intersection
    false_active = detected_duration - intersection
    false_inactive = expected_duration - intersection
    return {
        "start_error_ms": (
            detected_start - label_start if detected_start is not None else None
        ),
        "stop_error_ms": (
            detected_stop - label_end if detected_stop is not None else None
        ),
        "intersection_over_union": intersection / union if union else 0.0,
        "false_active_ms": false_active,
        "false_inactive_ms": false_inactive,
    }


def analyze_wav(audio_path, labels_path, config=None, fps=20):
    """Run a complete WAV through the same FFT and analyzer as the producer."""
    if (
        isinstance(fps, bool)
        or not isinstance(fps, (int, float))
        or not math.isfinite(fps)
        or fps <= 0
    ):
        raise ValueError("fps must be a positive finite number")
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
    comparison = compare_labels(labels["labels"], events)
    drone_labels = [row for row in labels["labels"] if row["type"] == "drone"]
    if drone_labels:
        comparison["drone"] = compare_drone(
            drone_labels[0], events, info["duration_ms"]
        )
    return {
        "info": info,
        "labels": labels,
        "features": features,
        "events": list(events),
        "comparison": comparison,
        "fps": fps,
    }
