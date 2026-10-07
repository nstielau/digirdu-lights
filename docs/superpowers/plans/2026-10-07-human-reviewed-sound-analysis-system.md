# Human-Reviewed Sound Analysis System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the approved NIC-8 thin slice: a committed 10-second Mac-microphone drone/yell WAV, deterministic offline analysis and validation artifacts, reusable semantic event detection, and a synchronized browser review page.

**Architecture:** Capture is isolated in `tools/record_fixture.py`. The existing `Spectrum`, `Analyzer`, and `CulvertAnimation` remain the analysis/rendering source of truth; a pure `audio_events.py` module adds semantic interval/point events. `tools/sound_review.py` produces inspectable JSON artifacts and a generated local HTML bundle; `web/review.html` provides the reusable synchronized browser view.

**Tech Stack:** Python 3, `wave`, `ffmpeg` CoreAudio input, NumPy host analysis through existing modules, Python `unittest`, vanilla browser JavaScript, existing Node/Playwright web tests, JSON artifacts, and the repository’s current Makefile workflow.

---

## File map

Create:

- `tools/record_fixture.py` — Mac CoreAudio capture, temporary-file handling, WAV validation.
- `audio_events.py` — CircuitPython-compatible semantic event detector.
- `tools/sound_review.py` — WAV framing, offline analysis, event comparison, effect simulation, artifact and HTML generation.
- `web/review.html` — synchronized review page markup.
- `web/review-page.js` — review bundle loading, playhead, waveform, tracks, and LED view.
- `tests/test_record_fixture.py` — recorder command and WAV validation tests.
- `tests/test_audio_events.py` — semantic detector tests.
- `tests/test_sound_review.py` — integration, metrics, artifact, and determinism tests.
- `tests/fixtures/audio/drone-yell-10s.wav` — the approved raw Mac-microphone recording.
- `tests/fixtures/audio/drone-yell-10s.labels.json` — human-reviewed authoritative labels.

Modify:

- `Makefile` — focused `record-review` and `sound-review` commands.
- `README.md` — capture, review, artifact, and limitation documentation.
- `web/test/app.spec.js` — Playwright review-page synchronization and error coverage.

Generated but ignored:

- `.artifacts/sound-review/drone-yell-10s.features.json`
- `.artifacts/sound-review/drone-yell-10s.events.json`
- `.artifacts/sound-review/drone-yell-10s.effects.json`
- `.artifacts/sound-review/drone-yell-10s.run.json`
- `.artifacts/sound-review/drone-yell-10s.html`

---

### Task 1: Add test-first Mac capture and WAV validation

**Files:**
- Create: `tests/test_record_fixture.py`
- Create: `tools/record_fixture.py`
- Modify: `Makefile`

- [ ] **Step 1: Write failing tests for WAV validation and command construction**

Add tests that build temporary WAV files with Python’s `wave` module and assert the public API below:

```python
from tools.record_fixture import build_ffmpeg_command, validate_wav


class RecordFixtureTests(unittest.TestCase):
    def test_validate_wav_returns_exact_capture_metadata(self):
        path = self.write_wav(sample_rate=16000, channels=1, width=2, frames=160000)
        self.assertEqual(validate_wav(path), {
            "sample_rate_hz": 16000,
            "channels": 1,
            "sample_width_bytes": 2,
            "frame_count": 160000,
            "duration_s": 10.0,
        })

    def test_validate_wav_rejects_wrong_format_and_duration(self):
        for kwargs in (
            {"sample_rate": 8000, "channels": 1, "width": 2, "frames": 80000},
            {"sample_rate": 16000, "channels": 2, "width": 2, "frames": 160000},
            {"sample_rate": 16000, "channels": 1, "width": 1, "frames": 160000},
            {"sample_rate": 16000, "channels": 1, "width": 2, "frames": 120000},
        ):
            with self.assertRaises(ValueError):
                validate_wav(self.write_wav(**kwargs))

    def test_ffmpeg_command_has_no_audio_processing_filters(self):
        command = build_ffmpeg_command(0, Path("capture.tmp.wav"), 10.0, 16000, 1)
        self.assertEqual(command[:5], ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f"])
        self.assertIn("avfoundation", command)
        self.assertIn("-ar", command)
        self.assertIn("16000", command)
        self.assertNotIn("-af", command)
        self.assertNotIn("loudnorm", command)
```

Run: `.venv/bin/python -m unittest tests.test_record_fixture -v`  
Expected: FAIL because `tools.record_fixture` does not exist.

- [ ] **Step 2: Implement the minimal recorder API**

