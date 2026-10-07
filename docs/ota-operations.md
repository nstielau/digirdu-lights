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
On Reverse TFT boards, the same state is visible on the display: an amber
`USB MAINT` badge and border appear on the EchoGlow splash, followed by
`CIRCUITPY READY`; the running dashboard keeps an amber `USB MAINTENANCE`
strip on every page. The `FTHRS3BOOT` TinyUF2 drive is earlier than
CircuitPython, so the TFT cannot display a status while that bootloader is
active.
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

### IO43 button USB update

The external button moved from an unsuccessful IO18 trial to IO43/TX, with
BOOT/IO0 retained. A 60-second native input test recorded 23 debounced presses,
46 transitions and a final HIGH state. IO38 is reserved for the wing data line.
This is a USB development change based on 1.0.3, not a new published OTA release.

The first IO43 deployment hit `EINVAL` accessing `/Volumes/CIRCUITPY/boot.py`.
After `diskutil verifyVolume` reported a clean filesystem and remounted it, the
same FeatherS2 UID showed only default `Hello World` files and empty settings.
The reason for this filesystem reset was not established; no erase, format or
firmware flash was requested by the host tooling. Do not equate a clean FAT
check with verification that application files or credentials are still present.

The saved producer profile was explicitly supplied to a fresh `make deploy`.
All 18 base/recovery files then verified; startup initialized BOOT/GPIO0 and
GPIO43, ESP-NOW channel 1, and changing microphone samples. The earlier flat
microphone failure did not recur in that startup check. The saved device
credential was reprovisioned with OTA enabled, preserving the enrolled identity.
After cleanly unmounting USB storage and resetting, Firebase recorded a fresh
producer check-in with app 1.0.3/base 1.0.1 and no error. CIRCUITPY returned to
host read-only mode. The 45-second boot observation showed changing audio
(logged RMS roughly 4 to 1,079), live spectrum values, and the complete effect
cycle Spectrum → Ember → Aurora → Ripple → Spectrum while audio continued.
This confirms the app's button/effect path in serial output; neither a new
two-wing visual confirmation nor a consumer reception test was performed.


## Chroma release 1.0.4

Application 1.0.4 includes Chroma (display 5, protocol ID 4), stronger
Ember/Aurora/Ripple motion and accents, and the FeatherS2 IO43-to-GND effect
button. It retains the ESP-NOW receive-completion fix from 1.0.3. Base 1.0.1,
CircuitPython 10.3.1, the ten-module app bundle and 51-byte protocol v3 remain
unchanged. Device profiles and credentials remain local.

Roll out to consumers first, then the microphone producer. Keep effects 1–4
selected until all nodes report 1.0.4: consumers on older apps reject effect ID
4 and fade if it stays selected. Spectrum remains the startup default. This
release does not introduce periodic OTA polling or remote resets; each board
checks at normal boot, runs a 30-second health trial, confirms and resumes
ESP-NOW. Use RESET alone, without pressing the maintenance button. Keep open
`openwireless.org` in range. Confirm actual reported versions and outcomes;
publishing a target alone does not prove that boards installed it.

### 1.0.4 rollout evidence (September 16, 2026)

Release source `804f988` and tag `firmware-v1.0.4` were pushed. GitHub's source
checks and release-import workflow passed. The immutable ten-module bundle is
64,209 bytes; Firebase selected deployment sequence 9. The website now labels
the effect library and saved replay as firmware 1.0.4.

The USB-connected ESP32 V2 consumer downloaded and staged 1.0.4 over HTTPS,
rebooted into its trial, then confirmed. Firebase recorded **1.0.4 / base 1.0.1**,
`state=current`, sequence **9**, empty error, **931 frames / 308 packets** in
the trial report. Serial logs showed the cyan number 5, Chroma pixel output
responding to transmitted sound features, and zero rejected packets. After
confirmation/reboot, the consumer resumed Chroma on ESP-NOW channel 1.
These are packet/pixel-buffer observations, not new physical LED confirmation.

After the user reset the separately powered FeatherS2 producer, its boot check
reported the previous USB recovery version and then completed the OTA trial.
Firebase recorded producer **1.0.4 / base 1.0.1**, `state=current`, deployment
sequence **9**, empty error, **415 frames / 286 sends**, and `active=true` in
the confirmation report. Both devices now report the same installed release.
The connected consumer briefly faded during the producer's confirmation/report
and reboot, then resumed live Spectrum reception with zero rejected packets
(365 packets observed after its own latest reboot). Spectrum is the expected
startup effect; Chroma remains effect 5. No new visual LED confirmation was
requested or inferred from these logs. This also verifies the producer's first
newer-version OTA download/trial beyond its USB bootstrap.


## Hold-to-sleep release 1.0.5

App 1.0.5 adds a three-second button hold followed by a three-second red fade
and reset-only deep sleep. Short effect presses now fire on release. Install
consumers first, then the producer; 1.0.4 and older ignore sleep-control packets.
The feature protocol remains v3 and base 1.0.1 needs no USB change. An independent
DGRS control frame carries the repeated sleep countdown. A consumer must have
received a recent feature frame from the same producer session before it accepts
sleep; duplicate/stale/wrong-source commands cannot restart a fade.
Sleep is ignored during the initial 30-second OTA health trial. After confirming,
the reboot starts the app normally and enables sleep. An ordinary intentional
sleep leaves confirmed OTA journals intact; no rollback or persistent sleep flag
is written. Reset each sleeping board separately to wake and run its boot-time
update check. With a USB/BLE host attached, CircuitPython may simulate sleep.
Host regression tests do not establish actual sleep current or visual behavior.

### 1.0.5 rollout evidence

Source `c89b6d4` / tag `firmware-v1.0.5` was pushed and published. GitHub checks
and immutable import passed; the ten app files total 70,968 bytes. All 100 host
firmware tests, web/backend/emulator tests and 30 browser tests passed. The
Effects page was published with the short-release and hold-to-sleep instructions.

The ESP32 V2 consumer downloaded/verified 1.0.5 and confirmed its OTA trial.
Firebase recorded app **1.0.5**, base **1.0.1**, `state=current`, deployment
sequence **10**, no error, **826 frames / 287 received packets**. It then
rebooted and resumed live Ember reception with zero rejected packets. Its
native CircuitPython image exposes the deep-sleep API. The producer subsequently confirmed too (below). Actual red-fade appearance,
deep-sleep current and reset wake-up still require the physical test. A host-connected sleep test alone cannot establish true
low-power consumption.


The producer's normal reset then completed the **1.0.5** OTA trial. Firebase
recorded app 1.0.5 / base 1.0.1, `state=current`, sequence 10, no error, **405
frames / 292 sends**. Both nodes now report 1.0.5. The consumer briefly faded
during the producer's confirmation/reboot, then resumed Spectrum with zero
rejected packets. The physical long-press test is separate from this OTA result.


