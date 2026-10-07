# Human-Reviewed Sound Analysis System Design

Date: 2026-10-07  
Issue: NIC-8  
Status: Approved design for the first thin slice

## Goal

Build a deterministic, reviewable vertical slice for one 10-second recording from the Mac microphone: a sustained didgeridoo drone with one yell near the middle. The slice must preserve the raw WAV, keep human labels authoritative, reuse the producer’s existing FFT/feature/effect code, compare detected events with the reviewed labels, and expose one synchronized browser review view.

This is the first fixture and validation loop for NIC-8. It is not the complete golden corpus, annotation editor, CBOR replay format, or hardware replay implementation.

## Design decisions

The capture path uses the already-installed `ffmpeg` CoreAudio input on macOS. Capture is raw: no normalization, filtering, resampling after capture, or other signal processing is allowed. The capture command writes a temporary file, validates the result as mono, 16-bit signed PCM at 16 kHz and approximately 10 seconds, then atomically renames it to the fixture path.

The committed fixture is an explicit exception to the repository’s general rule against committing recordings, authorized by the NIC-8 request. Only this short review fixture is committed in this slice; the future corpus remains subject to its own storage decision.

The offline runner reuses `audio_spectrum.Spectrum`, `audio_features.Analyzer`, `config.Config`, and `animation.CulvertAnimation`. It does not maintain a separate desktop implementation of FFT, normalization, smoothing, or visual rendering. A new pure `audio_events.py` module provides semantic event conversion that can later be imported by the CircuitPython producer.

The initial semantic output includes `drone_start`, `drone_stop`, `yell`, and `transient`. Existing `Analyzer` edge flags are the source for yell and transient events. Drone events use configurable hysteresis and minimum-duration rules over the existing normalized drone envelope. Growl, beat, and the richer future label vocabulary are schema-compatible but not required for this fixture.

Derived artifacts use JSON first so a human can inspect and diff them. CBOR export is intentionally deferred until the schema and replay contract are stable.

## Capture and review flow

1. List or select a macOS CoreAudio input.
2. Print a cue for a two-second quiet calibration section, followed by a sustained drone, one yell centered near five seconds, and drone through the ten-second end.
3. Record directly to a temporary WAV with `ffmpeg`.
4. Validate sample rate, channel count, sample width, frame count, and duration. Reject invalid or short captures without replacing an existing fixture.
5. Store the validated source at `tests/fixtures/audio/drone-yell-10s.wav` and write capture metadata separately.
6. Generate an initial label file with the known drone range and review the waveform to place the yell range precisely.
7. Run offline analysis against the WAV and labels.
8. Generate feature, event, comparison, effect, and run artifacts under ignored `.artifacts/sound-review/`.
9. Open the generated review page and verify the shared playhead, human labels, detected overlays, feature tracks, and LED output.
10. Commit the WAV, reviewed labels, source changes, tests, and documentation. Do not commit derived `.artifacts` output.

The human review step is mandatory. The detector may suggest a yell time, but it cannot modify or replace the label file.

## Components and file boundaries

### Capture

`tools/record_fixture.py` owns CoreAudio device discovery, the countdown/cue, `ffmpeg` invocation, temporary-file handling, and WAV header validation. It has no analysis logic.

### Semantic event layer

`audio_events.py` owns a small stateful detector with explicit configuration:

- drone on/off thresholds;
- minimum drone-on and drone-off durations;
- event cooldowns where applicable;
- timestamp and confidence construction.

The detector consumes normalized `AudioFeatures` frames and returns immutable event dictionaries. It must run on CPython and CircuitPython-compatible Python without dependencies beyond the standard language subset already used by the firmware.

### Offline runner

`tools/sound_review.py` owns WAV reading, contiguous PCM hops, analysis timestamps, semantic event collection, label parsing, matching metrics, feature serialization, effect simulation, and review-bundle generation.

Each complete 1024-sample hop is passed to `Spectrum.push`. A feature timestamp is the end of the hop in milliseconds, matching the live producer’s post-capture processing point. The first incomplete FFT window is withheld exactly as it is on-device. `Analyzer.update` receives the configured hop duration.

The runner renders the existing `CulvertAnimation` at a deterministic review frame rate. The core renderer continues to use the configured 32-pixel installation model; the review artifact exposes eight representative RGB pixels by grouping the 32-pixel output into eight equal spatial groups. At least three virtual node distances are rendered, including the producer midpoint and two opposing culvert positions. The artistic wave speed comes from `Config`; physical sound speed is not used.

### Browser review

`web/review.html` provides the static structure and `web/review-page.js` owns loading and interaction. The generated review bundle provides the audio URL/data, downsampled waveform, human labels, features, detected events, comparison metrics, and eight-pixel frames for each virtual node.

The browser has one canonical playhead in milliseconds. Audio playback position, waveform cursor, every track cursor, event emphasis, feature marker, and LED frame selection are derived from that value. Scrubbing updates all views. The first slice supports play/pause, scrubbing, zoom, and replay around a selected label; label editing is deferred until the fixture review flow is proven.

