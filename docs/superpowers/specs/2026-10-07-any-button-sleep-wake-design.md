# Any-Button Sleep/Wake Design

Date: 2026-10-07

## Goal

Make the Reverse TFT's three side buttons—D0, D1, and D2—equivalent for
deep-sleep control: a three-second hold on any button starts the existing sleep
transition, and a press of any button wakes a sleeping board without a hold.
Short releases retain their existing page, effect, and brightness actions.

## Scope and compatibility

This change builds on the `feature/reverse-tft` implementation. It applies the
new behavior to the Reverse TFT `TFTControls`/`TFTButtons` path. Existing
FeatherS2 and ESP32 V2 button behavior remains unchanged: their configured
buttons still use the legacy short/hold path and reset-only deep-sleep wake.

The existing three-second red fade, DGRS group-sleep packet, OTA-trial sleep
suppression, output hold, display-idle wake suppression, and reset wake path
remain intact. No protocol or base-file change is required. The app version
increments from 1.1.1 to 1.1.2.

## Behavior

While awake, each input keeps its current polarity and short-release action:

| Button | Polarity | Short release |
| --- | --- | --- |
| D0 | Active LOW | Cycle the local dashboard page |
| D1 | Active HIGH | Advance the shared effect, or increase brightness on the Brightness page |
| D2 | Active HIGH | Decrease brightness on the Brightness page; otherwise retain its existing no-op |

The control state machine checks the gesture type before applying the
button-specific short action. A `HOLD` from D0, D1, or D2 returns the same
`sleep` action. This keeps long holds out of the short-action branches and
preserves the existing one-shot debounce behavior.

The permanent dashboard button rail no longer labels D2 as `SLEEP`; it uses a
neutral `AUX` label, while the Brightness page continues to show its `+` and
`-` short-action labels. Transient copy says “Hold any button” and does not
identify D2 as the sleep button. Sleep overlays and the red fade remain
unchanged.

## Sleep and wake flow

Before entering deep sleep, the app waits until all three inputs are stably
released. This prevents the button that initiated sleep from immediately
retriggering the wake alarm. The existing display/power teardown and wing data
line preservation then run as before.

The sleep alarm is a level-triggered OR of three pin alarms:

- D0 wakes on its active-low level.
- D1 wakes on its active-high level.
- D2 wakes on its active-high level.

There is no timer alarm. Reset remains an independent wake path. On restart,
the existing per-button release gates ignore the waking press until every input
has returned to its stable idle level, so a wake press cannot also change a
page, change an effect, change brightness, or request sleep.

Consumers continue to wake locally; an asleep radio cannot receive a group
wake command. Producers and consumers retain their existing role-specific
handling of the `sleep` action and group control packets.

## Files and tests

- `effects.py`: make `TFTControls` return `sleep` for a hold from any input and
  track the hold countdown for whichever button is being held.
- `lights_app.py`: update generic hold/countdown text, wait for all Reverse TFT
  buttons to release, and arm D0/D1/D2 pin alarms.
- `dashboard.py`: remove the permanent `SLEEP` rail label and use generic hold
  guidance.
- `tests/test_controls.py`: cover short actions plus long holds for all three
  buttons and both producer/consumer roles.
- `tests/test_sleep.py`: cover all-button release gating, all three wake alarms,
  and preservation of the existing teardown contract.
- `tests/test_dashboard.py`: update the rail label and generic hold message
  expectations.
- `app_version.py`: bump the application version to 1.1.2.
- `README.md`, `TODO.md`: document the any-button behavior and remove the
  completed wake item from the project TODO.

The tests use host mocks for pin/alarm construction. They verify polarity,
argument shape, release-before-alarm ordering, and action routing, but do not
claim physical low-power current or hardware wake qualification.
