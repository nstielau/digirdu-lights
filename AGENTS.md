# Project guidance

## Current hardware: Unexpected Maker FeatherS2

Default make target: `BOARD=unexpectedmaker_feathers2`. Pin CircuitPython to
10.3.1; this app needs `audioi2sin.I2SIn`. The connected board was upgraded from
6.2.0-beta.1 and the microphone capture/beat detection was tested on hardware.
The user visually confirmed the rainbow works and reacts to claps with the
GPIO 38 wing data pin on September 15, 2026.
Do not confuse FeatherS2 with Adafruit ESP32-S2 Feather or
FeatherS2 Neo. Recheck identity whenever hardware changes.

ICS43434 wiring: BCLK=GPIO 5 (`IO5`), LRCLK/WS=GPIO 6 (`IO6`), DOUT=GPIO 9
(`IO9`), SEL/LR=GND (left channel), VDD=main 3.3V, GND=shared ground. Use
GPIO names, not D-number aliases. GPIO 9 is shared with SCL; do not initialize
I2C/STEMMA on it while using the mic. Capture standard I2S, 32-bit slots,
16 kHz mono left, signed 16-bit output. This is I2S, not PDM or analog audio.

The 32-pixel GRB NeoPixel FeatherWing factory jumper connects to GPIO 38
(`board.IO38`) on FeatherS2. Match physical header positions: the standard
Feather M0 D6 position is GPIO 38 here. FeatherS2's `board.D6` alias is GPIO 3
at a different position; using it left the wing dark. Keep brightness at 0.15
unless the user requests otherwise. The onboard APA102 is a separate LED.

## Previous hardware: Adafruit Feather ESP32 V2

Board ID `adafruit_feather_esp32_v2`, ESP32-PICO-V3-02 revision 3.1, 8 MB flash,
CircuitPython 10.3.1. Its wing uses `board.D32`. The original app is preserved
in `examples/esp32_rainbow.py`; deploy it only with `LEGACY_RAINBOW=1`.
Ordinary deployment installs the shared ESP-NOW consumer app. The app selects
GPIO 32 by board ID and rejects producer mode on this board.
It exposes USB serial only, whereas FeatherS2 exposes a CIRCUITPY drive.

## Didgeridoo installation

Use the 32-pixel FeatherWing preview of a ~100-foot culvert, player at midpoint.
Additional wings will be wireless ESP32 nodes, not one long wired pixel chain.
The current board is the microphone leader; ESP-NOW followers have their own
ESP32 and wing. Do not assume follower board types/pins without checking them.
Keep microphone capture out of follower mode. Per-node role/coordinates belong
in node_config.py; ordinary deployment preserves it, while NODE_CONFIG=...
explicitly replaces it. New boards default to consumers; do not infer producer
status from arbitrary nonzero microphone samples. Changing coordinates must not change the confirmed GPIOs.

Audio analysis uses 16 kHz, 1024-sample Hann FFT, 1024-sample contiguous hops, built-in ulab,
a participation-ratio noisiness estimate (optional logarithmic flatness),
and simultaneous drone/harmonic/growl/vocal envelopes with ATTACK/YELL events.
Keep spectral ratios and texture in the detectors: volume alone must not
classify a growl or yell. Maintain separate attack/release, gated slow background
learning, bounded reference adaptation, event rearm/cooldown, and long decay.
Default effect 0 (Spectrum, display 1) shows eight independent FFT bands as
bottom-up bars on the landscape 8x4 progressive matrix, with fractional top
pixels and a rainbow across frequency. Preserve shared slow normalization,
per-band background subtraction and separate fast attack/release. Consumers
receive eight levels over protocol v3 (51 bytes); update all nodes together.
Keep Ember/Aurora/Ripple musical layers and the 0.15 brightness cap. Spectrum
ignores axial coordinates; its rotation is independent of the portrait HUD.
Treat these as tunable acoustic heuristics; synthetic test success does not
establish didgeridoo classification accuracy in the culvert.