## Artifact schemas

The authoritative label file is `tests/fixtures/audio/drone-yell-10s.labels.json`:

```json
{
  "audio_file": "drone-yell-10s.wav",
  "sample_rate_hz": 16000,
  "labels": [
    {"type": "drone", "start_ms": 2000, "end_ms": 10000},
    {"type": "yell", "start_ms": 4700, "end_ms": 5400}
  ]
}
```

The actual yell timestamps are set by human waveform review after capture. Every label has a known type and either a range (`drone`, `yell`) or a point (`beat`, `transient`); this first fixture uses only the two range types.

The feature artifact contains ordered frames with `time_ms`, `calibrating`, `volume`, `drone`, `growl`, `vocal`, `transient_strength`, `low_energy`, `mid_energy`, `high_energy`, `spectrum`, and `active` fields. Values intended for display or comparison are normalized to `0.0..1.0`; raw RMS and dominant frequency are retained in explicitly named fields.

The event artifact contains ordered records with `type`, `time_ms`, `confidence`, and optional `end_ms`. `drone_start` and `drone_stop` form an interval; `yell` and `transient` are point events.

The effects artifact contains a fixed frame rate, node distances, eight RGB pixels per node per frame, and the source feature timestamp used for each frame. RGB bytes use the same GRB-to-logical conversion as the renderer output after grouping; the schema names the channel order explicitly.

The run manifest contains:

- source WAV relative path and SHA-256;
- label file SHA-256;
- sample rate, FFT size, hop size, Hann-window declaration, and analysis frame rate;
- complete detector thresholds and timing parameters;
- effect-engine version/configuration and virtual node distances;
- source-module hashes and git commit when available;
- a fixed random seed field, set to `0` for this deterministic slice.

No generated artifact is allowed to overwrite the label file.

## Comparison rules

Point/range event matching is one-to-one and deterministic: sort both sides by timestamp, match the earliest unmatched detected event to the earliest unmatched human label of the same type when the detection lies inside the label expanded by the configured tolerance, then continue. The default tolerance is 250 ms. For a range label, onset timing error is detected time minus label start; a detection inside the range is a true positive even if its onset is later than the label start.

The report includes true positives, false positives, false negatives, precision, recall, F1, signed timing error, absolute timing error, and unmatched records for `yell` and `transient`.

Drone comparison pairs detected start/stop events with the human drone range and reports start error, stop error, interval intersection-over-union, false-active seconds, and false-inactive seconds. Silence before calibration and any post-drone tail are included in the false-event accounting.

## Error handling

- Missing `ffmpeg`, unavailable CoreAudio input, nonzero recorder exit, malformed WAV, wrong channel count, wrong sample width, wrong sample rate, or duration outside the configured tolerance produces a clear failure and preserves the previous fixture.
- Invalid labels—unknown type, non-integer timestamp, negative time, end before start, out-of-bounds range, duplicate incompatible file metadata, or sample-rate mismatch—fail before analysis.
- Non-monotonic frames, incomplete hops, non-finite values, and invalid detector output fail the run and do not produce a success manifest.
- The browser displays a visible status/error message when any bundle or audio resource cannot be loaded; it does not silently show empty tracks.

## Testing strategy

Host unit tests use the existing `unittest` suite and generated short PCM arrays for algorithm-level behavior. The committed WAV is used by an integration test that checks header validation, label loading, analysis completion, event ordering, and repeatability.

Required tests include:

- WAV reader rejects non-16-kHz, non-mono, non-16-bit, truncated, and non-integral-hop input;
- runner timestamps are monotonic and match hop duration;
- drone detector starts/stops once with hysteresis and does not chatter around thresholds;
- yell/transient conversion preserves one-frame edge events and confidence;
- comparison metrics match known hand-built labels with exact TP/FP/FN and timing values;
- two complete runs over the same WAV/config produce byte-identical features, events, effects, and normalized run metadata;
- effect simulation produces eight RGB pixels for every configured node and changes predictably when an event is inserted;
- browser review keeps the waveform cursor, feature cursor, event highlight, and LED frame on the same timestamp, and reports missing asset errors.

The normal project `make check` remains the primary host verification command. A focused review command runs the fixture analysis and writes ignored artifacts for manual inspection.

## Acceptance criteria for this slice

The slice is complete when a developer can run the documented capture or fixture-analysis command, open the generated review page, hear the committed ten-second WAV, see the waveform and human labels, see detected overlays and disagreement metrics, scrub or replay the yell region, and see synchronized eight-pixel effect output for multiple virtual nodes. Re-running the command with the same source and configuration must produce identical derived content. The labels must remain unchanged by every automated step.

The fixture is evidence that the plumbing is deterministic and reviewable. It is not evidence of general didgeridoo classification accuracy, a complete golden corpus, RF replay equivalence, or hardware validation.
