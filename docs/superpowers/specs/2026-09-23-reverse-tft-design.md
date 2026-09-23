# Reverse TFT board support and device dashboard

Date: September 23, 2026

## Status and decisions

The user selected **layout A, performance first**, then approved the revision
with physical buttons and their on-screen labels down the **left edge**. That
screen direction is settled. This document specifies the remaining hardware,
setup, radio, update and power behavior for review before implementation.

Use one firmware application for producers and consumers on all supported
boards. Screen support is optional; existing boards continue without a TFT.
The proposed role policy is a guided, one-time microphone check plus explicit
confirmation and a saved role. Automatic role inference on every boot is not
part of this version.

The reviewed browser mockup is local design material, not firmware or measured
telemetry. It is saved under
`.superpowers/brainstorm/94011-1790194594/content/reverse-tft-layouts-v3.html`.
Its radio rates, counts and battery values are simulated.

## 1. Hardware profiles

Add `adafruit_feather_esp32s3_reverse_tft`, keeping the original FeatherS2 and
Feather ESP32 V2 profiles. Use CircuitPython 10.3.1; verify identity and required
modules on hardware before deployment. The connected USB device advertises
Reverse TFT, but its installed firmware and filesystem have not been verified.

Centralize pins and capabilities in a USB-base `hardware.py`, preloaded by the
bootstrap before application import paths are isolated. Base and app must use
the same profile. Host deployment tools may read the pure profile definitions
without importing CircuitPython hardware modules.

| Function | Reverse TFT | Original FeatherS2 | ESP32 V2 |
| --- | --- | --- | --- |
| Wing data, factory jumper | D6 / GPIO6 | IO38 | D32 / GPIO32 |
| I2S BCLK | Proposed D5 / GPIO5 | IO5 | Unsupported producer |
| I2S LRCLK / WS | Proposed D9 / GPIO9 | IO6 | Unsupported producer |
| I2S data input | Proposed D10 / GPIO10 | IO9 | Unsupported producer |
| Display | Built-in `board.DISPLAY`, 240×135 | None | None |
| Battery sensing | MAX17048 over board I2C | Unsupported | ADC1 GPIO35 divider |

New-board microphone wiring is a proposal for an ICS43434: SEL to GND,
VDD to main 3.3V, common GND. Verify actual wiring before capture. Do not reuse
the old GPIO6 microphone clock: it conflicts with this board's wing data.
Keep TFT SPI, GPIO7 TFT/I2C power, GPIO45 backlight, I2C GPIO3/4, and buttons
GPIO0/1/2 reserved. Do not assume FeatherS2's external IO43 button exists here.
Reject conflicting or unsupported pin overrides before claiming any pins.

Use the board's existing display initialization. Read the MAX17048 with bounded
I2C operations and the built-in modules; avoid a new unversioned `/lib`
dependency. Probe only its documented address, 0x36. Unknown sensor revisions,
absent devices or failed reads produce unavailable status, not invented
voltage/percentage. Report voltage through the existing battery report shape;
show the sensor's estimated percentage locally on the TFT. Do not derive a
percentage from the voltage scale used by the Wing's Battery effect.

## 2. One app, explicit saved identity

Separate board identity (detected hardware), role (saved configuration), and
microphone health (runtime observation). A failed microphone must not silently
turn a producer into a consumer, and random input noise must not elect a
producer.

For new, unprovisioned Reverse TFT nodes, show a first-run setup page:

1. Choose Consumer, or Test microphone for Producer.
2. The mic test checks capture completion, non-flat samples, clipping and level
   variation over a bounded ten-second quiet/sound trial. Display a live meter
   and explain flat, clipped or failed capture. Nonzero RMS alone is insufficient.
3. The user confirms Producer after seeing the meter respond, or selects
   Consumer. No automatic promotion based solely on the signal.
4. Save the chosen role and group. An explicit host profile may set the role
   instead. Existing `node_config.py` profiles continue to take precedence;
   existing nodes never enter first-run setup after an update.

For a newly provisioned Reverse TFT without an explicit profile, deployment
must leave the role unconfigured rather than copy the repository's default
consumer override. Resolve setup before constructing the audio configuration
or attempting authenticated OTA. Add `make configure-node` for host-assisted
role/source selection and verified writes while USB owns the filesystem.

Store user selections as validated data, not generated executable Python, in
`/node_state.json`. A base `node_state.py` merges defaults, saved data and
explicit node overrides consistently for the bootstrap and application. Use
bounded sizes, temporary writes, readback and atomic replacement. Do not write
when the USB host owns the filesystem; offer host-assisted setup instead.
Persist on confirmation only, never on each sample or boot.

OTA enrollment follows role selection. Once credentials are provisioned, role
changes require the host enrollment/configuration workflow so the device role
and cloud record cannot disagree. Re-running a microphone health test does not
change enrollment. Setup must never stall an OTA health trial.

