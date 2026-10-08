# Waveform Seek and Pan Design

## Context

The sound-review page already keeps playback, the position slider, feature
values, detector events, human labels, and the virtual consumer synchronized
through `setTime()`. Zoom widens the timeline track inside a horizontally
scrollable waveform viewport, but the waveform itself does not currently
accept direct seek or drag gestures.

During review of `high-yell-01.wav`, direct interaction was needed to locate a
hard-to-place yell. The human-reviewed drone interval is 1020–6950 ms. The
yell remains unlabeled, and transient detections will not be promoted to human
labels for this take.

## User-visible behavior

- A primary-button click or tap on empty waveform space seeks to the timestamp
  under the pointer.
- If audio is playing, it continues from the new timestamp. If audio is paused,
  it remains paused.
- Pointer movement of five CSS pixels or less remains a click. Movement beyond
  five pixels becomes a pan gesture and must not seek when released.
- A pan changes the waveform viewport's horizontal scroll position without
  changing the playhead.
- Panning clamps naturally to the scrollable bounds. At 1× zoom there is no
  horizontal overflow, so a pan has no visible effect.
- Detector-event and human-label buttons retain their existing click behavior
  and do not start a waveform seek or pan gesture.
- Mouse, pen, and single-touch input share the same pointer-event behavior.
  Vertical page scrolling remains available on touch devices.
- The waveform shows `grab` and `grabbing` cursors to disclose the interaction.
- The existing position slider remains the keyboard-accessible seek control.

## Implementation design

`web/review-page.js` will own a small pointer gesture state containing the
active pointer ID, initial client X coordinate, initial viewport scroll offset,
and whether the drag threshold has been crossed.

On `pointerdown` over empty waveform space, the viewport captures the pointer
and initializes gesture state. On `pointermove`, crossing the threshold changes
the gesture to panning and updates `waveform.scrollLeft` from the original
scroll offset and pointer delta. On `pointerup`, a non-drag gesture converts the
pointer's viewport coordinate plus `scrollLeft` into a track-relative fraction,
clamps it to the track, and calls the existing `setTime()` function. A drag only
ends pointer capture. `pointercancel` and lost pointer capture clear the state
without seeking.

The time conversion will use the rendered timeline track rectangle rather than
assuming a particular zoom level. This keeps seeking correct at every supported
zoom and after responsive layout changes. Seeking continues to flow through
`setTime()`, preserving the existing synchronization and audio behavior.

`web/review.html` will add only the focused cursor and `touch-action` styling
needed for the interaction. No new controls or review-bundle fields are needed.

## Error and edge handling

- Ignore non-primary mouse buttons and additional concurrent pointers.
- Ignore gesture starts from detector-event and human-label buttons.
- Clamp computed timestamps through the existing `setTime()` path.
- Clear gesture state on pointer cancellation or lost capture so an interrupted
  drag cannot cause a later accidental seek.
- Do not alter playback state while seeking or panning.

## Verification

Playwright coverage will verify:

- clicking the waveform seeks to the corresponding timestamp;
- seeking while playing does not pause playback;
- dragging a zoomed waveform changes its horizontal scroll position without
  changing the playhead;
- movement within the threshold still seeks, while movement beyond it pans;
- panning at 1× remains bounded;
- event and label marker clicks preserve their existing behavior; and
- the page remains within its responsive horizontal layout bounds.

The focused browser suite will run on desktop Chromium, mobile Chromium, and
mobile WebKit, followed by the repository's full `make check` and web tests.