Implement `tools/record_fixture.py` with these boundaries:

```python
def build_ffmpeg_command(input_device, output, duration_s, sample_rate_hz, channels):
    return [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-f", "avfoundation", "-i", ":%s" % input_device,
        "-t", str(duration_s), "-ar", str(sample_rate_hz),
        "-ac", str(channels), "-sample_fmt", "s16", str(output),
    ]


def validate_wav(path, expected_rate=16000, expected_channels=1,
                 expected_width=2, expected_duration_s=10.0,
                 duration_tolerance_s=0.25):
    with wave.open(str(path), "rb") as source:
        metadata = {
            "sample_rate_hz": source.getframerate(),
            "channels": source.getnchannels(),
            "sample_width_bytes": source.getsampwidth(),
            "frame_count": source.getnframes(),
        }
    metadata["duration_s"] = metadata["frame_count"] / metadata["sample_rate_hz"]
    if metadata["sample_rate_hz"] != expected_rate:
        raise ValueError("Expected 16000 Hz WAV")
    if metadata["channels"] != expected_channels:
        raise ValueError("Expected mono WAV")
    if metadata["sample_width_bytes"] != expected_width:
        raise ValueError("Expected signed 16-bit WAV")
    if (expected_duration_s is not None
            and abs(metadata["duration_s"] - expected_duration_s) > duration_tolerance_s):
        raise ValueError("Expected a ten-second capture")
    return metadata
```

The CLI must support `--list-inputs`, `--input`, `--output`, `--duration`, `--sample-rate`, and `--channels`. `--list-inputs` invokes `ffmpeg -f avfoundation -list_devices true -i ""` and exits without creating a file. Recording writes `capture.tmp.wav` beside the requested output, checks the subprocess exit code, validates the temporary WAV, then replaces the requested output with `Path.replace`.

- [ ] **Step 3: Run the focused tests**

Run: `.venv/bin/python -m unittest tests.test_record_fixture -v`  
Expected: PASS.

- [ ] **Step 4: Add Makefile entry without touching the fixture yet**

Add:

```make
.PHONY: record-review sound-review
record-review: setup
	$(PY) tools/record_fixture.py --output '$(REVIEW_AUDIO)' --input '$(AUDIO_INPUT)'

sound-review: $(VENV)/.dev-ready
	$(PY) tools/sound_review.py --audio '$(REVIEW_AUDIO)' --labels '$(REVIEW_LABELS)' --output-dir '.artifacts/sound-review'
```

Define defaults near the existing replay variables:

```make
REVIEW_AUDIO ?= tests/fixtures/audio/drone-yell-10s.wav
REVIEW_LABELS ?= tests/fixtures/audio/drone-yell-10s.labels.json
AUDIO_INPUT ?= 0
```

Run: `make -n record-review REVIEW_AUDIO=/tmp/drone-yell-10s.wav AUDIO_INPUT=0`  
Expected: the command prints the recorder invocation without running it.

- [ ] **Step 5: Commit the capture utility**

```bash
git add tools/record_fixture.py tests/test_record_fixture.py Makefile
git commit -m "feat: add validated Mac audio fixture capture"
```

### Task 2: Add the pure semantic event detector

**Files:**
- Create: `tests/test_audio_events.py`
- Create: `audio_events.py`

- [ ] **Step 1: Write failing detector tests**

Use `types.SimpleNamespace` frames so the test does not depend on the renderer:

```python
def frame(time_ms, drone=0.0, vocal=0.0, yell=False, attack=False,
          attack_strength=0.0):
    return SimpleNamespace(
        drone=drone, vocal=vocal, yellEvent=yell,
        attackEvent=attack, attack=attack_strength,
    )


def test_drone_hysteresis_emits_one_start_and_stop(self):
    detector = SemanticEventDetector(DroneEventConfig(
        on_threshold=0.6, off_threshold=0.3,
        start_hold_s=0.10, stop_hold_s=0.20,
    ))
    events = []
    for now, level in ((0, .0), (100, .7), (160, .7), (300, .7),
                       (350, .25), (430, .25), (560, .25)):
        events.extend(detector.update(frame(now, drone=level), now))
    self.assertEqual([event["type"] for event in events], ["drone_start", "drone_stop"])
    self.assertEqual(events[0]["time_ms"], 160)
    self.assertEqual(events[1]["time_ms"], 560)


def test_edge_events_preserve_type_time_and_confidence(self):
    detector = SemanticEventDetector()
    events = detector.update(frame(512, vocal=.8, yell=True,
                                   attack=True, attack_strength=.7), 512)
    self.assertEqual(events, (
        {"type": "yell", "time_ms": 512, "confidence": .8},
        {"type": "transient", "time_ms": 512, "confidence": .7},
    ))
```