App 1.0.4 expands visual feature ranges using the September 16
didgeridoo take: timbre 0.12–0.45, growl 0.04–0.30, vocal 0.03–0.40. Detector
thresholds and Spectrum stay unchanged. Keep the 0.15 cap, event-age correction
on attack/yell blooms, and independent 3.5-second audio decay with shorter
0.28-second pixel trails. These changes are included in OTA 1.0.4; consumers
need the same renderer. README records comparison metrics and capture limits:
host cue delays lengthened sections and the 80-second log missed final decay.
Do not claim three confirmed yells or technique-classification accuracy.
The expressive-preview native benchmark ran each musical effect for eight
seconds with LEDs/health/watchdog and measured 13.4–14.3 fps, with many frames
over 64 ms. The subsequent soft restart hit a CircuitPython native hard fault;
files still matched and normal-mode hard reset was used for recovery. Do not
hide that limitation or infer a proven fault cause from the benchmark sequence.

## Workflow

- `code.py`, `boot.py`, `ota_*.py`: USB-managed OTA base and recovery loader.
- `lights_app.py`: capture, radio/render loops and hardware diagnostics.
- `config.py`, `node_config.py`: algorithm defaults and per-node overrides.
- `audio_spectrum.py`: shared spectral extraction, ulab device / NumPy host.
- `audio_features.py`: pure feature/envelope/event processing.
- `animation.py`, `effects.py`: native-array layered renderer, stable effect IDs,
  bounded pulse storage and debounced human controls.
- `radio_protocol.py`: pure packet/state logic; `wireless.py`: device ESP-NOW.
- `sound_reactive.py`: earlier helpers used by mic diagnostics.
- `tests/`: generated PCM, rendering and radio protocol tests via `make check`.
- `tools/board.py`: host deployment, console, firmware, and mic-test tooling.
- `Makefile`: deploy auto-detects supported board IDs; explicit BOARD enforces
  the model. Flash defaults to FeatherS2 and requires BOARD for ESP32 V2.
- `requirements.txt`, `requirements-dev.txt`: pinned host dependencies in `.venv`;
  NumPy is host-only, no board library bundle needed.

Run `make check` after changes. For authorized hardware work, run `make deploy`
and inspect readback and serial startup checks. `make test-mic` captures ten
seconds of levels, then resumes the app. `make benchmark` measures live
capture/FFT/render/radio work against the hop budget; keep timing warnings.
`make test-buttons` polls the producer's configured GPIOs for 20 seconds with
audio paused, logs raw levels and debounced presses, and resumes the app. Use
it to distinguish physical input from effect handling before changing pins.
The ESP32-S2 driver does not report every DMA overflow. Preserve gap recovery,
bounded radio sends, duplicate/event protection and link-loss fading. Effect ID
is repeated in every packet so lost changes self-correct. BOOT/IO0 advances
effects on the producer while running. Changes show display numbers 1..5
(protocol IDs 0..4) for 1.5 seconds on the local 4x8 wing, mirrored by consumers
on changed received IDs. Repeated packets must not restart the overlay. Keep
capture/radio/scene processing running under it, preserve the brightness cap,
and keep its physical mapping independent of culvert pixel_positions. Factory
progressive 8x4 wiring is rotated to portrait with pixel 0 bottom left; allow
per-node 180-degree rotation or an explicit map. BOOT selects download mode when held
during reset. Keep future button GPIOs out of the mic/wing pin set.
App 1.0.4 adds a second next-effect input on FeatherS2 IO43/TX to
GND, with its own debouncer/internal pull-up; BOOT/IO0 remains enabled. Configure
`button_extra_next_gpio` (default 43, None disables). It does not enter USB
maintenance. Keep diagnostics and duplicate/conflicting-pin validation aware of
both inputs. This is included in OTA app 1.0.4.
The initial IO18 USB deployment passed readback and startup but its button
test remained LOW. IO43 subsequently passed a 60-second native test with 23
presses/46 transitions, ending HIGH. USB deployment now selects it alongside
BOOT; all 18 files verified and both inputs initialized. Do not use IO38 for a
button or enable UART on IO43. The microphone became flat during the wiring
investigation, including a stereo test, but changing samples returned after
the final restore. See operations for the unexplained filesystem reset and
saved-profile/credential recovery; do not attribute it to a proven cause.
After reprovisioning, normal OTA boot checked in successfully and resumed audio
and ESP-NOW. Serial logs showed all four effect changes and wraparound while
microphone levels varied; no new two-wing visual confirmation was collected.
A USB deployment from CircuitPython USER safe mode can verify
files but fail startup; `microcontroller.on_next_reset(microcontroller.RunMode.NORMAL)`
followed by `microcontroller.reset()` exited it. Cleanly unmount host storage
before a hard reset changes filesystem ownership.
Hardware validation needs changing
levels on quiet/clap trials plus a visual LED check; don't equate serial logs
or nonzero noise with confirmed acoustic response. Calibration needs two
quiet seconds. Do not save or transmit recordings unless requested.
Two-node reception was verified on September 15, 2026: ESP32 V2 consumer
MAC 14:33:5c:97:f2:a0 received 94 packets with zero rejected from the FeatherS2
producer during eight seconds of startup. This does not prove culvert range,
visual synchronization, or musical recognition. Document measured evidence.
The user subsequently visually confirmed matching, readable effect numbers on
both wings during the automatic 2,3,4,1 demo. The default indicator orientation
and consumer mirroring are confirmed; musical classification remains unverified.

