# Sound Analysis Virtual Consumer Design

Date: 2026-10-08
Status: Approved and implemented

## Goal

Make the sound-analysis review page more concise and useful while preserving the
firmware renderer as the single source of truth. Rename the page to **Sound
Analysis**, keep a synchronized virtual consumer visible in a sticky left rail,
and let the reviewer switch among the five sound-driven effects while viewing a
complete portrait 4×8 FeatherWing matrix.

## Rendering approach

The browser will not reimplement the Python animation engine. The existing
offline review pipeline continues to instantiate `CulvertAnimation` once per
effect and virtual node and render deterministic frames from the analyzed audio
features.

`tools/sound_review.py` will serialize all 32 LEDs from each rendered frame
instead of averaging them into eight groups. Renderer output is physical-order
GRB bytes. The review pipeline will use the shared `FEATHERWING_PORTRAIT`
mapping to reorder those bytes into logical, row-major portrait coordinates and
convert each pixel to RGB. This keeps physical mapping and channel conversion
in Python beside the authoritative firmware definitions. The browser receives
32 RGB triples ready to place in a four-column, eight-row grid.

The effects artifact continues to contain timelines for Spectrum, Ember,
Aurora, Ripple, and Chroma across the existing virtual nodes. Battery remains
excluded because sound-review recordings contain no node-voltage measurements.
Virtual node `0` remains the displayed consumer, preserving current behavior.

The effects artifact metadata will describe a 32-pixel portrait layout with
four columns, eight rows, row-major logical ordering, and RGB channel order.
Generated review-library bundles will be rebuilt from source recordings so the
deployed page and authenticated recording payloads use the same schema.

## Page layout and behavior

`web/review.html` changes its heading from “Human-reviewed sound analysis” to
“Sound Analysis.” The protected review area becomes a desktop two-column grid:
a narrow virtual-consumer rail on the left and the existing recording,
playback, waveform, label, event, feature, and comparison panels on the right.

The virtual-consumer rail contains an Effect label, a native select control,
and the full portrait 4×8 LED matrix. The rail uses sticky positioning below the
site header so it remains visible during analysis scrolling without covering
content. At the existing narrow-screen breakpoint, the layout becomes one
column, the rail moves above the analysis panels, and sticky positioning is
disabled.

The selector is populated in bundle order and is limited to the five available
sound effects. Spectrum is the initial selection. A reviewer’s selected effect
persists while playing, seeking, zooming, selecting labels, and changing
recordings when the new bundle contains that effect. Changing the selection
immediately redraws the nearest frame at the canonical playhead time; it does
not restart audio or reset the playhead.

Playback, manual seeking, label replay, and recording changes continue to use
the existing shared millisecond playhead. The virtual consumer chooses the
nearest frame from the selected effect’s node-`0` timeline, so every effect
remains synchronized with the waveform, features, events, and audio.

## Empty and invalid states

The virtual consumer always renders 32 pixel elements. Before a valid bundle is
loaded, when no effect timelines are available, or when the selected timeline
has no frame, every pixel is dark and the effect selector is disabled.

Bundle normalization accepts only effect names with frame collections. If a
previously selected effect does not exist in a newly loaded bundle, selection
falls back to the first available effect. Pixel channels are clamped to byte
range before being applied as CSS colors. Existing visible review and audio
errors remain authoritative; a missing visualization does not interrupt audio
review of otherwise valid bundle data.

The matrix keeps `role="img"` and exposes an accessible label containing the
selected effect and frame time. Individual pixels retain numbered RGB labels so
the generated colors remain inspectable without sight.

## File boundaries

- `tools/sound_review.py` owns physical-GRB to logical-portrait-RGB conversion,
  full-frame serialization, and effects-layout metadata.
- `tests/test_sound_review.py` verifies exact conversion, orientation, frame
  dimensions, and deterministic effect output.
- `web/review-mode.mjs` owns small pure helpers for available effect names and
  selected-effect frame lookup so browser behavior can be tested without a DOM.
- `web/test/review-mode.test.mjs` verifies selection, fallback, node-`0` lookup,
  and malformed/missing-frame behavior.
- `web/review-page.js` owns selector state, DOM rendering, and synchronization
  with the canonical playhead.
- `web/review.html` owns the renamed heading, left-rail structure, responsive
  layout, and 4×8 matrix styling.

No firmware renderer, effect algorithm, radio protocol, device configuration,
or public effects replay behavior changes.

## Testing and acceptance

Implementation follows test-first development. Focused Python tests first prove
that a known 32-pixel physical GRB frame becomes the expected row-major portrait
RGB frame and that every generated effect frame contains exactly 32 pixels.
Focused JavaScript tests first prove effect discovery, preserved selection,
fallback selection, and node-`0` frame lookup.

Browser coverage verifies that the page says “Sound Analysis,” the selector
contains exactly the five sound effects, choosing an effect updates the full
matrix without moving the playhead, and desktop/mobile layouts retain all 32
pixels. Existing review-library and authentication tests continue to cover
recording delivery.

The change is complete when the focused tests, web unit tests, browser tests,
web build, and project-wide `make check` pass; generated review artifacts report
a 4×8, 32-pixel portrait layout; and manual inspection confirms the selected
effect stays synchronized while playing and scrubbing.
