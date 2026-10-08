"""Analyze WAV fixtures through the production sound feature pipeline."""

import array
import hashlib
import json
import math
import os
import subprocess
import sys
from pathlib import Path
import wave

from audio_events import SemanticEventDetector
from audio_features import Analyzer, AudioFeatures
from audio_spectrum import Spectrum
from animation import CulvertAnimation
from config import Config
from effects import EFFECT_NAMES
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


_MAX_METRIC_MS = 1_000_000_000_000


def _metric_number(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite non-negative number")
    if value < 0 or value > _MAX_METRIC_MS:
        raise ValueError(
            f"{field} must be between 0 and {_MAX_METRIC_MS} milliseconds"
        )
    try:
        finite = math.isfinite(value)
    except OverflowError as exc:
        raise ValueError(f"{field} must be a finite non-negative number") from exc
    if not finite:
        raise ValueError(f"{field} must be a finite non-negative number")
    return value


def _metric_timestamp(row, field):
    if not isinstance(row, dict):
        raise ValueError("Metric records must be objects")
    return _metric_number(row.get(field), field)


def _metric_tolerance(value):
    return _metric_number(value, "tolerance_ms")


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
        label_starts = []
        candidates = []
        event_times = [
            _metric_timestamp(event, "time_ms") for event in available
        ]
        for label in expected:
            label_start = _metric_timestamp(label, "start_ms")
            label_end = _metric_timestamp(
                {"end_ms": label.get("end_ms", label_start)}, "end_ms"
            )
            if label_end < label_start:
                raise ValueError("Label end must not precede its start")
            label_starts.append(label_start)
            candidates.append(
                [
                    event_index
                    for event_index, event_time in enumerate(event_times)
                    if label_start - tolerance_ms
                    <= event_time
                    <= label_end + tolerance_ms
                ]
            )

        event_to_label = [None] * len(available)

        def assign(label_index, seen_events):
            for event_index in candidates[label_index]:
                if seen_events[event_index]:
                    continue
                seen_events[event_index] = True
                previous_label = event_to_label[event_index]
                if previous_label is None or assign(previous_label, seen_events):
                    event_to_label[event_index] = label_index
                    return True
            return False

        for label_index in range(len(expected)):
            assign(label_index, [False] * len(available))

        label_to_event = [None] * len(expected)
        for event_index, label_index in enumerate(event_to_label):
            if label_index is not None:
                label_to_event[label_index] = event_index

        unmatched_labels = [
            dict(label)
            for label_index, label in enumerate(expected)
            if label_to_event[label_index] is None
        ]
        unmatched_events = [
            dict(event)
            for event_index, event in enumerate(available)
            if event_to_label[event_index] is None
        ]
        timing_errors = [
            event_times[event_index] - label_starts[label_index]
            for label_index, event_index in enumerate(label_to_event)
            if event_index is not None
        ]
        true_positive = len(expected) - len(unmatched_labels)
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
            "unmatched_events": unmatched_events,
        }
    return report


def _merge_intervals(intervals):
    merged = []
    for start, stop in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], stop))
        else:
            merged.append((start, stop))
    return merged


def _interval_intersection(left, right):
    left_index = 0
    right_index = 0
    total = 0
    while left_index < len(left) and right_index < len(right):
        start = max(left[left_index][0], right[right_index][0])
        stop = min(left[left_index][1], right[right_index][1])
        total += max(0, stop - start)
        if left[left_index][1] <= right[right_index][1]:
            left_index += 1
        else:
            right_index += 1
    return total


def _drone_label_spans(label, duration_ms):
    if isinstance(label, dict):
        labels = (label,)
    elif isinstance(label, (list, tuple)):
        labels = tuple(label)
    else:
        raise ValueError("Drone label must be an object or array of objects")

    spans = []
    for row in labels:
        if not isinstance(row, dict):
            raise ValueError("Drone labels must be objects")
        start = _metric_timestamp(row, "start_ms")
        stop = _metric_timestamp(row, "end_ms")
        if stop <= start:
            raise ValueError("Drone labels must have positive duration")
        if stop > duration_ms:
            raise ValueError("Drone label is outside audio duration")
        spans.append((start, stop))
    if not spans:
        raise ValueError("At least one drone label is required")
    return _merge_intervals(spans)


