# EchoGlow startup

User approved EchoGlow branding, actual firmware version, live status, and a
soundwave that reflects off a wall then bursts into light. Apply to Reverse TFT
startup only; preserve existing project/cloud identifiers and other boards.

## Design

240x135 landscape: EchoGlow at top, version below, animation in the middle,
one-line status at bottom. Cyan wave travels right into a magenta wall, reflects
left, then bursts into cyan/pink/gold particles. After roughly two seconds it
settles into a gentle glow. After the font optimization, the user revised the
design to require the completed explosion before handoff. Target20Hz and finish
remaining animation through2.35s, with a3second safety deadline. Skip completion
on failed/replaced displays or when the intro has already completed. Blocking
Wi-Fi/TLS may pause it; resume gradually when callbacks return.

BootScreen remains USB-base owned. Raise base version to1.1.2, retain app minimum
base1.1.0 and radio protocols. Optional app startup callbacks must tolerate the
older base. Show the selected local version, never a remote latest version before
installation. USB/non-enrolled boots get the same screen and correct local status.
Display failures remain optional and must not prevent lighting. Close boot
display ownership before the dashboard takes over; preserve microphone faults.

## Tasks

- [x] Write failing tests for animation trajectory/bounds, bounded cadence,
  status/version, non-display boards, shared OTA-screen lifetime, and recovery
  version selection. Use built-in CircuitPython graphics; no third-party assets.
- [x] Implement cached bitmap animation plus lifecycle in hardware.py; service
  it from ota_bootstrap.py and optional dashboard font-preparation callbacks.
  Keep the dim OTA Wing indicator cadence/brightness unchanged.
- [x] Run targeted tests and make check; review error and ownership paths.
- [x] Back up and verify native USB base/app changes on the identified S3. Run
  native preview/timing, restore the normal app, request visual confirmation.
- [x] Update README/AGENTS/operations, including one-time USB requirement and
  app/version versus base/version distinction. No fleet publication requested.

## Validation

191 host tests pass. Review findings resolved. Native S3 readback and startup
passed; preview rendered all four stages (max tick41.99ms). Dashboard preparation
serviced the animation and handed off in6.64s. Normal app restored. User visually
confirmed branding/version, reflection/burst, and dashboard after RESET.
Documentation updated; no push or fleet publication.

Completion revision:195 host tests pass. Native measured43 frames including the
complete burst/glow, average51.4ms/max54.9ms frame gap; local soft boot to lighting
4.87s. Base1.1.2 and matching app verified on USB. The user accepted the smoother
animation and completed explosion after a physical RESET; visual check complete.