Run: `.venv/bin/python -m unittest tests.test_audio_events -v`  
Expected: FAIL because the detector module does not exist.

- [ ] **Step 2: Implement `audio_events.py` minimally**

Define immutable configuration and a stateful detector:

```python
class DroneEventConfig:
    def __init__(self, on_threshold=.45, off_threshold=.25,
                 start_hold_s=.12, stop_hold_s=.30):
        if not 0 <= off_threshold < on_threshold <= 1:
            raise ValueError("Invalid drone hysteresis thresholds")
        if start_hold_s <= 0 or stop_hold_s <= 0:
            raise ValueError("Drone hold times must be positive")
        self.on_threshold = on_threshold
        self.off_threshold = off_threshold
        self.start_hold_s = start_hold_s
        self.stop_hold_s = stop_hold_s


class SemanticEventDetector:
    def __init__(self, drone_config=None):
        self.drone = drone_config or DroneEventConfig()
        self.active = False
        self.pending_since_ms = None
        self.previous_time_ms = None

    def update(self, features, time_ms):
        if self.previous_time_ms is not None and time_ms <= self.previous_time_ms:
            raise ValueError("Event timestamps must increase")
        self.previous_time_ms = time_ms
        events = []
        if getattr(features, "yellEvent", False):
            events.append({"type": "yell", "time_ms": time_ms,
                           "confidence": clamp(features.vocal)})
        if getattr(features, "attackEvent", False):
            events.append({"type": "transient", "time_ms": time_ms,
                           "confidence": clamp(features.attack)})
        events.extend(self._update_drone(features.drone, time_ms))
        return tuple(events)
```

`_update_drone` accumulates time above/below the thresholds, emits `drone_start` after `start_hold_s`, emits `drone_stop` after `stop_hold_s`, and includes `confidence` clamped from the envelope. Add `finish(time_ms)` to close an active drone exactly once at end-of-stream. Keep imports limited to `audio_features.clamp` and the standard library.

- [ ] **Step 3: Run focused and existing detector tests**

Run: `.venv/bin/python -m unittest tests.test_audio_events tests.test_didgeridoo -v`  
Expected: PASS.

- [ ] **Step 4: Commit the semantic layer**

```bash
git add audio_events.py tests/test_audio_events.py
git commit -m "feat: add deterministic semantic audio events"
```

### Task 3: Add WAV framing, labels, and producer-pipeline analysis

**Files:**
- Create: `tests/test_sound_review.py`
- Create: `tools/sound_review.py`

- [ ] **Step 1: Write failing tests for WAV hops and label validation**

Add temporary-WAV tests for the exact host APIs:

```python
def test_read_wav_hops_uses_complete_1024_sample_frames(self):
    path = write_pcm_wav(self.tempdir / "take.wav", 16000,
                         array.array("h", range(2048)))
    info, hops = read_wav_hops(path, Config())
    self.assertEqual(info["sample_rate_hz"], 16000)
    self.assertEqual([len(hop) for hop in hops], [1024, 1024])


def test_load_labels_rejects_invalid_range_and_wrong_rate(self):
    path = self.tempdir / "labels.json"
    path.write_text(json.dumps({
        "audio_file": "take.wav", "sample_rate_hz": 8000,
        "labels": [{"type": "drone", "start_ms": 900, "end_ms": 100}]
    }))
    with self.assertRaises(ValueError):
        load_labels(path, duration_ms=1000, sample_rate_hz=16000)
```

Run: `.venv/bin/python -m unittest tests.test_sound_review.SoundReviewWavTests -v`  
Expected: FAIL because `tools.sound_review` does not exist.

- [ ] **Step 2: Implement the WAV and label APIs**

Implement:

