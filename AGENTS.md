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
Treat these as tunable acoustic heuristics; synthetic test success does not
establish didgeridoo classification accuracy in the culvert.

## Workflow

- `code.py`: capture, radio/render loops and hardware diagnostics.
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
effects on the producer while running; it selects download mode when held
during reset. Keep future button GPIOs out of the mic/wing pin set.
Hardware validation needs changing
levels on quiet/clap trials plus a visual LED check; don't equate serial logs
or nonzero noise with confirmed acoustic response. Calibration needs two
quiet seconds. Do not save or transmit recordings unless requested.
Two-node reception was verified on September 15, 2026: ESP32 V2 consumer
MAC 14:33:5c:97:f2:a0 received 94 packets with zero rejected from the FeatherS2
producer during eight seconds of startup. This does not prove culvert range,
visual synchronization, or musical recognition. Document measured evidence.

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
