# OTA application upgrades

The updater uses GitHub Releases, authenticated Firebase HTTPS, two complete
application slots and automatic trial rollback. Every device first needs a USB
bootstrap and its own token. The original design is in [ota-plan.md](ota-plan.md).
See the validation section below for what has actually been tested.

## Versions and files

`app_version.py` identifies the application (first OTA release 1.0.1);
`ota_manifest.py` identifies the USB-installed base, currently 1.0.1. CircuitPython remains pinned to 10.3.1.

- `code.py`, `boot.py`, `ota_*.py` and `certs/` are the USB-managed base.
- `lights_app.py` contains the previous audio/render/control loops. The other
  application modules remain modular source files at the repository root.
- USB deploy installs all ten application modules under `/recovery/`.
- `/ota/slot0/` and `/ota/slot1/` contain complete OTA applications. The loader
  imports only the selected directory plus base libraries. It cannot fill in a
  missing module from another application version.
- `/ota/state0.json` and `state1.json` alternate checksummed journal generations.
  An interrupted candidate does not overwrite the working slot or root recovery.
- `/node_config.py` retains the board's role and overrides. `/settings.toml`
  retains its credential. Neither is an OTA release asset.

Normal application work changes the application files. A change to boot,
recovery, HTTP, certificates, manifest compatibility or the loader needs a new
base version and deliberate USB deployment. Application OTA cannot replace the
base or CircuitPython itself. The API boundary is a convention for trusted
Python, not a sandbox against malicious release authors.

Base 1.0.1 resumes lighting immediately after an interrupted trial or corrupt
active slot, deferring the cloud report until a later normal boot. This avoids
reconnecting Wi-Fi during the first watchdog recovery boot. Base 1.0.0 boards
need `make deploy-base` over USB; application release 1.0.2 requires base 1.0.1.
App 1.0.2 retains the same audio, effects and ESP-NOW protocol as 1.0.1.

## Initial deployment and enrollment

```sh
make setup
make check
make deploy PORT=/dev/cu.usbserial-...  # Auto-detects supported hardware
make web-setup
make ota-enroll DEVICE_ID=<full-lowercase-cpu-uid> BOARD=adafruit_feather_esp32_v2 ROLE=consumer
make ota-provision DEVICE_ID=<uid> PORT=/dev/cu.usbserial-...
```

For the microphone board use `BOARD=unexpectedmaker_feathers2 ROLE=producer`.
Known full IDs are consumer `4133c5792f0a` and producer `c7fd1a30c4c2`.
The provisioner verifies board model and CPU UID, preserves unrelated TOML
settings, stores a local backup with owner-only permissions, and verifies the
new bytes. Enrollment stores a random token in ignored `.artifacts/ota/<id>.json`
and only its SHA-256 in Firestore. It refuses accidental re-enrollment/rotation.
Do not copy a token to a different board or commit populated settings/backups.

OTA is initially disabled. Enable it after bench validation:

```sh
make ota-provision DEVICE_ID=<uid> PORT=/dev/cu.usbserial-... OTA_ENABLE=1
```

Hard-reset to run `boot.py` and apply filesystem ownership. The normal update
SSID is `openwireless.org` with no password. No captive portal is started.
Tokens authenticate only their own device's reports and approved downloads.
They do not grant fleet administration. Physical access to the filesystem can
read them; there is no encrypted secret storage.

## Maintenance and USB repair

When OTA is enabled, a hard reset shows a dim blue wing for two seconds. During
that window, press the board's maintenance button:

| Board | Button | GPIO |
| --- | --- | --- |
| Unexpected Maker FeatherS2 | BOOT, pressed **after** releasing RESET | IO0 |
| Adafruit Feather ESP32 V2 | SW38 user button | `board.BUTTON`, GPIO38 |

GPIO0 on ESP32 V2 is the onboard NeoPixel, not the user button. Its GPIO38
button has an external pull-up; do not enable an unsupported internal pull-up.
On FeatherS2, holding BOOT through reset enters ROM download mode instead of
application maintenance. BOOT retains effect selection during normal playback.