```python
def read_wav_hops(path, config):
    validate_wav(path, expected_rate=config.sample_rate,
                 expected_duration_s=None)
    with wave.open(str(path), "rb") as source:
        frame_count = source.getnframes()
        metadata = {
            "sample_rate_hz": source.getframerate(),
            "channels": source.getnchannels(),
            "sample_width_bytes": source.getsampwidth(),
            "frame_count": frame_count,
        }
        raw = source.readframes(frame_count)
    values = array.array("h")
    values.frombytes(raw)
    expected_bytes = frame_count * 2
    if len(raw) != expected_bytes:
        raise ValueError("Truncated PCM payload")
    if len(values) % config.hop_size:
        raise ValueError("PCM length is not an integral hop count")
    metadata["duration_ms"] = round(frame_count * 1000 / config.sample_rate)
    return metadata, [array.array("h", values[offset:offset + config.hop_size])
                      for offset in range(0, len(values), config.hop_size)]


def load_labels(path, duration_ms, sample_rate_hz):
    document = json.loads(Path(path).read_text())
    if document["sample_rate_hz"] != sample_rate_hz:
        raise ValueError("Label sample rate does not match WAV")
    allowed = {"drone", "yell", "beat", "transient"}
    labels = []
    for label in document["labels"]:
        if label["type"] not in allowed:
            raise ValueError("Unknown label type")
        start = int(label["start_ms"])
        end = int(label.get("end_ms", start))
        if start < 0 or end < start or end > duration_ms:
            raise ValueError("Label is outside audio duration")
        labels.append({"type": label["type"], "start_ms": start, "end_ms": end})
    return {"audio_file": document["audio_file"],
            "sample_rate_hz": sample_rate_hz, "labels": labels}
```

The real implementation must preserve the WAV file’s little-endian signed samples on macOS and avoid converting or normalizing samples. Use a separate `read_wav_hops` metadata validation path so no open `wave.Wave_read` object is used after its context closes.

- [ ] **Step 3: Add the failing end-to-end analysis test**

Create a 10-second temporary WAV with two seconds of zeros followed by a deterministic 93.75 Hz sine drone and a high-frequency burst in the middle. Assert the result of:

```python
result = analyze_wav(audio_path, labels_path, Config(), fps=20)
self.assertEqual(result["features"][0]["time_ms"], 64)
self.assertTrue(all(a["time_ms"] < b["time_ms"]
                    for a, b in zip(result["features"], result["features"][1:])))
self.assertIn(result["events"][0]["type"], {"drone_start", "transient", "yell"})
```

Run: `.venv/bin/python -m unittest tests.test_sound_review.SoundReviewAnalysisTests -v`  
Expected: FAIL because `analyze_wav` is not implemented.

- [ ] **Step 4: Implement the shared pipeline loop**

Implement `analyze_wav(audio_path, labels_path, config=None, fps=20)` as a pure function:

```python
def analyze_wav(audio_path, labels_path, config=None, fps=20):
    config = config or Config()
    info, hops = read_wav_hops(audio_path, config)
    labels = load_labels(labels_path, info["duration_ms"], config.sample_rate)
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
    return {"info": info, "labels": labels, "features": features,
            "events": list(events), "fps": fps}
```

`serialize_features` must emit the fields in the approved spec, convert the five existing band energies into named low/mid/high display values, retain eight spectrum levels, and reject non-finite values before returning. It must not mutate the `AudioFeatures` object after serialization.

- [ ] **Step 5: Run focused and full Python tests**

Run: `.venv/bin/python -m unittest tests.test_sound_review tests.test_audio_events tests.test_didgeridoo -v`  
Expected: PASS.

- [ ] **Step 6: Commit the analysis runner**

```bash
git add tools/sound_review.py tests/test_sound_review.py
git commit -m "feat: analyze WAV fixtures through producer pipeline"
```

### Task 4: Add deterministic label/event comparison metrics

**Files:**
- Modify: `tests/test_sound_review.py`
- Modify: `tools/sound_review.py`

- [ ] **Step 1: Write failing metric tests**

Use hand-built records with exact expected results:

```python
def test_compare_events_reports_one_match_one_false_positive_and_one_miss(self):
    labels = [
        {"type": "yell", "start_ms": 1000, "end_ms": 1200},
        {"type": "yell", "start_ms": 3000, "end_ms": 3200},
    ]
    detected = [
        {"type": "yell", "time_ms": 1100, "confidence": .9},
        {"type": "yell", "time_ms": 5000, "confidence": .7},
    ]
    report = compare_labels(labels, detected, tolerance_ms=250)
    self.assertEqual(report["yell"]["true_positive"], 1)
    self.assertEqual(report["yell"]["false_positive"], 1)
    self.assertEqual(report["yell"]["false_negative"], 1)
    self.assertAlmostEqual(report["yell"]["precision"], .5)
    self.assertAlmostEqual(report["yell"]["recall"], .5)
    self.assertAlmostEqual(report["yell"]["f1"], .5)


def test_compare_drone_reports_bounds_and_time_errors(self):
    report = compare_drone(
        {"start_ms": 2000, "end_ms": 8000},
        [{"type": "drone_start", "time_ms": 2200},
         {"type": "drone_stop", "time_ms": 7600}],
        duration_ms=10000,
    )
    self.assertEqual(report["start_error_ms"], 200)
    self.assertEqual(report["stop_error_ms"], -400)
    self.assertAlmostEqual(report["intersection_over_union"], 5400 / 6000)
```

