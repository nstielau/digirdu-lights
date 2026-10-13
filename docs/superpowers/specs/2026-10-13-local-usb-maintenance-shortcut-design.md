# Local USB maintenance shortcut

## Behavior

On an ESP32-S3 Reverse TFT node, holding D0, D1, and D2 together for four
seconds enters USB maintenance. The TFT uses the existing Sleep countdown layout
with an orange **HOLD FOR USB** title, a seconds-remaining digit, and **Release
to cancel**. The chord is local: it sends no ESP-NOW command and does not put
other nodes to sleep. A single button's existing three-second sleep gesture
continues to work. Once the chord starts, individual button actions are
suppressed until all three have been released, even if the user cancels.

The gesture is disabled during an OTA health trial and after group sleep has
started. If the installed device base lacks the shortcut, the app shows
**BASE UPDATE NEEDED** and stays running. The shortcut does not alter the
radio protocol, role, node settings, or brightness limits.

## Boot handoff and indicators

After the countdown, the app unwinds its microphone, radio, button, and pixel
contexts; it writes a one-use maintenance marker in NVM bytes 5 through 8 and
resets. Bytes 0 through 4 remain reserved for OTA recovery. On the next hard
boot, `boot.py` consumes and clears the marker before selecting USB ownership.
The existing D0-after-RESET entry remains available. Normal startup keeps its
blue two-second selection window and cyan network activity indicator.

Maintenance startup uses a single dim orange moving pixel on the 4x8 wing
instead of blue, then a two-pixel orange border on the TFT boot splash. The
orange border and **USB MAINT** label remain visible while the recovery app
loads. The running dashboard retains its USB maintenance banner. The matrix
indicator is blacked out and its pin released before the app takes ownership.

USB maintenance remains active across soft reloads because `boot.py` is not
rerun. The next full RESET or power cycle, with no new chord or D0 press, boots
normal OTA mode. The user ejects `CIRCUITPY` before that reset. If NVM cannot
hold the marker, the app reports an error and does not reset. No runtime
filesystem remount bypasses host/device ownership protection.

## Releases and verification

The device base becomes 1.1.5; the app becomes 1.1.4. App minimum base stays
1.1.0 because the chord detects older bases and leaves existing behavior
available. A base-only USB update cannot install the new app gesture. Test the
one-use marker and boot selection, chord timing/cancellation and no broadcast,
trial/sleep suppression, countdown and orange indicators, full host suite,
then native entry/exit and readback on a Reverse TFT. Native fit and controls
require separate physical confirmation.