Maintenance keeps the device filesystem read-only to CircuitPython and permits
USB-host writes on FeatherS2. The ESP32 V2 uses the serial REPL. Do not bypass
concurrent-write protection or try host writes to a field-owned CIRCUITPY drive.
`make deploy` preserves node configuration, settings and OTA slots/journals.
`make deploy-base` updates only the base and certificates, preserving the USB
recovery app too. Host tooling disables the watchdog after entering the REPL
so deliberate USB work is not interrupted by a field watchdog reset.
A normal USB deploy updates the recovery copy and base; it does not silently
replace a confirmed OTA selection. To repair/select the USB recovery application,
back up the journals, then remove both `/ota/state*.json` in maintenance mode.
This is a deliberate recovery operation, not part of routine deploy.

Field mode writes through CircuitPython. A selected trial is marked started
before import. Failure or a reset before confirmation reselects the previous
working copy. A watchdog catches a stuck application loop. The immediate recovery boot
skips networking so the working app can resume; its saved failure report is
sent on a later normal boot. After a failed
candidate, the same deployment sequence is not retried; assign a newer sequence
or release. There is always a USB recovery path, but FAT/filesystem corruption
can still require manual repair. Two directories are not independent flash banks.

## Boot behavior and reporting

The board makes one bounded Wi-Fi attempt (8-second association timeout, 0–2 s
jitter), then checks in with its actual app/base/interpreter versions and saved
update outcome. The HTTP client verifies certificates and hostname using the
public Google roots, rejects redirects/compression and malformed framing, and
bounds body sizes, socket waits and maintenance time. A watchdog reset during
networking skips networking once on the next boot. NVM bytes 0–4 are reserved
for the `DGO1` marker and this skip flag; credentials are never stored there.

The newest compatible stable release is selected unless the device is pinned,
paused or revoked. An unavailable network leaves the installed application
running. TLS buffers/sockets are released and the AP disconnected before the
existing ESP-NOW initialization restores channel 1 (or the node's configured
channel). Consumers update independently; the producer does not relay firmware.

A candidate must run for 30 seconds after calibration with advancing render
frames and bounded finite features. Producer initialization includes I2S; a
consumer need not hear a producer to be healthy. A successful trial confirms
locally, pauses for one bounded report attempt, then restarts into normal
lighting. Failed reporting is retained for a later boot. Ordinary playback
makes no periodic internet connections. The dashboard timestamp is last report,
not proof of current reachability, sound recognition or physical LED output.

## Release workflow

```sh
# Edit app_version.py, test, commit, and push first.
git tag firmware-v1.2.0
git push origin firmware-v1.2.0
make firmware-build VERSION=1.2.0
make firmware-release VERSION=1.2.0
```

The build requires a clean tree and a matching tag at HEAD. It emits individual
app files and `manifest.json`, plus `base-firmware.zip` and `base-manifest.json`
for USB maintenance. Artifacts exclude node configuration, credentials and
recordings. Existing local artifacts cannot be replaced with different bytes.

The GitHub `Verify and import firmware release` workflow runs on published
non-prerelease releases. It uses short-lived workload identity, verifies asset
hashes against the tagged source, mirrors files into create-only Storage objects,
and advances stable to the highest semantic version. There are no static cloud
keys in GitHub. `make firmware-import VERSION=...` provides the same import using
local gcloud credentials. Import failure leaves the prior stable target intact.

Devices select the highest compatible imported version; a newer release requiring
an unavailable USB base does not hide an older compatible application. Routine
releases must retain protocol compatibility across independently updating nodes.
A breaking ESP-NOW change needs staged consumer support before producer migration.
An intentional rollback uses a newer deployment sequence even with older app bytes.

## Firebase operations

Project: **digirdu-lights**, region **us-east1**. Dashboard:
https://digirdu-lights.firebaseapp.com. Runtime identity is
`digirdu-functions@digirdu-lights.iam.gserviceaccount.com`; release import uses
`digirdu-releases@digirdu-lights.iam.gserviceaccount.com`. They have scoped database
and private firmware bucket access. Functions have zero minimum instances and
three maximum instances; container build images expire after seven days.
Drawbridge's project and credentials are separate.