Run: `.venv/bin/python -m unittest tests.test_sound_review.SoundReviewMetricTests -v`  
Expected: FAIL because metric functions are not implemented.

- [ ] **Step 2: Implement one-to-one event matching and drone interval metrics**

Implement these APIs in `tools/sound_review.py`:

```python
def compare_labels(labels, events, tolerance_ms=250):
    report = {}
    relevant_types = sorted({row["type"] for row in labels}
                            | {row["type"] for row in events})
    for event_type in relevant_types:
        expected = sorted((row for row in labels if row["type"] == event_type),
                          key=lambda row: row["start_ms"])
        available = sorted((row for row in events if row["type"] == event_type),
                           key=lambda row: row["time_ms"])
        matched = []
        unmatched_events = list(available)
        for label in expected:
            index = next((i for i, event in enumerate(unmatched_events)
                          if label["start_ms"] - tolerance_ms <= event["time_ms"]
                          <= label["end_ms"] + tolerance_ms), None)
            if index is not None:
                event = unmatched_events.pop(index)
                matched.append(event["time_ms"] - label["start_ms"])
        tp = len(matched)
        fp = len(unmatched_events)
        fn = len(expected) - tp
        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        report[event_type] = {
            "true_positive": tp, "false_positive": fp, "false_negative": fn,
            "precision": precision, "recall": recall,
            "f1": 2 * precision * recall / max(precision + recall, 1e-12),
            "timing_error_ms": matched,
            "absolute_timing_error_ms": [abs(value) for value in matched],
        }
    return report


def compare_drone(label, events, duration_ms):
    starts = [row["time_ms"] for row in events if row["type"] == "drone_start"]
    stops = [row["time_ms"] for row in events if row["type"] == "drone_stop"]
    detected_start = max(0, min(duration_ms, starts[0])) if starts else None
    detected_stop = max(0, min(duration_ms, stops[-1])) if stops else None
    active_start = detected_start if detected_start is not None else duration_ms
    active_stop = detected_stop if detected_stop is not None else active_start
    intersection = max(0, min(label["end_ms"], active_stop)
                       - max(label["start_ms"], active_start))
    union = max(label["end_ms"], active_stop) - min(label["start_ms"], active_start)
    false_active = max(0, active_stop - active_start - intersection)
    false_inactive = (label["end_ms"] - label["start_ms"]) - intersection
    return {
        "start_error_ms": (detected_start - label["start_ms"]
                            if detected_start is not None else None),
        "stop_error_ms": (detected_stop - label["end_ms"]
                           if detected_stop is not None else None),
        "intersection_over_union": intersection / max(union, 1),
        "false_active_ms": false_active,
        "false_inactive_ms": false_inactive,
    }
```

Handle absent start/stop events with explicit `None` errors and full false-active/false-inactive accounting; never divide by zero. Include the comparison report in `analyze_wav` without modifying `labels`.

- [ ] **Step 3: Run tests and commit metrics**

Run: `.venv/bin/python -m unittest tests.test_sound_review -v`  
Expected: PASS.

```bash
git add tools/sound_review.py tests/test_sound_review.py
git commit -m "feat: compare detected events with reviewed labels"
```

### Task 5: Add deterministic effect simulation and artifact manifests

**Files:**
- Modify: `tests/test_sound_review.py`
- Modify: `tools/sound_review.py`

- [ ] **Step 1: Write failing effect/artifact tests**

Add tests asserting multiple node distances, five audio effects, eight grouped RGB pixels, and stable serialization:

```python
def test_render_effects_groups_renderer_output_for_three_nodes(self):
    features = fixture_feature_frames()
    effects = render_effects(features, Config(), fps=20,
                             node_distances_mm=(-5000, 0, 5000),
                             virtual_wave_speed_mm_s=10000)
    self.assertEqual(effects["node_distances_mm"], [-5000, 0, 5000])
    self.assertEqual(set(effects["effects"]), {"Spectrum", "Ember", "Aurora", "Ripple", "Chroma"})
    self.assertEqual(len(effects["frames"]["Spectrum"]["0"][0]["pixels_rgb"]), 8)
    self.assertTrue(all(len(pixel) == 3 for pixel in effects["frames"]["Spectrum"]["0"][0]["pixels_rgb"]))


def test_artifacts_are_byte_stable_for_same_input(self):
    first = build_artifacts(fixture_audio, fixture_labels, output_dir, Config())
    second = build_artifacts(fixture_audio, fixture_labels, output_dir, Config())
    self.assertEqual(first["features_json"], second["features_json"])
    self.assertEqual(first["events_json"], second["events_json"])
    self.assertEqual(first["effects_json"], second["effects_json"])
    self.assertEqual(first["run_json"], second["run_json"])
```