Native USB consoles need DTR asserted. Serial USB-UART bridges on the old ESP32
use low DTR/RTS. FeatherS2 deployment must write through the mounted USB drive,
with board ID and CPU UID verification; do not remount it writable from Python
while the USB host owns it. Preserve backups, temporary-file writes, readback
checks, timeout reporting, and serial startup handling.

Back up board files before firmware upgrades. FeatherS2 `make flash` requires
the identified FTHRS2BOOT drive and uses UF2. For old boards without that loader,
`make flash-rom` uses BOOT+RESET recovery, verifies ESP32-S2/16 MB, backs up all
flash, erases, and installs the official merged .bin at 0x0. That does not
install TinyUF2. A physical reset may be needed after ROM flashing.
For this early S2 revision, keep esptool at 115200 baud (USB transport still
runs quickly) with `--before no-reset --after no-reset-stub`. Automatic resets
and returning the stub to ROM disrupted USB on this Mac. Holding BOOT during
USB reconnection entered recovery reliably.
The old ESP32 V2 flash target
backs up all flash then erases it. Do not erase flash for an application error.
Use PORT and MOUNT overrides when discovery is ambiguous. ESP32 V2 deployment
uses serial temporary-file staging, local backups and final readback for all
app files; it must preserve node_config.py unless explicitly replaced. New
board models require a verified pin profile, not just an ESP32 chip match.

Update README.md for wiring, firmware, and command changes. Never commit
`.venv`, `.artifacts`, binaries, board backups, credentials, or recordings.
Backups can contain existing user data or secrets.

The user also visually confirmed rainbow spectrum bars rising and falling with
sound on both the FeatherS2 producer and ESP32 V2 consumer. The two-board
Spectrum response check is complete; culvert RF coverage and didgeridoo
classification remain unverified.

## OTA implementation

The user approved implementation of `docs/ota-plan.md`. It adapts
Gate's two-slot updater for multiple app modules and boot-time HTTPS check-ins
over open `openwireless.org`. Keep the cloud project/credentials separate from
Drawbridge. Wi-Fi association changes the ESP-NOW channel: proposed maintenance
and performance phases must explicitly restore the configured lighting channel.

See `docs/ota-operations.md` for commands and actual bench results. App releases
contain the ten modules listed in `ota_manifest.APP_FILES`, staged as complete
slot directories. Never include node_config.py/settings.toml/credentials in OTA
assets. Base changes need a base version bump and USB deployment after initial
release. Keep the original recovery app and active slot intact during download.
Use the local Node 22 runtime for web tools; `make web-test` includes browser and
Firestore emulator checks. Never run emulator tests against production. Cloud
project is digirdu-lights/us-east1; runtime and release service accounts have
scoped privileges. Google auth/App Check guard browser administration; device
HTTP uses per-device hashed credentials. Preserve these independent boundaries.
Feather ESP32 V2 maintenance uses board.BUTTON/GPIO38 with its external pull-up;
GPIO0 is its status NeoPixel. FeatherS2 uses BOOT/IO0 during the startup blue
window, after RESET is released. Never transplant button pin assumptions.

