# USB maintenance countdown computer

The user selected the friendly compact computer (mockup C) and asked to raise it above “Release to cancel.” Draw a small blocky amber and gray computer with a dark screen and cyan smiling face on the Reverse TFT's 240 × 135 countdown overlay. Keep `HOLD FOR USB`, the changing countdown digit, `USB READY`, the cancel/release instruction, and the two-pixel orange border in their current places.

Place the computer in the left half of the overlay, below the title and at least a few pixels above the detail text. Show it while the three-button maintenance gesture is counting down and in its ready state. Keep the existing sleep dog on sleep overlays. Use the existing 16-color TFT palette and native rectangle fills to avoid an additional framebuffer or image asset. The app release version advances to 1.1.6; the USB base and app minimum base do not change.

Host tests will check that the computer's colored pixels stay within its allotted region on both maintenance overlay states and do not appear on other overlays. `make check` must pass. The current Reverse TFT can receive the new recovery app only through a full USB deployment in maintenance mode. Visual appearance on device requires a human check.
