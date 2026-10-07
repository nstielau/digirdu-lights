# TFT idle, sleep animation, and broadcast banner

**Goal:** Make the display easier to read on demand, stop unnecessary display
work, and communicate group operations without obscuring normal pages.

**Architecture:** Keep the existing bounded bitmap renderer. Dashboard owns
display inactivity and wake-press suppression; audio/radio/Wing loops continue.
Full-screen overlays are reserved for sleep. Command feedback replaces only the
top content heading. No base or radio protocol change is needed.

## Behavior

- TFT backlight defaults to 50%, independent of Wing brightness. After 30 seconds
  without buttons, set backlight to zero and skip snapshots, display-only sensor
  work, bitmap composition, and display transfers. This is display standby, not
  MCU deep sleep; no measured current saving is claimed.
- First press wakes the current page and consumes the entire gesture, including
  long holds. All buttons must be released stably before commands resume. Further
  presses refresh the timer. Incoming telemetry does not keep the screen awake.
- Group sleep wakes a blank display and inhibits inactivity blanking throughout
  the countdown. Existing group sleep, fade, and wake wiring are unchanged.
- Sleep screen retains title, number, and release guidance. A cached pixel-art
  sleeping dog breathes and rising Zs animate at a modest rate. Changing animation
  frames must never restart an unfinished strip transfer.
- Pending commands show `Broadcasting...` in the top content banner; failures
  retain meaningful text such as `NO PRODUCER`. Keep successful feedback briefly
  visible even if the acknowledgment arrives quickly. Pages remain underneath.

## Implementation and verification

- [x] Add failing tests in `tests/test_tft_activity.py` for timeout, zero idle
  drawing/sensor work, first-press suppression including holds, sleep wake, banner
  scope/expiry, and animation transfer progress.
- [x] Implement Dashboard lifecycle and bounded sprite rendering in `dashboard.py`;
  route button activity and banner status in `lights_app.py`. Add validated
  `display_idle_s` to `config.py` and raise only `display_brightness`.
- [x] Run `.venv/bin/python -m unittest discover -s tests -p 'test_tft_activity.py'`
  first failing, then passing. Run `make check` for full regression coverage.
- [x] Update README/AGENTS; review the diff. On the identified connected S3, back
  up files, use deploy/readback/startup checks, then measure native rendering and
  verify idle/wake. Request visual confirmation separately.

The current worktree already contains the previous group-control implementation.
The existing producer installation and OTA sequence floor14 must be preserved;
future fleet releases need sequence15 or higher. These UI-only changes do not
require a producer update when that producer has no TFT.

## Current validation

181 host tests pass. Code review completed and its fast-ACK banner issue has a
regression test and fix. README/AGENTS updated. The S3 has the verified files
and passed startup plus native idle/wake/animation preview. A later optional
screenshot export left serial unresponsive; physical RESET restored normal app
operation, verified in a45-second passive log. The user confirmed idle/wake,
page switching, and the animated dog/readable countdown. No fleet release, push,
or producer update was performed.