```sh
make web-setup
.venv/bin/python tools/cloud.py web-config
make admin-seed EMAIL=nick.stielau@gmail.com
make web-test
make web-build
make web-deploy
make ota-status
```

Google sign-in and App Check protect browser administration. Google provider
setup requires enabling it in the Firebase console with a support email/OAuth
client. Device endpoints use per-device tokens instead of App Check. Firestore
client rules deny all access; Functions return bounded, authorized views.

The dashboard shows reported app/base versions, desired version, board/role,
last report and update outcome. It supports pinning/rollback, follow-latest,
pause/resume, rename and token revocation. Revocation stops subsequent device
requests and requires deliberate re-enrollment/USB provisioning to restore.
Pausing affects future requests; a device that has already downloaded a verified
bundle may finish its trial. A requested target is never shown as installed
until the device reports it. No API or credentials are service-worker cached.

## Validation

Implemented checks include 76 host firmware tests, backend contract tests,
Firestore emulator authorization/transaction/rule tests, and mobile Chromium
and WebKit dashboard tests. Emulator tests refuse non-local database targets.
The consumer has booted the USB recovery bundle and resumed real ESP-NOW
reception. It sees `openwireless.org`, has approximately 1.9 MB free heap, and
has passed native SHA-256 and storage-capacity probes.

A native HTTPS check-in succeeded over open `openwireless.org`: Firebase recorded
consumer app 1.0.0, base 1.0.0 and the correct hardware/role. The consumer then
returned to ESP-NOW channel 1 and received changing Spectrum data. The dashboard
loads publicly; unauthenticated device requests return HTTP 401. Google sign-in
is enabled and its live popup reaches accounts.google.com. On September 16,
2026, the user confirmed signing in as nick.stielau@gmail.com and viewing the
consumer in the live fleet dashboard. This confirms the authenticated read
flow; live pin/pause/revocation actions have not been user-verified.

The consumer downloaded and SHA-256 verified all ten 1.0.1 release modules over
HTTPS, ran the 30-second trial, and reported `state=current` with 931 frames and
362 received packets. After the confirmation reboot it resumed ESP-NOW channel 1.
A locally injected candidate that raises `RuntimeError` on import rolled back
to the verified 1.0.1 slot and resumed reception. Fault candidates are never
published to GitHub or imported into the cloud.

The initial network attempt reset and recovered into lighting; its cause was
not established. A diagnostic download with the watchdog disabled succeeded;
the subsequent trial and confirmation used the normal watchdog. Reopening the
USB serial bridge also interrupted an early trial, correctly causing rollback.
Keep one serial connection open across resets when measuring a whole update.

A deliberately frozen candidate triggered the 20-second watchdog. Base 1.0.0
selected the correct previous slot but suffered a CircuitPython hard fault
while immediately reconnecting Wi-Fi. After USB installation of base 1.0.1,
the repeated frozen-candidate test rolled back, skipped that network phase and
resumed live ESP-NOW reception (13 packets by frame 33). The server's deployment
counter was advanced beyond the local fault-test sequences; no faulty releases
were published. Application 1.0.2 requires this updated base.

A complete automatic update from 1.0.1 to **1.0.2** then passed with the normal
watchdog enabled throughout. On boot the consumer joined the open SSID,
downloaded all ten modules (58,207 bytes), verified/staged them, rebooted into
the trial and confirmed after 931 frames / 373 received packets. Firebase
recorded app 1.0.2, base 1.0.1, deployment sequence 6 and `state=current`.
After the confirmation reboot it resumed live Spectrum reception on channel 1.
Both GitHub check runs and the release-import workflow passed for 1.0.2.

Both boards have completed USB bootstrap and provisioning; producer details
are below. Physical maintenance and power-loss qualification are tracked
separately from the host tests. Serial reception and pixel-buffer values are not a new visual
confirmation of the installed LEDs.

### Follow-up: intermittent receiver failure

