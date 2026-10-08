# Recording Spectrogram Design

## Goal

Add a deterministic spectrogram to the authenticated real-world recording
review page. It must appear directly below the existing peak-amplitude waveform,
share the same timeline interactions, expose frequency content on a logarithmic
axis, and keep each detected event on its own line.

## Scope

This change extends the existing generated review bundle and browser review UI.
It does not alter audio classification, human labels, event matching, firmware,
the radio protocol, or the five-effect public replay.

## Review Layout

The Waveform panel remains the recording's primary timeline. Its timeline track
contains two vertically stacked regions:

1. the existing normalized peak-amplitude bars; and
2. a spectrogram canvas immediately beneath the bars.

The two regions share one horizontal viewport, timeline width, playhead, zoom
factor, scrollbar, click-to-seek gesture, and drag-to-pan gesture. Existing
human-label and detected-event markers remain over the waveform region so they
do not hide spectral detail. The playhead spans both regions.

The spectrogram uses a dark-blue, cyan, magenta, and yellow intensity palette.
It shows logarithmic frequency labels from 31.25 Hz through the 8 kHz Nyquist
limit and a fixed -90 to 0 dBFS intensity legend.
Using a fixed level range makes color intensity comparable across recordings.

The Detected events panel retains its current visibility filters and click-to-
seek behavior. Its list uses a single-column layout so every visible event is a
separate full-width row. Human labels and comparison metrics retain their
existing layouts.

## Spectrogram Data

`tools/sound_review.py` adds a pure spectrogram preview helper and includes its
result in every generated review bundle. It uses the same contiguous 1024-sample
hops and 16 kHz sample rate as the current waveform and feature analysis, so one
spectrogram column aligns with one waveform bar.

Each hop is Hann-windowed and transformed with the host FFT implementation.
Magnitude is converted to dBFS, clamped to the fixed -90 to 0 dBFS display
range, and resampled into 64 logarithmic frequency bands from 31.25 Hz through
Nyquist. Each display band uses the maximum FFT-bin magnitude whose center lies
inside its geometric edges; a band narrower than the FFT spacing uses the
nearest FFT-bin magnitude. Values are quantized to integers from 0 through 255.
Quantization keeps authenticated callable responses compact and makes the
derived artifact deterministic.

The bundle gains a `spectrogram` object containing:

- the frequency and dB bounds;
- the row and column counts; and
- frame-major quantized intensity values.

The review bundle schema version increments for the new field. The recording
library generator rebuilds both tracked-source derived bundles used by Firebase;
the source WAV and human-authored label files remain unchanged.

## Browser Rendering

`web/review-page.js` validates spectrogram metadata, dimensions, and byte values
while normalizing a bundle. A missing spectrogram is accepted for backward
compatibility with older local artifacts and displays a clear unavailable
message. Present but malformed spectrogram data rejects the recording bundle so
the page never presents misleading frequency output.

The renderer paints the quantized values into a canvas, with high frequency at
the top and low frequency at the bottom. It accounts for device pixel ratio and
repaints after bundle changes or relevant size changes. The canvas belongs to
the existing timeline track, so CSS timeline zoom and horizontal scrolling keep
it aligned with waveform bars without maintaining a second pan state.

Selecting another recording resets the existing playhead, selection, zoom,
pan, replay, and event-filter state, then renders that recording's waveform and
spectrogram together. No browser-side audio decoding or duplicate FFT pipeline
is introduced.

## Error Handling

- Silence maps to the fixed dB floor without non-finite values.
- Invalid dimensions, bounds, frame counts, or intensity values reject the
  loaded bundle with the existing review error state.
- A valid older bundle without the optional field shows the waveform and an
  explicit spectrogram-unavailable message.
- Empty detector results continue to show the existing empty-state message.

## Testing

Python unit tests use generated PCM to verify silence, byte bounds, dimensions,
determinism, and placement of a sine wave's strongest energy near its expected
log-frequency row. Artifact and recording-library tests verify that generated
bundles include spectrogram data while labels remain unchanged.

Playwright tests verify that the spectrogram is rendered directly beneath the
waveform, uses the shared timeline through seeking, zooming, panning, and
recording changes, handles missing data, rejects malformed data, and keeps each
visible detected event on a separate row without changing filter or seek
behavior.

The completed change is validated with `make check`.

## Acceptance Criteria

- Each real-world recording shows amplitude and log-frequency content on one
  aligned timeline.
- Color intensity uses the same fixed dBFS range for every recording.
- The existing playhead, zoom, pan, seek, labels, event filters, and recording
  selector continue to work.
- Every visible detected event appears on its own line.
- Generated artifacts are deterministic and authoritative labels are unchanged.
- `make check` passes.