def _detected_drone_spans(events, duration_ms):
    records = []
    starts = []
    stops = []
    for index, row in enumerate(events):
        event_type = row["type"]
        if event_type not in ("drone_start", "drone_stop"):
            continue
        time_ms = _metric_timestamp(row, "time_ms")
        records.append(
            (
                time_ms,
                index,
                event_type,
            )
        )
        if event_type == "drone_start":
            starts.append(time_ms)
        else:
            stops.append(time_ms)

    active_start = None
    spans = []
    for time_ms, _index, event_type in sorted(records):
        time_ms = max(0, min(duration_ms, time_ms))
        if event_type == "drone_start":
            if active_start is None:
                active_start = time_ms
            continue
        if active_start is not None:
            if time_ms <= active_start:
                raise ValueError("Detected drone intervals must have positive duration")
            spans.append((active_start, time_ms))
            active_start = None
    return (
        _merge_intervals(spans),
        max(0, min(duration_ms, min(starts))) if starts else None,
        max(0, min(duration_ms, max(stops))) if stops else None,
    )


def compare_drone(label, events, duration_ms):
    """Compare one or more human drone intervals with detected spans."""
    duration_ms = _metric_number(duration_ms, "duration_ms")
    expected = _drone_label_spans(label, duration_ms)
    detected, detected_start, detected_stop = _detected_drone_spans(
        events, duration_ms
    )
    expected_duration = sum(stop - start for start, stop in expected)
    detected_duration = sum(stop - start for start, stop in detected)
    intersection = _interval_intersection(expected, detected)
    union = expected_duration + detected_duration - intersection
    return {
        "start_error_ms": (
            detected_start - expected[0][0] if detected_start is not None else None
        ),
        "stop_error_ms": (
            detected_stop - expected[-1][1] if detected_stop is not None else None
        ),
        "intersection_over_union": intersection / union if union else 0.0,
        "false_active_ms": detected_duration - intersection,
        "false_inactive_ms": expected_duration - intersection,
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
            drone_labels[0] if len(drone_labels) == 1 else drone_labels,
            events,
            info["duration_ms"],
        )
    return {
        "info": info,
        "labels": labels,
        "features": features,
        "events": list(events),
        "comparison": comparison,
        "fps": fps,
    }


def _positive_finite(value, name):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError(f"{name} must be a positive finite number")
    return value


def _finite_number(value, name):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise ValueError(f"{name} must be a finite number")
    return value


def group_pixels(grb_bytes, groups=8):
    """Convert equally sized GRB renderer groups to averaged RGB pixels."""
    if (
        isinstance(groups, bool)
        or not isinstance(groups, int)
        or groups <= 0
    ):
        raise ValueError("groups must be a positive integer")
    if not isinstance(grb_bytes, (bytes, bytearray, memoryview)):
        raise ValueError("grb_bytes must be a byte sequence")
    if len(grb_bytes) == 0 or len(grb_bytes) % 3:
        raise ValueError("Renderer output must contain complete RGB pixels")
    pixel_count = len(grb_bytes) // 3
    if pixel_count < groups or pixel_count % groups:
        raise ValueError("Renderer pixels must divide evenly into groups")

    pixels = [
        grb_bytes[offset : offset + 3]
        for offset in range(0, len(grb_bytes), 3)
    ]
    width = pixel_count // groups
    result = []
    for group in range(groups):
        members = pixels[group * width : (group + 1) * width]
        result.append(
            [
                round(sum(pixel[1] for pixel in members) / len(members)),
                round(sum(pixel[0] for pixel in members) / len(members)),
                round(sum(pixel[2] for pixel in members) / len(members)),
            ]
        )
    return result


def _feature_frame(frame, time_ms):
    """Reconstruct the renderer's feature object from one serialized frame."""
    if not isinstance(frame, dict):
        raise ValueError("Feature frames must be objects")
    result = AudioFeatures()
    result.volume = _normalized(frame.get("volume"), "volume")
    result.drone = _normalized(frame.get("drone"), "drone")
    result.growl = _normalized(frame.get("growl"), "growl")
    result.vocal = _normalized(frame.get("vocal"), "vocal")
    result.attack = _normalized(
        frame.get("transient_strength"), "transient strength"
    )
    spectrum = frame.get("spectrum")
    if not isinstance(spectrum, (list, tuple)) or len(spectrum) != 8:
        raise ValueError("Feature frames must contain eight spectrum levels")
    result.spectrum = tuple(
        _normalized(value, f"spectrum level {index}")
        for index, value in enumerate(spectrum)
    )
    active = frame.get("active")
    calibrating = frame.get("calibrating")
    if not isinstance(active, bool) or not isinstance(calibrating, bool):
        raise ValueError("Feature state flags must be booleans")
    result.active = active
    result.calibrating = calibrating
    if not _integer_timestamp(time_ms):
        raise ValueError("Feature frame timestamps must be integers")
    return result