Run: `.venv/bin/python -m unittest tests.test_sound_review.SoundReviewEffectTests -v`  
Expected: FAIL because effect/artifact functions are not implemented.

- [ ] **Step 2: Implement delayed node simulation and grouping**

Use the existing 32-pixel renderer and group four adjacent pixels into one review pixel:

```python
def group_pixels(grb_bytes, groups=8):
    pixels = [grb_bytes[offset:offset + 3]
              for offset in range(0, len(grb_bytes), 3)]
    width = len(pixels) // groups
    result = []
    for group in range(groups):
        members = pixels[group * width:(group + 1) * width]
        # Convert renderer GRB bytes to browser-facing RGB and average each group.
        result.append([
            round(sum(pixel[1] for pixel in members) / len(members)),
            round(sum(pixel[0] for pixel in members) / len(members)),
            round(sum(pixel[2] for pixel in members) / len(members)),
        ])
    return result


def render_effects(feature_frames, config, fps=20,
                   node_distances_mm=(-5000, 0, 5000),
                   virtual_wave_speed_mm_s=10000):
    # For each effect and node, sample the causal feature timeline at
    # time - abs(distance)/virtual_wave_speed, then render one frame.
    return {"fps": fps, "node_distances_mm": list(node_distances_mm),
            "virtual_wave_speed_mm_s": virtual_wave_speed_mm_s,
            "effects": list(EFFECT_NAMES[:5]), "frames": frames}
```

Create a fresh `CulvertAnimation(Config(effect_index=effect_id))` for every effect/node pair, feed `AudioFeatures` reconstructed from the serialized frame at each delayed sample, call `render(frame, 1 / fps)`, and group the resulting bytes. Do not use wall-clock time, random values, or current date in derived artifacts.

- [ ] **Step 3: Implement JSON artifact writing and manifest hashes**

Add:

```python
def build_artifacts(audio_path, labels_path, output_dir, config=None):
    config = config or Config()
    node_distances_mm = (-5000, 0, 5000)
    virtual_wave_speed_mm_s = 10000
    fps = 20
    result = analyze_wav(audio_path, labels_path, config)
    result["effects"] = render_effects(
        result["features"], config, fps=fps,
        node_distances_mm=node_distances_mm,
        virtual_wave_speed_mm_s=virtual_wave_speed_mm_s)
    result["comparison"] = compare_labels(result["labels"]["labels"], result["events"])
    stem = Path(audio_path).stem
    output_dir.mkdir(parents=True, exist_ok=True)
    module_hashes = source_hashes((
        "audio_spectrum.py", "audio_features.py", "audio_events.py",
        "animation.py", "effects.py", "config.py", "tools/sound_review.py"))
    # Serialize with sorted keys and compact separators so reruns are byte-stable.
    write_json(output_dir / (stem + ".features.json"), result["features"])
    write_json(output_dir / (stem + ".events.json"), result["events"])
    write_json(output_dir / (stem + ".effects.json"), result["effects"])
    write_json(output_dir / (stem + ".run.json"), manifest_without_wall_clock(
        audio_path, labels_path, result, config or Config(),
        module_hashes, node_distances_mm, fps, virtual_wave_speed_mm_s))
    return paths
```

The manifest includes SHA-256 values for the WAV, labels, `audio_spectrum.py`, `audio_features.py`, `audio_events.py`, `animation.py`, `effects.py`, `config.py`, and `tools/sound_review.py`, plus all analysis/effect parameters and `random_seed: 0`. Capture metadata may contain wall-clock time in a separate non-deterministic file, but derived run JSON must not.

- [ ] **Step 4: Run focused/full Python tests and commit**

Run: `.venv/bin/python -m unittest tests.test_sound_review tests.test_replay tests.test_effects -v`  
Expected: PASS.

```bash
git add tools/sound_review.py tests/test_sound_review.py
git commit -m "feat: render deterministic sound review artifacts"
```

### Task 6: Build the synchronized browser review page