During the subsequent user-triggered long press, the consumer received the
sleep broadcast at host log time **202.099 s** with **3.00 s remaining** and
logged deep-sleep entry at **205.117 s**: **3.018 s** later. Its output reported
32 lit pixels with peaks decreasing **28 → 15 → 2**, and zero rejected packets.
Cleanup completed without a traceback or OTA failure message; the app stopped
with autoreload off and the USB console retained. This validates native command
receipt, fade timing and handoff to the alarm API. It does not establish true
low-power current on USB, the producer's physical appearance, or reset wake-up.
Logs remain ignored under `.artifacts/sleep-physical-test.log` and
`.artifacts/sleep-physical-events.jsonl`. User visual/reset confirmation remains
separate from the native consumer result.


## Sleep output hold 1.0.6

After the native 1.0.5 sleep test, the user reported one bright white pixel on
the wing with slight color changes. This is not a passed dark-state visual
check. Version 1.0.6 addresses the potentially floating GPIO during VM teardown:
reclaim the verified wing pin after cleanup, send black, drive LOW, wait 1 ms,
then preserve its output state through the alarm call. It uses no wake alarms
and does not require an updated USB base. The suspected cause still needs a
physical retest. Both nodes need a normal reset to wake/check for this update.

Both nodes subsequently confirmed **1.0.6**, base **1.0.1**, deployment
sequence **11**, `state=current`, with no reported OTA error. The consumer
trial recorded **931 frames / 256 packets**; the producer recorded **406
frames / 290 sends**. GitHub checks and release import passed. After its
confirmation reboot, the consumer ran but reported no received packets;
restored reception and the repeat physical sleep test remain pending. These
reports establish installation, not a passed dark-state test.

After connecting the producer to USB, passive console capture showed changing
microphone features with no captured exception. Its active OTA journal was
current with no trial/error, and all ten active files matched their 1.0.6
manifest hashes. The user then confirmed both wings respond to claps again,
establishing restored audio/LED response and wireless reception. The earlier
dark state remains unexplained; this does not establish a crash or its cause.

The 1.0.6 physical sleep retest passed: the user confirmed **both wings faded
red to completely black and stayed black**, including the previously white
pixel. The producer console recorded the sleep request at **28.632 s** and
alarm handoff with the wing data held LOW at **31.749 s** (**3.117 s** later),
without a traceback. The USB console then reported `Code done running`.
Logs are local under `.artifacts/sleep-106-producer.log` and
`.artifacts/sleep-106-producer-events.jsonl`. This confirms the visual result
and native producer handoff; electrical sleep current remains unmeasured.

The user then reset each board with BOOT released and confirmed **both wings
respond to claps again**. Producer USB reconnected and passive logs showed
changing audio features. This completes the two-board visual fade/dark-state
and physical-reset wake test for 1.0.6.

## USB base 1.0.2: OTA activity indicator

The base now shows one cyan pixel during check-in, download and confirmation
reporting, moving to the next physical pixel at two-second service intervals.
Only one of 32 pixels is lit, at 15% maximum brightness; blocking network calls
pause movement. It is an activity marker, not a download percentage. Cleanup
blacks the wing and releases its pin on both normal and network-error exits.
Audio/ESP-NOW resumes through the existing boot flow.

This requires `make deploy-base` over USB on each node (FeatherS2 requires
BOOT-after-RESET maintenance mode). Preserve recovery/active/trial slots,
settings and node identity. App remains 1.0.6; base 1.0.1 remains compatible
with app OTA, with APP_MINIMUM_BASE separate from the installed BASE_VERSION.
Host checks pass 104 tests, including pin mapping, capped single-pixel stepping,
wraparound, error cleanup and unchanged app compatibility. Hardware deployment
and visual confirmation are tracked separately below.

The FeatherS2 producer received all seven base files through `make deploy-base`
with successful readback. After unmounting CIRCUITPY and a normal hard reset,
serial reported app **1.0.6 / base 1.0.2**, completed network maintenance and
resumed I2S/ESP-NOW. Firebase confirmed current 1.0.6, sequence 11, base 1.0.2,
no error. The ESP32 V2 consumer still reports base 1.0.1 and needs its own USB
base deployment. Visual confirmation of the activity indicator is separate
from file verification and the successful boot.
The user subsequently confirmed seeing the advancing cyan pixel during the
producer's OTA check, followed by the normal audio effects. Producer visual
verification is complete.

The ESP32 V2 consumer then received and verified the same seven base files.
After normal reset, Firebase reported **app 1.0.6 / base 1.0.2**, current,
sequence 11, no error on both devices. Consumer logs showed live reception
with **198 accepted / 0 rejected packets** after resuming. Its native boot
capture is `.artifacts/ota-indicator-consumer-boot.log`; producer capture is
`.artifacts/ota-indicator-producer-boot.log`. Consumer visual confirmation
remains separate from these serial/fleet results.

The user then confirmed the consumer's indicator too, but found it too bright
and slow on both boards. USB base **1.0.3** changes only the indicator to
**3% brightness** (integer GRB `7, 0, 7`) and a **0.5-second step interval**.
The audio-effect brightness cap stays 15%. Blocking Wi-Fi/TLS can still hold
the current pixel until control returns. This tuning needs another USB base
deployment on each device; the OTA app remains 1.0.6.

The ESP32 V2 consumer's seven base files verified, and a normal reboot reported
**app 1.0.6 / base 1.0.3** to Firebase with no error. ESP-NOW reception resumed
with **103 accepted / 0 rejected packets** in the startup log
`.artifacts/ota-dim-consumer-boot.log`. All 104 host tests passed. Producer
deployment and the user's assessment of the revised appearance remain pending.

The producer subsequently verified all seven base files too. The deploy
startup check encountered BOOT-triggered CircuitPython USER safe mode. After
cleanly unmounting CIRCUITPY, a normal-mode hard reset restored app startup;
serial reported **app 1.0.6 / base 1.0.3** and resumed microphone capture and
ESP-NOW. No flash erase or app-slot replacement was needed. Both devices now
report base 1.0.3/current app 1.0.6 with no OTA error. The capture is
`.artifacts/ota-dim-producer-boot.log`. GitHub checks passed; the revised
brightness/speed preference has not yet been visually assessed by the user.

## Battery support: app 1.0.7 / USB base 1.0.4

The optional `battery` report field has an explicit status and nullable voltage;
the API still accepts old reports without it. The fleet view labels it as the
last reported BAT/JST voltage, not a live percentage or battery-presence signal.
ESP32 V2 uses its ADC1 GPIO35 divider. Original FeatherS2 reports unsupported
until external sensing is explicitly wired and implemented.

`battery.py` is a shared base module preloaded by ota_bootstrap, and is included
in the eight USB base files. Base deployment preserves recovery/OTA slots and
credentials. App 1.0.7 requires minimum base 1.0.4; publish/deploy the compatible
API first, then USB bases, then boot into app OTA. Existing bases stay compatible
with earlier app releases and old-format reports. No credentials or sensor
values are included in release assets.