def _validate_feature_frames(feature_frames):
    if not isinstance(feature_frames, (list, tuple)):
        raise ValueError("feature_frames must be a list")
    previous = None
    for frame in feature_frames:
        if not isinstance(frame, dict):
            raise ValueError("Feature frames must be objects")
        time_ms = frame.get("time_ms")
        if not _integer_timestamp(time_ms) or time_ms < 0:
            raise ValueError("Feature frame timestamps must be non-negative integers")
        if previous is not None and time_ms <= previous:
            raise ValueError("Feature frame timestamps must increase")
        previous = time_ms
    return feature_frames


def _sample_feature(feature_frames, target_ms):
    """Return the newest frame no later than target_ms, or a silent frame."""
    selected = None
    for frame in feature_frames:
        if frame["time_ms"] > target_ms:
            break
        selected = frame
    if selected is None:
        return _feature_frame(
            {
                "volume": 0.0,
                "drone": 0.0,
                "growl": 0.0,
                "vocal": 0.0,
                "transient_strength": 0.0,
                "spectrum": (0.0,) * 8,
                "active": False,
                "calibrating": False,
            },
            0,
        ), None
    return _feature_frame(selected, selected["time_ms"]), selected["time_ms"]


def _renderer_config(config, effect_id):
    overrides = dict(vars(config))
    overrides["effect_index"] = effect_id
    return Config(**overrides)


def render_effects(
    feature_frames,
    config,
    fps=20,
    node_distances_mm=(-5000, 0, 5000),
    virtual_wave_speed_mm_s=10000,
):
    """Render deterministic eight-pixel views for five audio effects."""
    fps = _positive_finite(fps, "fps")
    virtual_wave_speed_mm_s = _positive_finite(
        virtual_wave_speed_mm_s, "virtual_wave_speed_mm_s"
    )
    if not isinstance(node_distances_mm, (list, tuple)) or not node_distances_mm:
        raise ValueError("node_distances_mm must be a non-empty sequence")
    distances = []
    for distance in node_distances_mm:
        distances.append(_finite_number(distance, "node distance"))
    feature_frames = _validate_feature_frames(feature_frames)

    duration_ms = feature_frames[-1]["time_ms"] if feature_frames else 0
    frame_count = max(1, int(math.ceil(duration_ms * fps / 1000.0)))
    frame_times = [round(index * 1000.0 / fps) for index in range(frame_count)]
    delays_ms = [
        abs(distance) * 1000.0 / virtual_wave_speed_mm_s for distance in distances
    ]
    effects = {}
    for effect_id, effect_name in enumerate(EFFECT_NAMES[:5]):
        by_node = {}
        for node_index, delay_ms in enumerate(delays_ms):
            renderer = CulvertAnimation(_renderer_config(config, effect_id))
            rendered = []
            for time_ms in frame_times:
                source_target_ms = max(0.0, time_ms - delay_ms)
                source_time_ms = int(math.floor(source_target_ms))
                features, selected_time_ms = _sample_feature(
                    feature_frames, source_time_ms
                )
                pixels = renderer.render(features, 1.0 / fps)
                rendered.append(
                    {
                        "time_ms": time_ms,
                        "source_time_ms": selected_time_ms,
                        "pixels_rgb": group_pixels(pixels),
                    }
                )
            by_node[str(node_index)] = rendered
        effects[effect_name] = by_node

    return {
        "fps": fps,
        "node_distances_mm": distances,
        "virtual_wave_speed_mm_s": virtual_wave_speed_mm_s,
        "pixel_channel_order": "rgb",
        "effects": list(EFFECT_NAMES[:5]),
        "frames": effects,
    }


def _json_value(value):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Configuration contains a non-finite value")
        return value
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    raise ValueError(f"Configuration contains unsupported value: {type(value).__name__}")