Consumers retain an explicit producer MAC and group. Host setup uses the
selected producer's real MAC when provisioning new consumers; do not keep the
old FeatherS2 MAC as an invisible default for a new installation. Automatic
producer discovery/election is outside this increment. Legacy configured
consumers must have their saved source changed before following a new producer.

## 3. TFT layout and behavior

Use the approved landscape 240×135 canvas. Reserve approximately 45 pixels on
the left for button labels; align labels to the physical buttons in the chosen
orientation. Verify the actual top-to-bottom ordering during board bring-up.
The content region keeps the effect name and level meter dominant. Provide
rotation as a profile setting independent of the NeoPixel matrix orientation.

| Area | Producer | Consumer |
| --- | --- | --- |
| Header | PRODUCER, local battery | CONSUMER, local battery |
| Main title | Effect number and name | Received effect number and name |
| Meter | DC-removed microphone RMS in dBFS, clipping flag | Received normalized audio level in percent |
| Lower row | Recently seen consumers, transmit rate | LIVE/LOST, receive rate or age of last valid packet |
| Footer | Channel/group and app version | Channel/group and app version |

Do not label consumer normalized volume as dBFS: the existing feature packet
does not carry raw microphone RMS. Quiet, clipping, calibration, mic fault and
lost link need distinct text states; color alone is insufficient.

D0 opens a diagnostics page with counters: submitted transmits, native send
success/failure, skipped sends, valid receives, rejected packets, packet age,
source MAC and audio timing overruns as applicable. A radio send success does
not prove a consumer received or rendered a frame. Use fixed-size text fields
and rate windows; handle counter wrap and reboot without negative rates.

Implement an optional `dashboard.py` with a pure snapshot/view-model layer and
a lazy CircuitPython display backend. Reuse display objects and built-in font
resources. Start with manual refresh at 5 Hz, dim configurable backlight and
no full-screen decorative animation. Audio/radio processing has priority;
skip a display refresh instead of queueing old updates. Dashboard failure logs
a bounded warning and leaves audio/wing operation running. No display imports
or allocations on boards without a TFT.

Show boot/update state on the TFT as bounded phase text, while retaining the
existing dim cyan wing indicator. Network calls can pause visible updates;
do not display a fabricated percentage or leave the backlight bright by default.
The small boot screen belongs to the USB base hardware helper; never import an
app-slot dashboard during maintenance and risk caching a mixed app version.

## 4. Buttons and power

| Button | Producer | Consumer |
| --- | --- | --- |
| D0, active LOW | Switch dashboard page | Switch dashboard page |
| D1, active HIGH | Short release advances shared effect | No group control; label FOLLOW |
| D2, active HIGH | Three-second hold requests group sleep | Three-second hold requests local sleep |

Preserve D0's ROM-loader and boot-time USB maintenance functions. Do not apply
the old active-low-only button handler to D1/D2. Debounce each input separately.
D1 long holds must not sleep the device. Existing boards retain their current
short/long controls and reset-only wake behavior.

For Reverse TFT, D2 is also the proposed local wake input. Show the hold
countdown, start the existing three-second red fade after the threshold and
broadcast producer sleep during the fade. After the fade, keep output black
and wait for D2 to be stably released before arming a level-triggered wake.
A held or stuck button must not produce an immediate wake/re-sleep loop; show
Release D2 while waiting. Ignore the waking press until a stable release.
A fresh press wakes this board through a normal restart; RESET also works.
Wake does not require a three-second hold. There is no timer wake.

Wake is local: an asleep consumer cannot receive an ESP-NOW wake command.
Each sleeping device requires its own button press or reset. Keep group sleep
best-effort; screen wording must not imply all nodes acknowledged shutdown.
Sleep remains disabled during candidate health trials.

Before sleep, blank the TFT and wing, stop display refresh, release the display
bus/backlight ownership, disable TFT/I2C and onboard NeoPixel power through the
verified profile, stop microphone/radio, and preserve the wing data LOW. Validate
the ordering against CircuitPython's board pin-reset hooks: GPIO7 defaults ON
and must not be re-enabled inadvertently during teardown. A pin alarm and held
power outputs must coexist. Test USB simulated sleep separately from actual
battery sleep. Do not claim measured current savings without measurement.

The separate FeatherWing VBAT/VUSB power rail remains powered. The deferred
intermittent sleep-light issue is not considered fixed by TFT power management.

## 5. Consumer presence over ESP-NOW

Keep the existing v3 audio feature and sleep packets unchanged. Add a separately
versioned presence message with its own magic, group, intended producer MAC,
producer session, consumer boot session/sequence and last accepted audio
sequence. Validate length and fields before use. Count the actual sender MAC,
not a MAC claimed in the payload.