**Files:**
- Create: `web/review.html`
- Create: `web/review-page.js`
- Modify: `web/test/app.spec.js`

- [ ] **Step 1: Write the failing browser tests**

Add a `review.html` Playwright test that fulfills `/test-review.json` with a small deterministic bundle and checks the page contract:

```javascript
test('review page synchronizes all tracks from one playhead', async ({page}) => {
  await page.route('**/test-review.json', route => route.fulfill({json: {
    duration_ms: 1000,
    audio_url: '/fixture.wav',
    waveform: [0, .2, .8, .3],
    labels: [{type: 'drone', start_ms: 0, end_ms: 1000}],
    events: [{type: 'yell', time_ms: 500, confidence: .9}],
    features: [{time_ms: 500, volume: .8, drone: .7, vocal: .9, transient_strength: .2}],
    effects: {node_distances_mm: [0], frames: {Spectrum: {'0': [
      {time_ms: 500, pixels_rgb: [[1, 2, 3], [1, 2, 3], [1, 2, 3], [1, 2, 3],
                                     [1, 2, 3], [1, 2, 3], [1, 2, 3], [1, 2, 3]]}
    ]}}}
  }}));
  await page.goto('/review.html?data=/test-review.json');
  await page.getByRole('slider', {name: 'Position'}).fill('500');
  await page.getByRole('slider', {name: 'Position'}).dispatchEvent('input');
  await expect(page.locator('#review-time')).toHaveText('0.50 s');
  await expect(page.locator('[data-track-cursor="waveform"]')).toHaveAttribute('data-time-ms', '500');
  await expect(page.locator('#review-events')).toContainText('yell');
  await expect(page.locator('#review-led')).toHaveAttribute('data-time-ms', '500');
});

test('review page reports missing bundle instead of showing empty tracks', async ({page}) => {
  await page.route('**/missing-review.json', route => route.fulfill({status: 503, body: 'unavailable'}));
  await page.goto('/review.html?data=/missing-review.json');
  await expect(page.locator('#review-status')).toContainText('could not load');
});
```

Run: `npm run test:browser -- --grep 'review page'`  
Expected: FAIL because the page and selectors do not exist.

- [ ] **Step 2: Add the page structure with accessible controls**

Create `web/review.html` with these stable IDs and labels:

```html
<main class="review-page">
  <h1>Human-reviewed sound analysis</h1>
  <p id="review-status" role="status" aria-live="polite">Loading review…</p>
  <audio id="review-audio" preload="auto"></audio>
  <button id="review-play" type="button">Play</button>
  <button id="review-replay" type="button">Replay label</button>
  <label>Position <input id="review-position" aria-label="Position" type="range" min="0" value="0"></label>
  <output id="review-time">0.00 s</output>
  <label>Zoom <input id="review-zoom" aria-label="Zoom" type="range" min="1" max="8" value="1"></label>
  <section id="review-waveform" data-track-cursor="waveform"></section>
  <section id="review-labels"></section>
  <section id="review-events"></section>
  <section id="review-features"></section>
  <section id="review-led" data-time-ms="0"></section>
</main>
<script type="module" src="./review-page.js"></script>
```

- [ ] **Step 3: Implement one canonical playhead in `web/review-page.js`**

Implement these functions:

```javascript
const state = {bundle: null, timeMs: 0, playing: false};

function setTime(timeMs) {
  state.timeMs = Math.max(0, Math.min(state.bundle.duration_ms, timeMs));
  audio.currentTime = state.timeMs / 1000;
  position.value = state.timeMs;
  timeOutput.textContent = `${(state.timeMs / 1000).toFixed(2)} s`;
  renderWaveformCursor(state.timeMs);
  renderFeatureCursor(state.timeMs);
  renderEventHighlight(state.timeMs);
  renderLedFrame(state.timeMs);
}

audio.addEventListener('timeupdate', () => {
  if (state.playing) setTime(audio.currentTime * 1000);
});
position.addEventListener('input', () => setTime(Number(position.value)));
play.addEventListener('click', async () => {
  state.playing = !state.playing;
  if (state.playing) await audio.play(); else audio.pause();
});
```

The page must load a bundle URL from `?data=/test-review.json` or the documented generated default, set the audio source, set slider max to `duration_ms`, render labels/events/features/LED frames, and put every fetch/audio failure into `#review-status`. `Replay label` seeks to the currently selected label’s start minus 500 ms and pauses after the label end plus 500 ms. Zoom changes only the timeline viewport; it must not change canonical timestamps.

- [ ] **Step 4: Run the browser tests and fix responsive layout**

