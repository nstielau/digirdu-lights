# Device information and OTA base requirement

Status: approved by the user on September 25, 2026.

## Screen and controls

Append Device as page four: Audio, Status, Brightness, Device. Keep Brightness
at index2 so its D1/D2 controls do not change. D0 cycles all four pages. Device
uses the existing left PAGE/NEXT/SLEEP labels, effect control and group sleep.
Preserve 30-second display idle, wake-only first gesture, full-screen sleep
overlay and the top Broadcasting banner.

Device displays the actual running app version, installed USB base version,
and complete lowercase CPU UID. This is the same ID used by OTA enrollment,
not the radio MAC. It is available even without enrollment. Both producer and
consumer use the same page and read their own information.

Use compact static text in the existing 240x135 layout, with left button labels.
Stack App, Base and ID above an update-status area. Keep the complete ID visible;
wrap long supported IDs or version strings onto bounded lines rather than
silently truncate them. No scrolling text or continuous animation. Maintain the
bounded strip renderer and stop all page rendering while the display is idle.

Illustrative content (example versions, not a current fleet claim):

```text
PAGE   DEVICE                 4/4
       App   1.1.1
NEXT   Base  1.1.3
       ID    468e33377e80
       UPDATE BLOCKED
SLEEP  App 1.2.0 needs base 1.2.0
       USB base update required
```

## Update status and freshness

Use only the current boot's check-in result. Do not add periodic network checks
or persistent status writes. The page must not initiate Wi-Fi or disturb ESP-NOW.
Distinguish a confirmed base block, a successful check with no base block, OTA
disabled/not enrolled, USB maintenance/no check, and failed/unavailable checks.
Older servers or bases without status support display an explicit unavailable
state. Do not say Up to date merely because no update was downloaded.

A base-block status names both the newer app version and its minimum base.
Only report a base block when an approved, non-revoked release newer than the
running app would otherwise match this device's board, role and CircuitPython,
but requires a newer installed base. Respect explicit pins; a pause is a pause,
not a base block. Continue selecting an older compatible release where allowed.

## Server and device flow

Add optional, bounded update-status metadata to the existing check-in response,
alongside the compatible manifest or null. Include explicit status support so
absence from an older server is not mistaken for a successful compatibility
check. Return blocked-version details even when a compatible fallback exists.
Keep download authorization and manifest compatibility enforcement unchanged.

The USB base validates status fields/version syntax and exposes a small in-memory
snapshot through a base-owned interface available to the app after slot isolation.
Treat metadata as display information only: it cannot authorize a download,
relax minimum-base checks, select an app slot or modify rollback state.

The app reads the running app version from its selected app_version module,
installed base version from the preloaded base, and UID from microcontroller.
Read static identity once, not on every audio frame. Read status only when the
dashboard needs it, using safe fallbacks on older bases. Never display credentials.

## Compatibility and rollout

Increment the USB base to1.1.3 for check-in metadata retention. Keep the app
minimum at1.1.0 because older supported bases can show versions/ID and explicitly
report that update-status support needs a base upgrade. Do not misrepresent that
fallback as a completed OTA check. Full blocked-release reporting needs the new
server and base; this is a one-time USB update even on boards just provisioned.

App release remains a separate publication step; the proposed next public app
version is1.1.1. No GitHub release, cloud deployment, fleet enrollment or hardware
write is part of this design review. Implement and test the changes first, then
use the existing authorized deployment workflow with the connected board's
identity rechecked.

## Verification

- Test page cycling, controls, actual app/base/ID sources and bounded text layout.
- Test idle/wake, sleep and Broadcasting overlays with the new page.
- Test server metadata for compatible fallback, newer base-only block, matching
  current version, no release, paused/pinned/revoked and other incompatibilities.
- Test device handling of valid, missing, malformed and failed check-in status;
  preserve rejection before file download and support for older bases/servers.
- Run make check plus relevant server/emulator checks; use emulators only.
- Inspect a rendered/native page including blocked and unknown states. Verify
  actual startup/readback on hardware if deploying, and report physical visual
  confirmation separately from software checks.
