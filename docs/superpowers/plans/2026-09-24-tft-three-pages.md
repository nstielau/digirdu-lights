# Three-page TFT implementation plan

> Execute inline in the existing `feature/reverse-tft` worktree using the
> executing-plans workflow. User approved the combined spec; radio testing is deferred.

**Goal:** Audio → Performance → Status, one purpose per page.

**Architecture:** `dashboard.py` formats snapshots and reuses front/back bitmaps and cached colored/scaled
built-in font glyphs. `lights_app.py` passes existing spectrum, packet
freshness and failed-send measurements. No protocol, FFT or USB-base changes.

**Tech stack:** CircuitPython displayio/bitmaptools, pure Python unittest.

## 1. View model and navigation

- [x] Add failing tests to `tests/test_dashboard.py`: `Dashboard.page == 0`,
  three toggles yield `[1, 2, 0]`; refresh and effect updates preserve selection.
- [x] Test `snapshot(..., spectrum=levels, age=None, tx_failed=3)` carries eight
  clamped levels, shows missing battery/packet age as `--`, LOST before first
  audio, and exactly four role-specific `status_rows`. Assert fault/countdown
  priority through a pure `page_content(state, page)` mapping.
- [x] Run `.venv/bin/python -m unittest discover -s tests -p test_dashboard.py`
  and observe failures. Implement page cycle `(self.page + 1) % 3`, snapshot
  values, bounded status formatting and page content; rerun the tests.

## 2. Native rendering and integration

- [x] Test all pages with a recording TextScreen and fake bitmap backend:
  no field exceeds its count or 240×135 bounds, switching hides old content,
  spectrum and meter geometry match input, faults/countdowns fit all pages.
- [x] Native profiling found full scene refreshes at 45–100ms. Replace the
  composed TileGrid scene with two 240×135 bitmaps and a single display TileGrid.
  Precompute colored/scaled built-in glyph atlases at startup. Prepare off-screen
  separately, then transfer at most24 rows per loop, continuing pending strips
  before the next frame interval. Test bounded transfers/page replacement.
- [x] Place PAGE/1-of-3/NEXT-or-dash/SLEEP in a 36-pixel left rail; effect scale2
  on Performance, compact title on Audio, four label/value rows on Status.
- [x] `lights_app.update_dashboard` passes `features.spectrum`,
  `radio.radio.send_failure`, and `age=None` before `receiver.audio_sequence`
  exists. Keep early budget gate and include formatting/render cost.
- [x] Ensure omitted on-screen fields remain in bounded serial diagnostics:
  source/config/version, radio counters and timing information.
- [x] Run `make check`; inspect the complete diff against the approved spec.

## 3. Documentation and native preview

- [x] Update README/AGENTS with page order, roles, controls and limitations.
- [x] Verify board identity, back up existing files, use `make deploy`, verify
  byte readback/startup. If the documented Mac FAT12 problem repeats, unmount
  and eject first, then use the documented exclusive serial transfer procedure.
- [x] On bare-board consumer, exercise backend pages with explicit simulated
  input without sending radio data; inspect bounds/native refresh and memory.
  Restore the real consumer app on Audio afterward.
- [x] Record native outcomes in operations notes; request visual page/readability
  confirmation. Do not claim live RF, microphone, battery or sleep qualification.

- [x] User confirmed all three physical pages are readable and comfortably spaced
  after the D0 cycling check (September 24). Live radio testing remains deferred.
