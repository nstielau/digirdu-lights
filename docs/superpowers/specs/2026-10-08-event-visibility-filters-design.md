# Event Visibility Filters Design

## Context

The sound-review page displays detector events in two places: as markers over
the waveform and as rows in the Detected events panel. Recordings can contain
many low-value transient detections, which makes the musically relevant yell
and drone-boundary events harder to inspect.

This feature adds presentation-only filters. It does not change the detector,
human labels, comparison results, or saved review data.

## User-visible behavior

A compact, keyboard-accessible fieldset in the Detected events panel will show
one native checkbox for each detector display group present in the review
bundle. Each label includes that group's event count.

The known event types have these labels, groupings, and defaults:

- `Transient (count)` controls `transient` events and starts unchecked.
- `Yell (count)` controls `yell` events and starts checked.
- `Drone boundaries (count)` controls both `drone_start` and `drone_stop`
  events and starts checked. Its count is the combined boundary count.

Changing a checkbox immediately hides or shows matching detector markers on
the waveform and matching rows in the Detected events list. Human-label
markers remain visible. Human/detector comparison results remain visible and
unchanged because filtering is not a change to the underlying event data.

Visibility choices last only for the current page load. Reloading restores the
defaults. Playback, playhead position, waveform zoom, and horizontal pan are
not reset when a filter changes.

If a review bundle contains an event type that is not one of the known types,
the page creates a separate, checked-by-default checkbox for it. The label is
derived from the event type by replacing underscores with spaces and applying
readable capitalization. Unknown events therefore remain visible unless the
reviewer explicitly hides them.

## Implementation design

`web/review-page.js` will define the known display groups and maintain an
in-memory set of enabled group IDs. After loading a review bundle, it will
derive the available controls and counts from the detector events. Known drone
start/stop events will map to the shared drone-boundaries group; each unknown
raw event type will map to its own generated group.

The event-group fieldset will be rendered once per loaded bundle. Checkbox
change handlers will update the enabled-group set, then rerender only the
detector waveform overlays and Detected events list from the original,
unmodified event collection. Existing event ordering and marker interaction
will be preserved.

`web/review.html` will add the fieldset container and compact responsive styles
that follow the existing review-panel visual language. Native checkbox inputs,
a visible legend, and associated labels will provide keyboard operation and an
accessible group name without custom interaction code.

No review-bundle schema, export format, storage, detector logic, or comparison
logic will change.

## Edge handling

- A known group with zero events is omitted, because there is nothing to show
  or hide.
- Drone-start and drone-stop events always share one control, even if a bundle
  contains only one of the two boundary types.
- Unknown event types get independent controls rather than being merged into a
  catch-all category.
- Filter state is initialized after each bundle load, preventing state from a
  previous bundle from leaking into another review.
- Filtering does not mutate the source events, so re-enabling a group restores
  the same rows and markers.

## Verification

Browser tests will verify that:

- transient rows and waveform markers are hidden by default;
- yell and drone-boundary rows and markers are visible by default;
- enabling Transient restores its rows and markers;
- disabling Drone boundaries hides both drone-start and drone-stop events while
  leaving yell events visible;
- human-label markers remain visible through detector filtering;
- comparison output is unchanged when filters change;
- an unknown event type receives its own checked-by-default control; and
- filtering preserves playback time, zoom, and horizontal pan state.

The focused browser suite will run on desktop Chromium, mobile Chromium, and
mobile WebKit, followed by the repository's full `make check` and web tests.