Effect 6 selects the local battery gauge/scrolling voltage on each wing. Voltage
does not enter the ESP-NOW feature packet; it remains protocol v3. Upgrade all
consumers before selecting Battery. The display refreshes locally every two
seconds, while cloud snapshots occur only during boot-time network maintenance.
ADC resources are released after each read, and errors replace stale readings.
Host checks cover sensor conversion/cleanup, unsupported S2, error/null states,
report snapshots, local display after radio loss, gauge/scroll/rotation/caps and
cloud schema/round-trip behavior. Native readings, multimeter calibration and
visual acceptance require hardware and are tracked separately.

Release **1.0.7**, tag `firmware-v1.0.7`, source `2243603`, was published and
imported as stable. Firmware/dashboard GitHub checks passed. Local validation
passed **111 firmware tests**, web/API tests, **30 browser tests** and **12
Firestore emulator tests**. The deviceApi function and hosting were deployed
successfully before release publication; old reports remain accepted.

No USB board was connected during implementation, so base 1.0.4 deployment,
native ADC accuracy, actual battery reports, and the two-wing visual test are
pending. Existing base 1.0.3 devices retain compatible app 1.0.6 until their
USB base upgrade. `.artifacts/battery-preview.html` previews actual renderer
frames using clearly labelled simulated 3.3/3.7/4.2 V values and unavailable
state; these are not hardware measurements or saved playing data.

### Consumer deployment, September 20, 2026

The user confirmed LiPo batteries on BAT/JST. After USB enumeration returned,
the first deployment attempt lost its USB connection during setup. A retry
verified all **eight base files** without erasing flash. The ESP32 V2 consumer
then downloaded and confirmed app **1.0.7 / base 1.0.4**, deployment sequence
**12**, with no OTA error and **931 frames** in its health trial. No producer
packets were received during this trial; this does not verify the current RF
link. Firebase accepted the new battery report, **4.379 V / measured**.

An independent native ADC sequence sampled at 20 ms intervals returned
**4.382–4.388 V**. The readings are stable, but not checked against a
multimeter; no calibration gain was changed to force an expected voltage.
The USB-powered charging state can affect the terminal reading. Base readback
and OTA logs are `.artifacts/battery-consumer-base-deploy.log` and
`.artifacts/battery-consumer-ota.log`. Producer base/app upgrade and visual
acceptance are tracked separately from this successful consumer report.


### Gauge-only display: app 1.0.8

The user confirmed both displays appeared, but found scrolling voltage hard to
read. App 1.0.8 keeps the portrait battery gauge visible continuously after the
effect number. Numeric voltage remains in device reports. The 3% cap,
two-second sampling, local readings and unavailable dashes are unchanged.
This is an app-only OTA change; USB base 1.0.4 remains compatible.

The repeated consumer demo ran 60 seconds / 1,063 frames with readings
4.380–4.387 V and peak output 7, then restored normal app 1.0.7 startup.
This confirms the original display ran; gauge-only deployment is pending.

Release **1.0.8**, source `1caaee7` / tag `firmware-v1.0.8`, was published and
imported successfully. All 111 firmware tests, web/API checks, 30 browser tests,
12 emulator tests and GitHub checks passed. The updated Effects guide is live.
The connected ESP32 V2 consumer staged 1.0.8, confirmed it after its health
trial, and resumed normal startup at **app 1.0.8 / base 1.0.4**. The capture is
`.artifacts/battery-gauge-consumer-ota.log`. No packets arrived during the
observed startup, and this run did not visually validate the revised gauge.
The producer's latest fleet report remains app 1.0.6 / base 1.0.3; its USB base
upgrade is still needed. Do not infer that the visual report for both displays
establishes both firmware versions.

### Producer deployment and recovery, September 20, 2026

FeatherS2 UID `c7fd1a30c4c2` entered USB maintenance and verified all eight
base files with `make deploy-base`. After unmounting CIRCUITPY, a normal-mode
reset started OTA. The first network attempt returned `OSError` and resumed
app 1.0.6; a second boot downloaded and confirmed **1.0.8 / base 1.0.4**,
sequence **13**, with **399 frames / 267 sends** in the trial report. Firebase
reports no OTA error and `battery: {status: "unsupported", voltage: null}`.
The ESP32 V2 also reports current 1.0.8/base1.0.4/sequence13; its latest
battery snapshot after disconnecting laptop USB was **3.691 V** (uncalibrated).

The producer's post-confirmation reset entered CircuitPython native
`SafeModeReason.HARD_FAULT`, with software reset reason and no previous Python
traceback. The slot journal remained current 1.0.8 and BOOT read released.
After cleanly unmounting the drive, an explicit normal-mode reset with the
one-boot network skip restored microphone processing and ESP-NOW initialization.
This recovers operation but does not establish the native fault's cause or fix
it. No flash erase or slot replacement was performed. Logs are
`.artifacts/battery-gauge-producer-base.log`,
`.artifacts/battery-gauge-producer-ota.log`, and
`.artifacts/battery-gauge-producer-recovery.log`.

The user was asked to select Battery for the two-wing gauge-only visual check;
that confirmation remains separate from firmware/report validation.

The recovered producer then registered all five short presses through
Ember/Aurora/Ripple/Chroma to `EFFECT 5 Battery display=6`, with audio processing
continuing. The user confirmed the consumer shows a steady gauge with no
scrolling and the FeatherS2 shows two amber dashes. The gauge-only two-wing
visual check is complete. Passive host monitoring was stopped, leaving the
normal application running in the selected Battery effect.


### Recurrent sleep illumination investigation

After the successful gauge rollout, the user reported intermittent LEDs turning
bright after long-press sleep. App 1.0.8 already uses the output-hold sequence
introduced in 1.0.6. Read-only source inspection and a passive 12-second USB
listen were performed; the connected FeatherS2 console was idle with a Done
title. No reset, GPIO reconfiguration or new firmware was applied during this
inspection, so the board's existing sleep/stopped state was left undisturbed.
The affected node and USB-versus-battery reproduction remain unconfirmed.

README now documents an input-side 10 kΩ pull-down as a proposed floating-input
test, and default-off wing power switching as the stronger hardware solution.
The wing's DIN pad is level-shifted; both its diode-fed VBAT and VUSB sources
must be considered for power isolation. Neither hardware change is installed.
Do not treat the older two-wing visual pass as resolution of this recurrence.

## September 23: Reverse TFT 1.1.0 development

Implemented shared board profiles, explicit role/source setup, dim TFT dashboard,
D0/D1/D2 controls, DGRP consumer presence, MAX17048 readings and schema2 releases.
Schema1 journal/rollback fixtures remain exact historical contracts. Firmware
checks currently pass139 tests; web3/API5/browser30/emulator12 pass. Emulator
initially lacked worktree dependencies, then exposed historical fixtures using
new dynamic constants; dependency links and explicit legacy fixtures fixed this.