Consumers broadcast one presence message about every 3 seconds with randomized
initial delay and ±0.5-second interval jitter, only after receiving a valid,
recent frame from their configured producer. Broadcast replies avoid per-peer
registration limits for the first version. Producers listen with the existing
native `read_success` completion gate and an eight-packet drain bound.
Retain one outstanding send per device and never block audio waiting for a
presence transmission. Suspend presence during sleep transitions.

Maintain a bounded table of 32 sender MACs, with a configurable maximum and
10-second expiration. Validate intended producer, group and current producer
session; reject stale/duplicate presence sequences. Evict expired records
first, then the least recent, and show a capacity indicator if the table fills.
No fixed-size queue may grow with the number of incoming packets.

Label the number **SEEN/10s**, meaning recently acknowledged listeners. It is
not an exact inventory, a range guarantee, or proof LEDs are visibly working.
Older consumers still render v3 features but are uncounted until updated.
Old producers ignore presence; upgraded consumers still work with them.
Avoid counting unrelated control packets as lost audio sequences.

## 6. Deployment and release compatibility

Update `make` and host helpers to recognize all three exact board IDs, verify
required modules and use native USB/CIRCUITPY deployment for Reverse TFT.
Generalize the existing identity/UID/drive checks rather than treating every
new board as an ESP32 serial-only target. Preserve credentials, profiles,
recovery and slots; routine deployment never erases flash.

For new-board CircuitPython installation, inspect the existing bootloader and
firmware first. CircuitPython 10 requires a compatible TinyUF2 bootloader.
Back up existing contents and use board-specific official artifacts; firmware
installation and application deployment remain separate commands.

Target a new **USB base 1.1.0 / app 1.1.0**, with minimum base 1.1.0. Add
`hardware.py` and `node_state.py` to the base and preload them. Add
`dashboard.py` and `device_setup.py` to the app bundle, alongside the existing
ten modules. Base and cloud validation must support two explicit contracts:

- Legacy schema 1: exact historical ten app files and two-board list.
- Schema 2: exact new twelve app files and three-board list, with minimum base
  1.1.0. Keep app entry-point API 1 and audio protocol v3.

Do not replace the legacy contract with the new constants: doing so would
invalidate installed manifests and rollback slots. Select the exact permitted
file set by schema, reject mixed sets/unknown paths, and retain all digest,
size, sequence and compatibility checks. New Reverse TFT devices cannot run
legacy releases; they need their own compatible recovery bundle at provisioning.

Update Firebase release/report validation and enrollment tools before publishing
the new release. Existing bases must keep selecting compatible 1.0.x releases.
Upgraded old-board bases must still validate and boot installed 1.0.x slots,
then trial 1.1.0 with a valid rollback path. Provisioning must treat the new
native USB board like FeatherS2 for safe filesystem ownership.

## 7. Verification and rollout

Host checks cover profile conflicts, role persistence/precedence and corrupt
state; quiet/flat/clipped microphone-test handling; button polarity, debounce,
hold/release/wake suppression; display snapshots and refresh throttling;
presence validation, duplicates, expiry, capacity and mixed versions; and
legacy/new release contracts including rollback after base upgrade.

Run `make check`, relevant API/emulator/browser checks, and source readback on
each deployment. On the new board verify I2S support, pin assignments, TFT
orientation/button order, battery readings and dim backlight. Compare audio
timing with display disabled/enabled; report measured FPS, mean/max work,
64 ms budget misses and capture discontinuities. Reduce display rate if it
adds sustained overruns. Preserve existing limitations rather than claiming
lossless capture from a zero discontinuity counter.

Bring up a new-board consumer first, then a microphone producer on a second
new board. Validate old/new producer-consumer combinations and count only
upgraded acknowledging consumers. Run user-visible effect-change, unplug/rejoin,
mic quiet/sound, lost-link, Battery and local/group sleep tests. Test wake after
release with USB and battery power separately; confirm reset remains usable.
Keep the old working nodes available throughout migration.

Update README wiring, commands, role setup, display fields, presence semantics,
button controls and OTA upgrade instructions. Update AGENTS with verified new
hardware facts. Record measured hardware results and failures in operations.

## Sources

- [Reverse TFT pinouts](https://learn.adafruit.com/esp32-s3-reverse-tft-feather/pinouts)
- [Button polarities](https://learn.adafruit.com/esp32-s3-reverse-tft-feather/digital-input-multiple-buttons)
- [Battery and power management](https://learn.adafruit.com/esp32-s3-reverse-tft-feather/power-management)
- [CircuitPython 10.3.1 board pins](https://raw.githubusercontent.com/adafruit/circuitpython/10.3.1/ports/espressif/boards/adafruit_feather_esp32s3_reverse_tft/pins.c)
- [CircuitPython 10.3.1 display and power initialization](https://raw.githubusercontent.com/adafruit/circuitpython/10.3.1/ports/espressif/boards/adafruit_feather_esp32s3_reverse_tft/board.c)
- [CircuitPython pin alarms](https://docs.circuitpython.org/en/latest/shared-bindings/alarm/pin/index.html)