Run: `npm run test:browser -- --grep 'review page'`  
Expected: PASS in the existing desktop, mobile Chromium, and mobile WebKit projects with no horizontal overflow.

- [ ] **Step 5: Commit the review page**

```bash
git add web/review.html web/review-page.js web/test/app.spec.js
git commit -m "feat: add synchronized sound review page"
```

### Task 7: Record, human-review, and commit the real fixture

**Files:**
- Create: `tests/fixtures/audio/drone-yell-10s.wav`
- Create: `tests/fixtures/audio/drone-yell-10s.labels.json`
- Modify: `README.md`

- [ ] **Step 1: Discover the Mac microphone input**

Run:

```bash
ffmpeg -f avfoundation -list_devices true -i ""
```

Expected: the output lists the Mac microphone input index. Choose the input that identifies the Mac’s built-in microphone; do not record until the selected input is clear.

- [ ] **Step 2: Record the take with the approved cue**

Run:

```bash
make record-review AUDIO_INPUT=0 \
  REVIEW_AUDIO=tests/fixtures/audio/drone-yell-10s.wav
```

Perform: 2 seconds of silence, a sustained drone from approximately 2 seconds, one yell centered near 5 seconds, then drone until the 10-second stop. The command must validate and atomically install the WAV.

- [ ] **Step 3: Generate the initial label file without detector output**

Create `tests/fixtures/audio/drone-yell-10s.labels.json` with the validated file name, `sample_rate_hz: 16000`, a drone range from the reviewed onset to the reviewed end, and a provisional yell range based only on the waveform. Do not copy detected timestamps into the file.

- [ ] **Step 4: Run the review generator and inspect the waveform**

Run:

```bash
make sound-review \
  REVIEW_AUDIO=tests/fixtures/audio/drone-yell-10s.wav \
  REVIEW_LABELS=tests/fixtures/audio/drone-yell-10s.labels.json
```

Open `.artifacts/sound-review/drone-yell-10s.html` through the local static server documented by the README. Use the waveform and replay controls to set the yell range precisely in the labels file. Re-run the generator and confirm the metrics reference the updated human file.

- [ ] **Step 5: Add the fixture integration assertions**

Extend `tests/test_sound_review.py` to load the committed WAV and labels, assert the exact WAV header, assert the label file remains unchanged after `build_artifacts`, assert all event times are ordered and in range, and assert the derived files are repeatable.

- [ ] **Step 6: Document the capture/review workflow and limits**

Add README sections covering:

- the fixture path and why this one short recording is committed;
- Mac microphone selection and the exact cue;
- `make record-review` and `make sound-review` commands;
- ignored derived artifact paths;
- human labels as authoritative;
- the fact that one recording does not establish classification accuracy or hardware replay equivalence.

- [ ] **Step 7: Commit the reviewed fixture and documentation**

```bash
git add tests/fixtures/audio/drone-yell-10s.wav \
  tests/fixtures/audio/drone-yell-10s.labels.json README.md tests/test_sound_review.py
git commit -m "test: add human-reviewed drone yell fixture"
```

### Task 8: Run complete verification and hand off

**Files:**
- No new files; verify the complete branch.

- [ ] **Step 1: Run focused Python verification**

```bash
.venv/bin/python -m unittest \
  tests.test_record_fixture \
  tests.test_audio_events \
  tests.test_sound_review \
  tests.test_didgeridoo \
  tests.test_replay \
  tests.test_effects -v
```

Expected: all tests pass.

- [ ] **Step 2: Run repository checks**

```bash
make check
```

Expected: syntax compilation, all Python tests, and `git diff --check` pass.

- [ ] **Step 3: Run browser checks**

```bash
npm test
npm run test:browser -- --grep 'review page|saved replay|missing replay'
```

Expected: Node tests and relevant Playwright projects pass without overflow.

- [ ] **Step 4: Verify deterministic artifacts and clean scope**

```bash
make sound-review
cp -R .artifacts/sound-review /tmp/sound-review-first
make sound-review
diff -ru /tmp/sound-review-first .artifacts/sound-review
git status --short
git diff --check
```

Expected: the artifact diff is empty; only the approved source, fixture, labels, docs, and tests are tracked; `.artifacts` remains ignored.

- [ ] **Step 5: Review limitations before claiming completion**

Report the recorded fixture duration and label ranges, event metrics, deterministic rerun result, and browser test result. Explicitly state that this slice does not validate the complete corpus, live hardware replay, culvert RF coverage, or generalized didgeridoo event recognition.