Connected bare board advertises VID239A/PID8123, serial64:e8:33:73:f3:84,
`/dev/cu.usbmodem1101`. No CIRCUITPY drive or CircuitPython REPL response.
Initial double RESET did not expose a UF2 drive. Holding D0 while connecting
USB exposed ROM recovery (303A:1001). esptool confirmed ESP32-S3 revision v0.1,
4 MB XMC flash, 2 MB PSRAM, MAC `64:e8:33:73:f3:84`.

Before erasing, the entire 4,194,304-byte factory flash was backed up and a
second hash-matched copy saved outside the worktree under the main checkout:
`.artifacts/board-backups/reverse-tft-64e83373f384/`. Backup SHA256:
`54e405f011094cef073f8ca2ccf58e5852bfa2be48b7226c7c66b67d3281c1da`.
Official TinyUF2 0.33.0 combined.bin was installed with hash verification.
Official CircuitPython 10.3.1 .bin was then written at offset zero without a
full erase, also hash verified. Both images have matching partition tables;
the CircuitPython write ends below the preserved UF2 partition at 0x2d0000.
RTS reset left ROM USB visible. On September 24, the user’s physical RESET
exposed FTHRS3BOOT with TinyUF2 0.33.0. The direct .bin write had not completed
a bootable CircuitPython installation: the precise boot-selection cause was
not established. `make flash BOARD=adafruit_feather_esp32s3_reverse_tft` then
backed up CURRENT.UF2 and transferred the official 10.3.1 UF2. macOS reported
EIO during the reboot/disconnect; CIRCUITPY subsequently appeared and both
boot_out.txt and the serial REPL confirmed CircuitPython 10.3.1, board ID and
UID `468e33373f48`. Do not treat a copy error alone as installation success.

Configured consumer group1/source `7c:df:a1:03:4c:2c` with verified readback.
The first deployment stopped because macOS cached the newly created recovery
directory as a zero-byte regular file, although device os.stat reported a
directory. Unmounting/remounting temporarily corrected the host view without
erasing/reformatting. A second `make deploy` copied the files but failed host
readback for ota_store.py (host saw 4096 bytes; device saw the expected 6669).
After unmounting the Mac volume, serial readback verified every deployed file
byte-for-byte against source, plus the saved consumer profile. No app rewrite
was needed. The cause of the recurring host/device filesystem disagreement is
not established; keep the Mac volume unmounted during these native checks.

Serial soft restart then passed startup: app/base1.1.0, follower
`64e83373f384`, channel1/group1. Normal LIGHTS frames advanced with no traceback
or TFT warning; received/rejected remained 0/0 during the initial nine-second
check. Thus lost-link startup works, but live radio/presence and TFT physical
appearance remain unconfirmed. All139 host tests passed before deployment.

No credentials provisioned on the new board, no cloud deployment or
stable release publication yet. Old producer/consumer remain untouched.

Outstanding hardware gates:
physical button/sleep checks, battery-backed MAX17048 reading, explicit-source receive and heartbeat,
USB versus battery sleep/wake, later wired mic/wing and TFT-on/off benchmark.
Keep 1.0.8 stable until qualification. The intermittent powered-Wing sleep-light
issue remains deferred; no electrical fix or low-current measurement claimed.

Independent whole-branch review found two important issues: TFT preparation ran
before the audio budget gate, and runtime microphone faults lacked visible
status. Both have regression tests and fixes. Display-disabled now explicitly
blanks/stops native refresh, host S3 button diagnostics use correct aliases and
polarities, and missing enrolled identity cannot enter interactive first-run
setup. Deployment rejects versions other than pinned CircuitPython10.3.1 before
writing. Final software gate: **139 firmware tests pass**. Hardware gates above
remain pending; implementation commits are on `feature/reverse-tft`.


September 24 native observations: user confirmed the CONSUMER/Spectrum TFT is
readable and correctly oriented, with labels on the left. Live RF testing is
deferred at the user's request. The display reports 240x135, rotation0 and
brightness0.12. A REPL-time free-heap snapshot was 1,945,360 bytes; this is not a
running-producer memory or performance benchmark. MAX17048 returned
`out_of_range` on the bare USB-powered board; no battery was fitted/qualified.

Button probing found unpulled inputs at inconsistent idle levels. Enabling
D0 Pull.UP and D1/D2 Pull.DOWN changed all three to the expected released
states (True/False/False), matching the official Adafruit multiple-buttons
example. Corrected runtime controls, first-run setup, host button diagnostics,
release-before-sleep and D2 PinAlarm (`pull=True`). Regression tests reproduced
missing input bias and pass after the fix; full suite now141 tests. Physical
press/sleep/wake tests still remain pending.


The two corrected app files were backed up and updated through the serial
REPL with staged/final byte readback. Native CP10.3.1 rejects remount while the
USB LUN is exposed even after Mac eject. After successful host unmount/eject,
`storage.unsafe_disable_usb_drive()` allowed controlled serial writes, following
CircuitPython's documented prerequisite that the host finish all writes.
`storage.enable_usb_drive()` restored USB ownership; the device reported its
filesystem read-only before app restart. This was a one-off bring-up procedure,
not an automatic fallback in make deploy. Native make deploy's Mac FAT12
readback problem remains a tooling limitation to investigate.


### September 24: three focused TFT pages

Approved Audio → Performance → Status, starting on Audio and cycling via D0.
Implemented spectrum/level/four-row status, page numbers, missing-data markers,
fault/sleep priority, and bounded DEVICE serial details every10s. Updated
README/AGENTS. Host gate:149 tests pass, including native math API compatibility,
page cycle, bounds, strip continuation and pending-page replacement.

`make deploy` verified identity but macOS mounted CIRCUITPY read-only and refused
its first staging write. Used the documented host unmount/eject plus exclusive
serial procedure to back up, stage, read back and replace the changed recovery
files. No flash erase, credential change or source/role change.

The native simulation caught missing `math.log10` in CP10.3.1; switched dBFS to
`20 * log(x) / log(10)` with a host regression. Font reports6x12; fields reserve
up to6x14. Initial multi-TileGrid full refreshes measured45–100ms, which could
permanently starve the existing spare-time guard. Text caching/visibility
changes alone did not fix that. Replaced composition with front/back indexed
bitmaps and cached colored/scaled glyph atlases. Startup clears the screen
before audio/radio, then each running-loop transfer covers at most24 rows.

Isolated native strip transfers measured14.2–22.0ms. With a29ms spare budget and
32ms loop, each of the three pages completed6 full frames over1.5seconds, zero
skips, maximum update23.2ms. This is an isolated display/consumer-budget check,
not a microphone-on or live-radio benchmark. Prototype free heap was1,880,160
bytes including duplicate diagnostic module objects; not production peak usage.
Logs: `.artifacts/bringup/tft-strips-prototype.log` and
`.artifacts/bringup/tft-budget-prototype.log`. The user confirmed physical readability, comfortable spacing and D0 cycling
of all three pages on September 24; live radio remains deferred.

