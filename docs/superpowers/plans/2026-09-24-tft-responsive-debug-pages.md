# Responsive TFT diagnostic pages

**Goal:** Keep D0 page changes responsive, with one live Audio page and one slowly
changing Status page, as requested after the intermittent frozen display.

**Design:** Retain the existing layout and left controls. Audio keeps eight bars;
Status replaces Performance with current effect and four existing status rows.
Audio targets 5 Hz; Status updates once per second, with page presses immediate.
Bounded strips remain. Investigate timing starvation before changing scheduling;
a slow draw must not permanently prevent all future redraws. Preserve audio-first
handling when no time is available. Do not change microphone or radio protocol.

- [x] Capture real runtime timing, button and received spectrum evidence.
- [x] Add failing regression for the identified display stall and two-page cycle.
- [x] Fix scheduling, implement two-page cadence, and run make check.
- [x] Deploy with backup/readback; run sustained live diagnostics and D0 check.
- [x] Record findings and remaining qualification limits.