def _config_values(config):
    values = {}
    for name in dir(config):
        if name.startswith("_"):
            continue
        value = getattr(config, name)
        if callable(value):
            continue
        values[name] = _json_value(value)
    return values


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_hashes(paths):
    """Return stable SHA-256 hashes for repository source paths."""
    root = Path(__file__).resolve().parent.parent
    hashes = {}
    for path in paths:
        path = Path(path)
        resolved = path if path.is_absolute() else root / path
        if not resolved.is_file():
            raise ValueError(f"Source file does not exist: {path}")
        hashes[path.as_posix()] = _sha256(resolved)
    return hashes


def write_json(path, value):
    """Write compact, sorted JSON with stable UTF-8 and a final newline."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    path.write_text(encoded + "\n")
    return path


def _git_commit():
    root = Path(__file__).resolve().parent.parent
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    commit = result.stdout.strip()
    return commit if result.returncode == 0 and commit else None


def manifest_without_wall_clock(
    audio_path,
    labels_path,
    result,
    config,
    module_hashes,
    node_distances_mm,
    fps,
    virtual_wave_speed_mm_s,
):
    """Build run metadata without filesystem times or other wall-clock data."""
    manifest = {
        "schema_version": 1,
        "audio_file": Path(audio_path).name,
        "labels_file": Path(labels_path).name,
        "source_sha256": {
            "audio": _sha256(audio_path),
            "labels": _sha256(labels_path),
        },
        "module_sha256": dict(module_hashes),
        "sample_rate_hz": result["info"]["sample_rate_hz"],
        "frame_count": result["info"]["frame_count"],
        "duration_ms": result["info"]["duration_ms"],
        "analysis": {
            "sample_rate_hz": config.sample_rate,
            "fft_size": config.fft_size,
            "hop_size": config.hop_size,
            "window": "hann",
            "feature_fps": result["fps"],
            "config": _config_values(config),
            "detector": {
                "drone_on_threshold": 0.45,
                "drone_off_threshold": 0.25,
                "drone_start_hold_s": 0.12,
                "drone_stop_hold_s": 0.30,
            },
        },
        "effect_engine": {
            "version": 1,
            "renderer": "CulvertAnimation",
            "effects": list(EFFECT_NAMES[:5]),
            "fps": fps,
            "node_distances_mm": list(node_distances_mm),
            "virtual_wave_speed_mm_s": virtual_wave_speed_mm_s,
            "pixel_groups": 8,
            "pixel_channel_order": "rgb",
        },
        "random_seed": 0,
        "event_count": len(result["events"]),
        "comparison": result["comparison"],
    }
    commit = _git_commit()
    if commit is not None:
        manifest["git_commit"] = commit
    return manifest


def build_artifacts(audio_path, labels_path, output_dir, config=None):
    """Analyze a WAV and write deterministic feature, event, effect, and run JSON."""
    config = config or Config()
    node_distances_mm = (-5000, 0, 5000)
    virtual_wave_speed_mm_s = 10000
    fps = 20
    result = analyze_wav(audio_path, labels_path, config, fps=fps)
    result["effects"] = render_effects(
        result["features"],
        config,
        fps=fps,
        node_distances_mm=node_distances_mm,
        virtual_wave_speed_mm_s=virtual_wave_speed_mm_s,
    )
    output_dir = Path(output_dir)
    stem = Path(audio_path).stem
    module_hashes = source_hashes(
        (
            "audio_spectrum.py",
            "audio_features.py",
            "audio_events.py",
            "animation.py",
            "effects.py",
            "config.py",
            "tools/sound_review.py",
        )
    )
    paths = {
        "features_json": output_dir / f"{stem}.features.json",
        "events_json": output_dir / f"{stem}.events.json",
        "effects_json": output_dir / f"{stem}.effects.json",
        "run_json": output_dir / f"{stem}.run.json",
    }
    write_json(paths["features_json"], result["features"])
    write_json(paths["events_json"], result["events"])
    write_json(paths["effects_json"], result["effects"])
    write_json(
        paths["run_json"],
        manifest_without_wall_clock(
            audio_path,
            labels_path,
            result,
            config,
            module_hashes,
            node_distances_mm,
            fps,
            virtual_wave_speed_mm_s,
        ),
    )
    return paths