Final installed-renderer simulation passed all42 producer/consumer page, effect,
fault and countdown cases. Maximum native step21.97ms, additional allocated
heap81,040 bytes, free heap1,894,960 bytes in the diagnostic session. These
are rendering measurements with simulated input, not audio/radio qualification.
Log: `.artifacts/bringup/tft-three-pages-native.log`. Fresh `make check` passes
149 tests and `git diff --check`.

After the simulation, passive serial monitoring confirmed the real consumer
app resumed: advancing LIGHTS frames, expected Spectrum/LOST state, no received
packets or rejected packets, and no traceback. The user subsequently confirmed
all three pages look good when cycling with D0.

### September 24: responsive two-page debugging UI

After the earlier visual confirmation, the user reported LIVE with no spectrum
and D0 apparently unresponsive. Passive logs showed real changing spectrum and
accepted radio packets. A 40-second instrumented run logged physical D0 changes
and page transitions, but 801 display skips. At one point row48 stalled for
several seconds with cost24.08ms and spare26.96ms: snapshot preparation was
subtracted before comparing against a cost that already included preparation.
Also, a slow cost estimate could prevent all future draws from remeasuring it.
This establishes timing starvation; the precise initial long stall was not
captured before interruption. D0 worked after restarting during diagnostics.

Count preparation once, transfer at most12 rows, and allow a bounded retry after
half a second with >=12ms spare. D0 resets refresh/retry deadlines and logs the
selected page. No work is forced with zero spare time. Per user request, simplify
to Audio/Status: Status has current effect and four existing diagnostic rows,
updates once per second; Audio keeps its configured cadence. A retry can exceed
its estimate, so this is not a hard real-time guarantee for the microphone.

Three regression tests failed before the fix and passed afterward; make check
passes152 tests. Native make deploy again hit the known Mac FAT12 directory-view
problem before writing. After host unmount/eject, serial backup, staged/final
byte readback of dashboard.py/lights_app.py and normal startup passed. No base,
identity, firmware, or radio protocol change. Live validation log:
`.artifacts/bringup/tft-responsive-live.log`.

The installed-code60-second live test passed:1,674 render steps,128 completed
frames,38 skipped updates, both pages visited by physical D0, received spectrum
peak0.996. An injected80ms cost estimate recovered automatically. Typical sampled
step estimates were11.8–13ms. The reported maximum1.58s step gap includes initial
display setup, so it is not a measured button latency. Both pages were observed
in runtime state; final physical readability confirmation remains separate.
The previous40-second run had801 skips. The app restarted normally afterward,
with live accepted packets and no traceback. Producer/mic timing and sleep/wake
qualification remain pending; this test exercised consumer reception only.

The user confirmed that D0 reliably switches between Audio bars and Status
after the two-page update. This closes the physical page-switch check.

### September24: group controls, sleep takeover and Brightness page

Implemented consumer-to-producer DGRC requests and DGRA acknowledgments for
next effect, group sleep, brightness up/down. Producer retains authority and
repeats v3 effects/DGRS sleep; DGRB adds current/max brightness every0.5s without
changing51-byte audio. One pending request, bounded retry/deadline, sender boot
and sequence dedup, intended MAC/group/session/recent-audio validation, bounded
registry, and preserved OTA sleep inhibition. Legacy listeners follow effect
and sleep; brightness and initiating controls require updated participants.

Full-screen TFT overlays replace the selected page during hold/cancel/fade and
control feedback. A native display-only preview passed hold3s, cancel2s, hold3s,
fade3s and release-to-sleep message:393 steps,max12.33ms,free1,099,200 bytes.
Log `.artifacts/bringup/tft-sleep-preview.log`. It did not sleep devices or send
group commands. No new electrical sleep/wake qualification is claimed.

Independent review found countdown changes restarting unfinished frames. Added
a failing regression, then preserved strip progress across digit changes and
allowed overlay steps with>=12ms spare. New stages still preempt, zero spare
still skips. Reviewer confirmed fix; no remaining important findings.

User then requested Brightness, authorizing50% maximum. D0 cycles Audio/Status/
Brightness; D1/D2 short changes shared brightness by5 percentage points on that
page, D2 long still sleeps. Default15%,zero allowed, TFT brightness unchanged.
Updated cached Spectrum colors and effect indicators. Battery retains3% cap.
Brightness is volatile and resets with producer config after reboot. Added
loss/replay/new-session/cache/control/cap tests and a regression proving busy
ACK traffic cannot starve DGRB or audio. Brightness state alone does not rewind
animation time or keep stale audio alive.

Both USB deployments hit the known host FAT12/read-only view before writing;
used successful host unmount/eject followed by exclusive serial backups and
staged/final readback. The connected S3 has the combined seven-file app update.
Producer and other consumers still need matching app installation for actual
cross-node control/brightness qualification. No release/OTA publication or
saved identity changes were made.

Final combined firmware:168 host tests pass. S3 serial verified all seven changed
app files and restarted normally with live producer audio reception. Native
Brightness preview at0%,15%,50%,15% passed with no display fault; native DGRB
encode/accept returned0.15/current,0.5/maximum. Preview log:
`.artifacts/bringup/tft-brightness-preview.log`. Normal consumer app restored.
User has been asked to connect the microphone FeatherS2 for matching producer
installation; cross-node control/brightness is not yet physically verified.
Do not publish the unqualified1.1.0 release or claim old nodes adopted brightness.

### September24: local producer trial deployment

Connected FeatherS2 confirmed CP10.3.1, saved producer identity, OTA field mode,
active1.0.8 slot1, sequence/floor13, no pending trial. The matching1.1.0 source
will be checkpointed locally and installed via USB into inactive slot0 as a
sequence14 trial, preserving slot1 and credentials, with the existing30-second
health gate and rollback. This is a local hardware preview, not a published
GitHub/Firebase release. Reserve sequence14 for this device trial; a subsequent
fleet release must use sequence15 or higher to exceed its anti-rollback floor.
Keep USB-base backups and old journal for explicit recovery. Do not replace
active slot files or bypass trial health confirmation.

Producer deployment completed from local commit `be5f9f2` (no push/publication).
Base and recovery files were backed up along with both previous OTA slots,
settings and saved identity under ignored `.artifacts/app-backups/feathers2-trial-1790273295356996000`.
The host drive was unmounted/ejected; the device already owned its filesystem
in OTA field mode, so serial writes required no ownership override. All22 base/
recovery files passed staged and final byte readback. OTA base1.1.0 first booted
the preserved1.0.8 active slot successfully. `UpdateStore.stage` then validated
all12 new files into inactive slot0 as sequence14, with old slot1 retained.