OTA base 1.0.1 skips networking on the first boot that rejects an interrupted
trial or corrupt active slot; preserve this immediate return to lighting. Report
on a later normal boot. A native ESP32 V2 test with base 1.0.0 rejected a hung
candidate but hit a CircuitPython hard fault during the immediate Wi-Fi phase.
Keep the serial connection open across trial resets; reconnecting a USB-UART
bridge can interrupt the trial and correctly cause rollback.

The ESP32 V2 consumer completed a fully automatic OTA 1.0.1 -> 1.0.2 with base
1.0.1: ten files verified, 30-second trial confirmed, Firebase actual-version
report recorded, and ESP-NOW channel 1 reception resumed. Native exception and
watchdog rollback were exercised; physical maintenance/power-cut qualification
is tracked separately. See operations for current status.

ESP-NOW receive reads must be gated by the native `read_success` counter,
which advances after the complete RX callback. CircuitPython 10.3.1's `read()`
and `len()` can observe partially copied packets on ESP32 V2; ungated polling
reproduced `ValueError: Invalid buffer` in 36 ms. Track consumed native packets
separately from accepted protocol packets, handle 32-bit wrap, and retain the
8-packet drain bound. Never remove this gate or substitute `bool(radio)`.

On September 16, 2026, the user confirmed Google sign-in and viewing the consumer
in the live Firebase fleet dashboard. The authenticated read flow is verified;
this confirmation does not establish live administrative mutation tests.

The producer FeatherS2 completed USB bootstrap/provisioning on September 16,
2026: app 1.0.3, base 1.0.1, OTA enabled, Firebase check-in verified, followed
by I2S capture and ESP-NOW channel 1. It reports recovery/sequence 0 because
the USB copy already equals latest; it has not yet performed a newer-app OTA
trial. The LED-enabled 12-second benchmark with watchdog/health monitoring
measured 12.1 fps, 74.6 ms mean work, 136/146 frames over 64 ms, and no radio
errors. Preserve this limitation in reporting; zero detected discontinuities
does not prove lossless audio capture. With OTA enabled, run USB deployment and
producer diagnostics from BOOT-after-reset maintenance mode.
The user's RESET-then-BOOT test reached `DIGIRDU_BOOT mode=maintenance` in
boot_out.txt, then returned to OTA mode with host read-only storage, a fresh
Firebase report and continuing audio. Host writes in that maintenance window
and physical power-cut qualification were not tested.

The web account control is shared by the fleet and public Effects guide.
Use Firebase's user photo with an initials fallback; keep sign-out in its
keyboard-accessible dropdown. Update `web/effects.html` alongside changes to
the released effect library/defaults and its documented firmware version.


## Saved samples and Chroma (1.0.4)

The user authorized saving the playing samples. Preserve the local ignored
`.artifacts/samples/didgeridoo-2026-09-16/` take/manifest and original capture;
never treat these feature logs as PCM or commit recordings. `make replay`
runs actual renderers into a self-contained local HTML player; regenerate it
when animations change. Sample-and-hold, reconstructed envelopes and synthetic
tail are deliberate and must remain labelled. Tests use generated fixtures.
Chroma appends effect ID 4/display 5 (cyan digit), mapping a coarse eight-band
power centroid through log-frequency bounds 153.28–350.55 Hz, fitted to 63
active paired observations. Preserve volume-only brightness, separate color
and attack/release smoothing, quiet hue hold and 0.15 cap. This is spectral
color, not pitch identification. No wire-format change, but older consumers
reject effect ID 4; update all nodes before using it. Chroma is included in OTA release 1.0.4.

The user requested the replay on the public Effects overview. The page now
describes firmware 1.0.4 with five effects, using the September 16 captured take. `make replay-web` exports public rendered LED frames and
section labels to `web/assets/effects-replay.json`; this derived visualization
is authorized for the site. Keep original feature captures local and ignored.
Regenerate the snapshot after renderer changes; website builds use the saved
asset without reading private captures. Preserve paused-by-default playback,
seek controls, synthetic-tail labelling, fetch-failure fallback and OTA compatibility notes. The replay cannot send device commands or record audio.
