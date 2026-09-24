> Superseded later September 24 by the user-requested Audio/Status simplification.
> See `../plans/2026-09-24-tft-responsive-debug-pages.md` and operations notes.

# Reverse TFT: Audio, Performance and Status

Date: September 24, 2026

## Decision and scope

After testing the first TFT dashboard on the physical Reverse TFT board, the
user found it readable but crowded. They requested a combination of mockup A
(effect and level) and B (frequency bars), with three screens in this order:
**Audio → Performance → Status**.

This revises the dashboard layout in the September 23 Reverse TFT spec.
Hardware, role setup, audio analysis, ESP-NOW protocol, OTA and sleep behavior
remain governed by that spec and subsequent documented button pull fixes.
The user approved this design on September 24; implementation is underway.

## Navigation and shared behavior

- D0 short release cycles Audio → Performance → Status → Audio.
- Boot starts on Audio. Page selection is local, held in RAM, and never sent
  to other devices or saved on each press.
- Pages do not advance automatically, including when the effect changes.
- D1 advances the producer's shared effect from any page. On consumers it
  remains inactive and its label is a dash.
- D2 retains hold-to-sleep, countdown, release-before-sleep and local wake.
- Keep button labels down the left edge. Add a small 1/3, 2/3 or 3/3 marker
  below PAGE so the cycle is discoverable.
- Critical microphone faults, clipping, and consumer link loss remain visible
  on every page. Sleep countdown/fade/release instructions temporarily take
  priority over normal page content. Text accompanies status colors.
- Preserve dim backlight, rotation setting, bounded 5 Hz refresh and audio-first
  scheduling. A display failure must not stop audio, radio or Wing output.

## Page 1: Audio

Show a modest effect number/name heading, eight rainbow spectrum bars, and a
single state label. Use the existing eight normalized spectrum levels; do not
run another FFT or introduce different normalization for the TFT.

Producer bars represent local microphone analysis. Consumer bars represent
received analysis, with the existing link-loss decay and an explicit LOST
state. Bars always show the audio spectrum, even when another Wing effect is
selected. No battery, radio counters, firmware footer or numeric level here.

## Page 2: Performance

Show a large effect number/name, one wide level meter, a numeric level and one
state label. Leave deliberate space between these elements.

- Producer: DC-removed microphone RMS in dBFS, with current calibration,
  quiet/playing, clipping or microphone-fault state.
- Consumer: received normalized volume in percent, with LIVE or LOST.
- Preserve the existing meter mappings; do not label received volume as dBFS.
- Effect changes update the title on the current page; they do not navigate.

## Page 3: Status

Use a role/status heading and exactly four spacious rows:

| Row | Producer | Consumer |
| --- | --- | --- |
| 1 | Local battery estimate | Local battery estimate |
| 2 | Consumers seen in last 10 seconds | LIVE / LOST |
| 3 | TX submissions per second | Valid RX packets per second |
| 4 | Native failed sends since app start | Age of last valid audio packet |

Battery displays the local MAX17048 percentage when valid, otherwise `--`.
Do not infer battery presence from USB-powered readings. Seen count retains
its bounded registry/capacity semantics; it is not proof of LED rendering.
TX submissions are not acknowledgments. Show `--` for last-packet age before
any valid audio arrives. Keep rates wrap-safe and packet age bounded to fit.

Full MAC addresses, channel/group, firmware version, totals, rejects, skipped
sends and timing details remain available through serial diagnostics. Remove
their persistent on-screen footer. The current explicit source is unchanged.

## Implementation boundaries and verification

Keep view formatting and page cycling testable in `dashboard.py`; retain
hardware resources in the existing display backend. Supply spectrum, local
battery and radio statistics from the existing runtime without new packets.
Reuse front/back indexed bitmaps and cached colored/scaled built-in glyph
atlases. Native qualification found composed full-scene refreshes too slow;
prepare off-screen, then copy at most24 rows to a single display TileGrid per
loop turn. Continue partial transfers across turns before starting the next
frame. Initial full-screen clearing happens before the audio/radio loop.

Use the 240×135 canvas with a roughly 36-pixel control rail. All text must fit
with the actual built-in font: large effect text at scale 2, other text at
scale 1. Validate the longest effect name and unavailable/fault states.

Before deployment, verify all three pages for both roles, D0 wraparound,
effect changes without page changes, silence/link-loss rendering, absent
battery, fault/countdown priority and display-budget behavior. Run `make check`.
After deployment, confirm readability and page cycling on the physical bare
board. Live radio testing remains deferred at the user's request; microphone,
Wing, battery and sleep-current qualification still require appropriate hardware.

## Review artifact

Local mockup (illustrative data, approximate browser fonts):
`.superpowers/brainstorm/4441-1790261408/content/tft-three-pages.html`.
It shows both roles and fault states side by side at a 240×135 drawing resolution.