Native trial logged `OTA confirmed version=1.1.0` and successful check-in.
The intentional confirmation reset disconnected USB; this caused a host serial
read exception, not a device traceback. Reconnected successfully. Checksummed
journal generation20 reports active1.1.0 slot0, floor14, no trial/error and no
pending report. Continued live microphone/spectrum output after reset confirms
normal field operation. Both GPIO0 and IO43 inputs are retained. Logs include
occasional processing-over-budget warnings (including109ms against64ms); no
new real-time performance guarantee is claimed. Logs:
`.artifacts/bringup/producer-trial-live.log`,
`.artifacts/bringup/producer-confirmed-startup.log`.
A live TFT-originated effect/brightness control test is now awaiting user input.

The90-second passive button-test window completed with continued microphone
output and no GROUP/EFFECT/SLEEP command log entries. No user confirmation
arrived during the window; cross-node button behavior remains unconfirmed.

The user subsequently confirmed TFT D1 changes the shared effect and the
Brightness page D1/D2 changes the percentage with the producer Wing following.
This is physical confirmation; those presses were outside the captured log
window. Group sleep/countdown verification is the next check.

The user reported the sleep action done. The120-second recording did not
capture a GROUP/SLEEP transition. A subsequent six-second passive console check
returned only CircuitPython Done/Wi-Fi off, consistent with sleep; no reset,
interrupt or wake command was sent. This is not a sleep-current measurement.
Explicit confirmation of full-screen countdown and both nodes remaining dark
is still needed to close the visual check.

The user explicitly confirmed the full-screen countdown appeared and both the
Reverse TFT and microphone producer finished completely dark. Group sleep
visual validation is complete for these two nodes; both were left asleep.
Sleep current and post-update wake behavior were not measured in this test.

### September24: brighter TFT, display standby, and sleep animation

The next local app preview raises TFT backlight from12% to50%, blanks it after
30seconds without buttons, and stops dashboard snapshots/composition/transfers
while blank. Audio/radio/Wing work continues. A first press wakes only, consuming
holds until stable release. Incoming group sleep wakes the countdown display.
Sleep adds a cached pixel-art dog with breathing/Z animation. Group command
feedback is now a small top Broadcasting... banner with error text preserved.
No base or wire-format change; these app files can be released over OTA once
devices have compatible base/credentials. The bare S3 is not enrolled yet.

Host `make check` passed181 tests. Review caught and fixed banner expiry before
Status-page composition after a fast ACK; a regression covers that case. Tests
also cover actual button routing through wake holds, display-only failure
isolation, zero dashboard work while blank, and continued sleep strip progress.

The connected S3 retained UID468e33373f48/MAC64:e8:33:73:f3:84. `make deploy`
hit the known Mac FAT directory inconsistency (`File exists: recovery`). After
unmount/eject of verified disk4/CIRCUITPY, the established native serial path
backed up and verified all seven selected recovery modules byte-for-byte,
preserving node identity/base/credentials. Consumer startup passed, with zero
received packets while the microphone producer remained asleep.

An isolated native display preview exercised banner, shortened3-second idle,
wake, hold countdown, and fading countdown. All stages passed with no dashboard
fault; native backlight readings were0.5 ->0 ->0.5. Drawing stopped while idle.
398 bounded update steps had a maximum observed16.11ms, with1,272,704bytes free.
This synthetic consumer preview is not an audio/radio benchmark or current
measurement. Log: `.artifacts/bringup/tft-idle-preview.log`.

An optional subsequent full-frame screenshot export exceeded the serial timeout;
attempts to re-enter/restart the REPL received no response. The native preview
had already completed successfully. No cause of the unresponsive console is
established; a physical RESET was requested to restore the normal app. Do not
claim a clean diagnostic exit or completed visual/real30second-idle confirmation.

After the requested physical RESET, a45-second passive serial capture confirmed
normal1.1.0 consumer operation with continuing LIGHTS/DEVICE output and no
traceback or TFT-disabled message. Source/group identity remained unchanged;
RX stayed zero while the producer was asleep. Normal app restoration is
verified. Log: `.artifacts/bringup/tft-idle-live.log`. The user was asked to check
real30second blanking, first-press wake, second-press page change, and the dog
countdown using a1–2second D2 hold followed by release. Visual confirmation is
pending. This preview has not been committed/pushed or published to the fleet.

The user then confirmed first-press wake, second-press page switching, and the
animated sleeping dog with a readable countdown after the idle screen went dark.
The physical idle/wake/countdown visual check is complete. This does not measure
power consumption or repeat the already-qualified two-node deep-sleep test.

### September24: EchoGlow startup, USB base1.1.1

User approved EchoGlow branding with selected app version/live status and a
soundwave that reflects off a wall and bursts into light. BootScreen now shares
one cached animation bitmap through network startup and dashboard preparation.
The cyan outbound wave reflects pink from a wall, bursts into cyan/pink/gold,
then settles into a glow. Callback cadence is bounded10Hz, with capped catch-up
after blocking operations and no fixed splash delay. App minimum base remains
1.1.0; callbacks are optional on older bases. The screen displays app1.1.0 while
the USB base is1.1.1. Wire formats, settings, credentials, project identifiers,
and the dim cyan Wing OTA indicator are unchanged.

`make check` passed191 tests. Review found an old-app compatibility issue where
stale startup cleanup could erase a replacement fault screen; TextScreen.close
now checks root ownership, with a regression test. A fresh network confirmation
screen receives the actual app version too. Native test logs are under ignored
`.artifacts/bringup/echoglow-deploy.log` and `echoglow-preview.log`.

Connected S3 UID468e33373f48 retained its consumer role/source/group. Standard
make deploy again failed at the host FAT directory view (`File exists: recovery`).
After verified CIRCUITPY/disk4 unmount and eject, the serial fallback backed up
and byte-verified hardware.py, ota_bootstrap.py, ota_manifest.py, and recovery
dashboard.py/lights_app.py. Saved identity/credentials/release slots were not
replaced. Startup confirmed app1.1.0/base1.1.1 and continuing consumer operation.

Native preview completed wave/echo/burst/glow with no fault, maximum observed
animation tick41.99ms and1,041,168bytes free. Instrumented dashboard preparation
took6.64seconds and serviced all four animation stages before relinquishing
boot ownership, preserving a live dashboard at50% backlight. This is startup
work before audio processing, not an audio-frame benchmark. The preview exited
cleanly and the normal app restarted successfully. Physical startup appearance
was requested from the user; no fleet OTA release or push was performed.

The user subsequently confirmed the physical reset sequence shows EchoGlow,
v1.1.0, wave reflection/light burst, then the normal dashboard. Startup visual
validation is complete on this Reverse TFT board.

### September24: startup latency investigation and fix

The user reported the startup delay was too long. A native comparison isolated
dashboard initialization at5.836s without EchoGlow callbacks versus6.418s with
them (21 callbacks,638ms total callback time). The main cost was rebuilding eight
colored/scaled font atlases using Python per-pixel reads/division/generation.
Font source is570x12; atlas sizes/scales1/2/4 total177,840pixels.