After the successful 1.0.2 update trial, the consumer later saved `ValueError`
and selected USB recovery 1.0.0. Both OTA slots still matched their release
hashes. A direct native receive stress test reproduced `ValueError: Invalid
buffer` after 1,727 polls / 36 ms. CircuitPython 10.3.1 appends the incoming
header, MAC and payload separately, while `read()` tests only whether any bytes
are available.

App 1.0.3 gates reads on `ESPNow.read_success`, which the driver increments
after the complete packet is appended. Consumed native packets are counted
independently of rejected/accepted protocol packets, with 32-bit wrap handling
and the existing eight-packet drain limit. The base remains 1.0.1. This fixes
a reproduced radio failure; the earlier saved error contained only its class,
so it cannot establish that every observed dark interval had this cause.

The fixed native receive path passed 539,217 rapid polling iterations over
30 seconds, receiving 356 valid packets with zero rejected packets or buffer
exceptions. Regression tests cover callback completion, rejected-packet counting,
bounded draining and native counter wraparound.

The consumer subsequently completed the automatic 1.0.3 download, reboot and
30-second health trial. Firebase recorded app 1.0.3 / base 1.0.1, deployment
sequence 7, `state=current`, 931 frames and 360 received packets. Live ESP-NOW
reception resumed after confirmation. GitHub checks and release import passed.

Upstream details: CircuitPython 10.3.1's
[ESP-NOW receive callback and reader](https://github.com/adafruit/circuitpython/blob/10.3.1/ports/espressif/common-hal/espnow/ESPNow.c).

The connected ESP32 V2's USB recovery copy was also updated to 1.0.3 using
`make deploy`, with all 18 deployed files verified and node credentials/profile
preserved. Recovery startup received 85 valid packets in its startup check.
Near-silent spectrum values can legitimately leave the wing dark despite a
live radio link.

### Producer bootstrap (September 16, 2026)

The FeatherS2 `c7fd1a30c4c2` was identified through both USB and CIRCUITPY.
`make deploy` installed and verified all 18 base/recovery files, preserving
`radio_role="producer"` and BOOT/GPIO0. The first staging attempt hit a host USB
I/O error before replacing the original app. The original root app files were
backed up; `diskutil verifyVolume` reported a clean filesystem and remounted
the drive. The retry succeeded without erasing or reformatting flash.

The device-specific credential was provisioned and OTA enabled. The reserved
NVM bytes were checked before use. The host volume was cleanly unmounted before
a hard reset transferred filesystem ownership to CircuitPython; macOS then
mounted CIRCUITPY read-only. Firebase recorded the producer's actual app **1.0.3**,
base **1.0.1**, CircuitPython **10.3.1**, correct board/role and no error.
It disconnected from the AP, resumed ESP-NOW channel 1 and showed microphone
RMS levels changing from roughly 2 to 370 with rising/falling spectrum bars in
the output data. A 65-second observation completed without a reset. This is
serial/feature evidence, not a new visual confirmation on both wings.

The producer reports `state=recovery`, sequence 0 because it is running the
USB-installed app, which already matches the latest release. This is expected
and is not a failed update. A future newer compatible release will download
into an OTA slot and undergo its 30-second trial. Actual OTA download/trial
was verified on the consumer; the producer's current test verifies enrollment,
HTTPS check-in, filesystem ownership, microphone processing and radio startup.

The LED-enabled benchmark with watchdog and health checks measured 146 frames
in 12 seconds (12.1 fps), 74.6 ms mean / 93.0 ms maximum work, 136 frames over
the 64 ms budget, zero detected discontinuities and 146 sends without errors
or skips. See [benchmark interpretation](../README.md#producer-with-ota-health-monitoring-september-16-2026).

During the user's RESET-then-BOOT test, a host poll observed
`DIGIRDU_BOOT mode=maintenance` in `boot_out.txt`. The board subsequently
returned to normal OTA mode with CIRCUITPY read-only to the host. A new Firebase
check-in reported app 1.0.3 with no error, and a passive ten-second serial check
showed continuing microphone levels, spectrum changes and attack events.
This verifies that the physical maintenance branch was reached; host writes
during that window were not tested. Consumer physical maintenance and power-cut
qualification remain separate outstanding checks.