A tiny native scaling probe verified bitmaptools.rotozoom at zero source and
destination origins produces exact integer replication for scale2/4. Both
rotozoom and replace_color are present in pinned CP10.3.1. A native under1second
startup regression first failed against the old implementation at6.466s.
The replacement uses native scaling and palette substitution, preserving all
atlas dimensions/indices and bounded runtime strip rendering. Review found no
new correctness issue. This changes only dashboard.py, not the USB base.

After the usual make-deploy host FAT-directory failure, the verified disk4 was
unmounted/ejected and the serial fallback backed up and byte-verified the one
changed recovery file on UID468e33373f48. Startup passed. The native regression
then passed: preparation0.689s, all177,840pixels identical to the old reference,
1,567,744bytes free. See tests/native/tft_startup.py for the test and ignored
`.artifacts/bringup/fast-fonts-before.log`, `fast-fonts-after.log`,
`profile-startup.log`, `scale-probe.log`, and `fast-fonts-deploy.log` for evidence.

Same-board software reboot to first LIGHTS output fell8.852s ->2.903s (~67%
less time). These are two local USB/non-enrolled soft boots, not physical reset
timing or an OTA check; Wi-Fi/TLS/update timing remains separate. Logs are
`.artifacts/bringup/boot-before.log` and `boot-after.log`. The normal consumer
app is restored. Fast boots may hand off before the animation finishes; no
artificial delay is added to complete it. Host make check passed191 tests.
The user was asked to confirm startup feel and dashboard legibility. No push
or fleet release was performed.

### September24: smoother intro with completed explosion

After the optimization, the user reported choppiness and that startup cut off
before the explosion. Their updated preference explicitly requires completing
the intro, superseding the earlier immediate handoff. Native frame profiling
measured3.29ms average drawing plus37.06ms refreshing; removing the refresh FPS
limit made no difference. The previous10Hz limit and sparse startup callbacks
were the cadence constraint, and the0.69s font setup ended the splash early.

Base1.1.2 targets20Hz, caps animation catch-up at75ms, and adds a completion step
before dashboard handoff through2.35seconds of animation (explosion ends at2.2).
It skips closed/replaced displays and already-complete intros, and stops waiting
after3seconds if progress stalls. App callbacks remain optional for older bases;
app minimum base stays1.1.0. Native font construction is retained. The font test
now excludes deliberate intro completion from its under1second timing assertion.

Host make check passed195 tests, including completion stages/cadence/deadline,
no repeat, and failed/replaced display behavior. Review found no substantial
issue. Standard deployment again encountered the known Mac FAT directory
inconsistency; the verified disk4 was unmounted/ejected and the serial fallback
backed up and byte-verified hardware.py, ota_manifest.py, and recovery/dashboard.py
on S3 UID468e33373f48. Normal app1.1.0/base1.1.2 startup passed.

Native completion test rendered43 frames in2.203s:10 wave,10 echo,19 burst,4 glow;
average frame gap51.36ms, maximum54.87ms. The completed screen handed ownership
to a live dashboard at50% backlight without replaying the intro. Software reboot
to first LIGHTS now measures4.871s (original8.852s, optimized but truncated2.903s).
This is a deliberate completion wait before audio/radio startup and still keeps
the faster font preparation; it is not a guaranteed physical reset/OTA duration.
Native test: tests/native/tft_intro.py. Logs under ignored .artifacts/bringup:
echo-frame-timing.log, complete-intro-deploy.log, complete-intro.log, and
boot-complete-intro.log. The normal app is restored. Visual check is pending;
no push or fleet publication was performed.

Final font regression with the completion wait excluded passed in0.542s, with
all177,840pixels matching and1,562,048bytes free. Normal app restart passed
afterward; log `.artifacts/bringup/complete-intro-fonts.log`.

The user accepted the revised startup after a physical RESET: smoother
wave/reflection and a completed light explosion before the dashboard. Visual
validation is complete for this Reverse TFT. No further animation tuning was
requested.

## September 24: second Reverse TFT, later used as producer

New board MAC `64:e8:33:73:d8:3c`, UID `468e33378dc3`, ESP32-S3 rev0.1,
4 MB flash/2 MB PSRAM. It first ran as a consumer with source
`7c:df:a1:03:4c:2c`; it was later reconfigured as the Reverse TFT producer
after the ICS43434 wiring was verified. Its producer role is now the source
that new consumers should use.

Factory firmware exposed USB239A:8123. Double RESET did not expose UF2;
D0-held RESET exposed ROM303A:1001. Before erase, esptool read all4,194,304
bytes and verified the device digest. Two SHA256-matched copies are saved in
the worktree and main checkout under ignored
`.artifacts/board-backups/reverse-tft-64e83373d83c/`:
`factory-1790289180814346000.bin`, SHA256
`54e405f011094cef073f8ca2ccf58e5852bfa2be48b7226c7c66b67d3281c1da`.

Installed official TinyUF2 0.33.0 combined image with write hash verification.
RTS reset left recovery visible; esptool's ESP32-S3 watchdog reset exposed
FTHRS3BOOT without another physical button step. INFO_UF2 confirmed0.33.0.
`make flash BOARD=adafruit_feather_esp32s3_reverse_tft` backed up CURRENT.UF2
and sent CircuitPython10.3.1. macOS reported EIO at reboot; CIRCUITPY then
appeared and boot_out.txt plus serial independently confirmed10.3.1/board/UID.
No direct CircuitPython .bin write was needed on this board.

`make deploy BOARD=adafruit_feather_esp32s3_reverse_tft
PORT=/dev/cu.usbmodem468E33378DC31
NODE_CONFIG=.artifacts/bringup/new-s3-consumer.py` passed195 host tests,
all23 base/recovery/profile file readbacks, and serial startup. App1.1.0,
base1.1.2, consumer channel1/group1; frames advanced without a traceback.
Initial received/rejected counts were0/0: no live producer reception established.
Normal mounted USB deployment worked; no serial filesystem fallback was needed.
The user confirmed EchoGlow startup followed by the consumer dashboard, plus
D0 wake/page switching on this board. D1/D2 and live radio checks remain pending.
No OTA credentials provisioned, cloud enrollment, release publication or push.

## September 24: third Reverse TFT consumer

User confirmed another Reverse TFT consumer, already in ROM recovery. MAC
`64:e8:33:73:cc:04`, UID `468e3337cc40`, ESP32-S3 rev0.1, 4 MB flash and
2 MB PSRAM. A read attempt at460800 failed before any erase; a logged retry
at115200 completed all4,194,304 bytes in42.4s and passed the device digest.
The cause of the first read failure is not established. Full backup and a
second SHA256-matched copy are saved under both checkouts' ignored
`.artifacts/board-backups/reverse-tft-64e83373cc04/`, file
`factory-1790294459694478000.bin`, SHA256
`54e405f011094cef073f8ca2ccf58e5852bfa2be48b7226c7c66b67d3281c1da`.

Official TinyUF2 0.33.0 combined image write passed hash verification;
esptool watchdog reset exposed FTHRS3BOOT directly. The guarded make flash
target backed up CURRENT.UF2 and transferred CircuitPython10.3.1. macOS again
reported EIO during reboot. CIRCUITPY boot_out.txt and the deployment serial
identity check subsequently confirmed the pinned version and correct board.

`make deploy` with explicit S3 board, serial port and the shared consumer profile
passed195 tests, all23 file readbacks and normal startup. App1.1.0/base1.1.2,
channel1/group1/source `7c:df:a1:03:4c:2c`; frames advanced without traceback.
Initial received/rejected counts were0/0. The user confirmed EchoGlow startup,
the consumer dashboard, and D0 wake/page switching. D1/D2 and live radio checks
remain pending. No OTA credentials enrolled or provisioned;
no release publication or push. Full mounted USB deployment worked normally.

## September 24: fourth Reverse TFT consumer

New ROM-mode board MAC `64:e8:33:73:e7:08`, UID `468e33377e80`, ESP32-S3
rev0.1, 4 MB flash/2 MB PSRAM. Full4,194,304-byte factory backup passed the
device digest, with SHA256 matching the previous Reverse TFT factory images:
`54e405f011094cef073f8ca2ccf58e5852bfa2be48b7226c7c66b67d3281c1da`.
Two matching copies are saved in the main checkout and worktree under ignored
`.artifacts/board-backups/reverse-tft-64e83373e708/`, file
`factory-1790294915103342000.bin`. The115200 read took365.3s without errors.

TinyUF2 0.33.0 installation passed write hash verification; watchdog reset
exposed FTHRS3BOOT. The guarded make flash target backed up CURRENT.UF2 and
transferred official CircuitPython10.3.1. macOS reported EIO during reboot;
CIRCUITPY subsequently appeared and boot_out.txt confirmed version/board/UID.

Explicit-board `make deploy` installed the shared consumer profile and passed
195 tests, all23 file readbacks, serial CircuitPython identity and app startup.
App1.1.0/base1.1.2, channel1/group1/source `7c:df:a1:03:4c:2c`. Frames advanced
without traceback; initial received/rejected counts0/0. The user confirmed
EchoGlow startup, the consumer dashboard, and D0 wake/page switching. D1/D2
and live radio checks remain pending. No OTA credentials provisioned
or cloud enrollment, release publication or push.


## September 25: Device page and OTA base-block diagnostics

Approved spec: `docs/superpowers/specs/2026-09-25-device-info-design.md`.
D0 cycles Audio/Status/Brightness/Device. Device shows selected app version,
preloaded base version and complete CPU UID, with current-boot OTA status.
New optional check-in update_status metadata reports the newest otherwise
compatible approved release blocked solely by minimum base, while retaining
compatible fallback and respecting pins/pause/revocation. Artifact authorization
and local pre-download manifest checks remain unchanged.

New base-only ota_status.py stores a bounded validated RAM snapshot; base1.1.3
includes it in the USB bundle. No flash writes or periodic Wi-Fi checks. Missing,
invalid or failed checks show unknown/unavailable; disabled, maintenance, paused
and no-release states are distinct. An unavailable check carries a bounded,
non-sensitive reason such as `Wi-Fi`, `timeout`, or `HTTP 400` for the Device
page and serial log. Report-only does not overwrite the check.
Malformed metadata cannot stop an otherwise valid manifest from being staged.
The app remains compatible with base1.1.0 and uses explicit unavailable guidance
on older bases. Application release1.1.1 publishes the current dashboard and
shared controls; the USB base remains version1.1.3.

Verification: initial new tests failed before implementation, then make check
passed206 tests; full make web-test passed3 web,5 API,30 browser and15 emulator
tests. Independent review found no substantive issues and reran21 targeted tests.

Connected fourth Reverse TFT (MAC64:e8:33:73:e7:08, UID468e33377e80) received
app1.1.0/base1.1.3 via make deploy. All24 base/recovery/profile readbacks and
serial startup passed, preserving its consumer profile. Normal startup reported
channel1/group1/source7c:df:a1:03:4c:2c, received0/rejected0.

Native `tests/native/device_info.py` verified actual identity and12 bounded
render strips. Captured and visually inspected device-framebuffer PNGs for the
unchecked state, a simulated base block, and maximum permitted UID/version
lengths: all fit without clipped text. These simulated releases were not real
server offers. Raw-REPL diagnostic imports begin with a not_checked snapshot;
normal unenrolled startup uses disabled. The host capture uses bounded960-byte
chunks and restores the normal app in finally. Artifacts/logs are ignored under
`.artifacts/bringup/device-info-*`; deployment and web logs are under `.artifacts/`.
The user visually confirmed the Device page on the connected TFT: App 1.1.0,
Base 1.1.3, ID `468e33377e80`, and the OTA-not-enabled message are readable.

At this point the server changes had not yet been deployed to production; no
release, credential provisioning or enrollment was performed during this
September 25 test window. The later September 28 enrollment note below records
the production rollout and the first live Reverse TFT check-in.

## September 25: fleet enrollment

Production Firebase enrollment was confirmed for all six known IDs:
`c7fd1a30c4c2` (FeatherS2 producer), `4133c5792f0a` (ESP32 V2 consumer),
Reverse TFT consumer `468e33373f48`, Reverse TFT producer `468e33378dc3`, and
Reverse TFT consumers `468e3337cc40` and `468e33377e80`. The four new Reverse TFT enrollments generated ignored
owner-only local credential files; the two legacy devices retain their existing
credential files in the main checkout's ignored OTA artifact directory.

The connected `468e33377e80` board was provisioned over USB with its own
credential and `OTA_ENABLED=1`; settings readback passed. Its normal reboot
still needs a physical/clean reset confirmation after provisioning. The other
five have enrollment records, but were not physically connected, so their USB
credential writes remain outstanding. The two legacy credential files are in
the main checkout; the three other Reverse TFT credential files are in this
worktree's ignored OTA directory.

## September 28: Reverse TFT consumer OTA provisioning

The USB-connected consumer `468e3337cc40` already had a Firebase device record
and an owner-only local credential file, but it had never received that
credential in `settings.toml`. It therefore had no `OTA_DEVICE_TOKEN`,
`OTA_DEVICE_ID`, or `OTA_ENABLED` setting and correctly displayed OTA as
unenrolled. `make ota-provision DEVICE_ID=468e3337cc40 PORT=... OTA_ENABLE=1`
verified the board UID, role and maintenance mount, wrote all seven OTA
settings, and passed readback without printing the token.

The deployed API initially returned `400 invalid_report` because the production
function was behind the local Reverse TFT report contract. Function tests passed
and `deviceApi`, `fleetOverview`, and `fleetChange` were redeployed. After a
clean field-mode reset, the board reported app `1.1.0`, base `1.1.3`, role
`consumer`, and battery status `out_of_range`; Firebase recorded the check-in.
