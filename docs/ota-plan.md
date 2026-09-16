# OTA upgrades — proposal for review

Status: **plan only; not implemented or provisioned**. September 15, 2026.
The separate Spectrum effect change does not enable Wi-Fi or OTA.

## Recommendation and scope

Use a small Firebase HTTPS REST API, a Firebase administration app, and GitHub
Releases as the source of application versions. Each device gets its own token
in `settings.toml`. At boot it tries the open **`openwireless.org`** network,
reports its actual installed versions, asks for the newest compatible stable
release, and installs it if needed. If the network or service is unavailable,
it runs its last working application. No captive portal or MQTT broker is
needed for this workflow.

Keep performance lighting on the existing offline ESP-NOW network. All nodes
update independently over Wi-Fi; the producer does not relay firmware or device
credentials over ESP-NOW. A node within radio range of the producer but outside
Wi-Fi coverage can keep showing lights, but cannot obtain cloud updates there.

Initial supported boards remain the microphone FeatherS2 and consumer Feather
ESP32 V2. Preserve mic GPIO 5/6/9, wing GPIO 38/32, BOOT effect selection, local
node role, orientation, calibration tuning, and brightness 0.15.

## What to reuse from gate_controller

Use its **implemented** [OTA operations](../../gate_controller/docs/ota-operations.md)
and [bench results](../../gate_controller/docs/ota-bench-validation.md), rather
than copying the older rename-based proposal:

- A USB-installed bootstrap and independent application/base version reports.
- Two application slots, a retained confirmed version, two checksummed journals,
  bounded downloads, SHA-256 verification, trial boots, watchdog and rollback.
- GitHub artifacts mirrored to immutable private Storage objects; devices use
  one authenticated HTTPS endpoint, with explicit trusted roots and hostname
  checks. Gate's bench tests needed explicit Google roots on CircuitPython.
- Per-device random tokens, server-side token hashes, disable/revoke support.
- Firebase Hosting, Google sign-in, server-checked admins, App Check for browser
  requests, deny-all direct Firestore client access, and audit records.

Adapt rather than directly copy its XIAO pins, MQTT health conditions, single
application file, credentials, Firebase project, or gate-specific output logic.
Create a **separate Digirdu Firebase project**; do not modify Drawbridge or share
its runtime credentials. Project ID/region will be selected before provisioning.
Its power-loss and recovery qualification is incomplete; repeat those tests on
both of our boards.

## Network phases: protect ESP-NOW during playing

ESP-NOW and an associated Wi-Fi station must use the access point's channel.
Our current lighting channel is 1; `openwireless.org` could be on another
channel. Arbitrary Wi-Fi scans/reconnects during playback would interrupt
reception. This follows [Espressif's coexistence guidance](https://docs.espressif.com/projects/esp-faq/en/latest/application-solution/esp-now.html#can-wi-fi-be-used-with-esp-now-at-the-same-time).

Proposed first version:

1. **Boot maintenance:** keep LEDs dim with a distinct update status indicator.
   Try only the configured SSID, with no password or setup access point.
   Use a short bounded scan/association attempt (target 8 seconds), 0–2 seconds
   of per-device jitter, and no endless reconnect loop.
2. **Check in:** send running app/base versions and the last saved update result;
   receive desired version, deployment sequence, pause state and manifest.
   Treat captive-portal redirects, TLS failures, malformed content and timeouts
   as unavailable internet. Never disable TLS validation on this open network.
3. **Update if required:** download to the inactive slot with limits, verify,
   journal a pending trial and reboot. Suggested initial bounds: 8 KiB manifest,
   256 KiB total application, 1 KiB chunks, 5-second socket timeout, 90-second
   overall maintenance deadline. Measure DNS/TLS blocking on both boards before
   promising that deadline; use watchdog recovery for a stuck startup. A failed
   maintenance watchdog boot skips networking once to reach the saved app.
4. **Enter lighting:** close sockets, disconnect Wi-Fi, stop scanning, release
   TLS buffers, explicitly restore the configured ESP-NOW channel and start
   audio/rendering. Restore the channel on every success and error exit.
5. **Trial confirmation:** run a new candidate for 30 seconds on ESP-NOW.
   Require imports, finite/bounded feature values, continuing render frames,
   no unhandled errors and role-appropriate subsystem initialization. Producer
   also requires working capture and completed calibration; consumer must keep
   rendering but need not hear a producer. Missing internet or a silent/absent
   producer is not evidence that consumer code is broken. Distinguish RF reception
   and measured audio activity from software health in the report.
6. After a successful trial, commit locally and make **one bounded post-update
   report attempt**: fade, pause lighting briefly, join Wi-Fi, report the actual
   confirmed version, then restore ESP-NOW. On failure persist the latest result
   for the next boot. This short extra interruption occurs only after an update;
   do not periodically reconnect during a show. Treat it as part of startup.

A normal boot reports before lighting starts. Internet-free boots cannot report;
show a timestamped last report, never infer that the device is online. A later
explicit maintenance command/button gesture could check without a power cycle.
Periodic online heartbeats or seamless concurrent Wi-Fi require a separately
reviewed channel-coordination design or a dedicated Wi-Fi/ESP-NOW gateway.

## Application layout and recovery

The app has multiple coupled Python modules, so overwriting root files one by
one is unsafe. Use **two complete module directories**, selected as a unit:

```text
/boot.py                 USB-managed filesystem ownership
/code.py                 USB-managed loader, watchdog, boot maintenance
/lib/ota_*.py            USB-managed updater, HTTP and journal support
/certs/...               USB-managed public TLS roots
/recovery/...            USB-installed complete known-working application
/ota/slot0/...           complete application bundle
/ota/slot1/...           complete application bundle
/ota/state0.json         alternating checksummed selection journals
/ota/state1.json
/node_config.py          per-node role/pins/tuning overrides, preserved
/settings.toml          per-device endpoint/credential, preserved
```

Release the audio, effects, renderer, config defaults, radio protocol/transport,
and main application together. Bootstrap pins a small application API for
startup, progress/health reporting and shutdown; per-node overrides are loaded
separately and validated by the selected app. Never silently reset a producer
to consumer or lose an orientation override during update.

On a fresh VM boot, import only the chosen slot's app modules plus explicit
base libraries. Do not fall back to modules from an older slot or root directory
when an import is missing. Prototype this module isolation on CircuitPython
before implementing cloud delivery. Do not hot-reload an arbitrary set of modules.

Download manifest-listed files individually through the authenticated endpoint;
no on-board ZIP extractor. Accept only fixed relative file names, reject traversal,
unexpected/duplicate files and unsupported sizes; verify every length/digest and
bundle digest before selecting a slot. The active slot and root recovery bundle
are never download destinations. Clean only the inactive slot after validating
space requirements; reject if there is insufficient space plus a reserve.

Write and sync a complete checksummed journal to the older journal generation.
Record a trial as started before importing it. A boot that finds an already-started,
unconfirmed trial rolls back; a loop hang triggers the hardware watchdog.
Confirm only after progress-based health checks, not merely a successful import.
A bad app must not repeatedly download on each boot: remember the rejected digest
and deployment sequence until a newer deployment or explicit retry is assigned.
Recovery is offline-capable and independent of Firebase. These application slots
are on one FAT filesystem, not isolated ESP flash partitions; whole-filesystem
corruption can still require USB repair.

### Filesystem ownership and initial USB install

Every board needs one USB bootstrap/enrollment deployment. CircuitPython must
own writes in OTA field mode; the USB host owns writes in maintenance mode.
Never enable concurrent host/device write protection bypasses. The ownership
choice belongs in `boot.py`, per [CircuitPython storage documentation](https://docs.circuitpython.org/en/stable/shared-bindings/storage/index.html).

FeatherS2 needs a **tested physical recovery route** that exposes writable
CIRCUITPY even when the selected app fails. Choose and verify a spare non-strapping
GPIO/jumper during the first hardware stage. Do not copy the XIAO's GPIO8/D9
assignment. BOOT/GPIO0 held during reset invokes ROM download mode, so it cannot
simply replace Gate's maintenance jumper. A delayed BOOT press after reset is an
alternative only if reliable in bench tests. Preserve the ordinary short BOOT
press for selecting lighting effects. Firmware recovery through ROM remains a
last resort, not the normal maintenance flow.

ESP32 V2 has serial USB rather than a CIRCUITPY drive. Test bootstrap bypass and
serial REPL repair there too. Extend `make deploy` to recognize maintenance
ownership, preserve settings/journals, explicitly select a repaired recovery app
when requested, and retain backups/readback/startup verification. Never erase
flash as a routine OTA recovery step.

OTA v1 updates application code only. CircuitPython, bootloader, loader, HTTP
client, certificates and base libraries remain separately versioned USB updates.
No cloud operation changes device credentials or saved node configuration.

## Releases and what “newest” means

Use tags such as `firmware-v1.2.0`, produced from clean commits with passing tests.
GitHub Release assets include a manifest, the application files/bundle for host
use, and a separately identified USB base/recovery bundle. Exclude credentials,
recordings, node profiles, journals, backups and build environments.

Manifest fields: schema, semantic app version, full Git commit, application API,
minimum supported base version, CircuitPython compatibility, supported board IDs
and roles, ESP-NOW send/receive protocol versions, file names/sizes/SHA-256 and
aggregate digest. The server adds a monotonic **deployment sequence**; an intentional
rollback to older code gets a newer sequence. Verify compatibility on the server
and again on the device.

“Newest” means the **highest compatible semantic version from published,
non-draft, non-prerelease, non-revoked releases successfully imported and verified
by our release workflow**. Do not sort version strings lexicographically or rely
on GitHub's latest endpoint alone: its selection also involves release metadata
([GitHub release API](https://docs.github.com/en/rest/releases/releases#get-the-latest-release)).
Publishing a stable release triggers import/verification and advances the stable
channel automatically; no per-device assignment is required. If import fails,
the old stable target remains and the dashboard flags the failed release.
Allow optional device pinning, pause, canary channels and audited rollback.
A base-incompatible node keeps its working app and reports “USB base update
required.” An offline device remains on its last version until a later boot
with internet; newest is a policy, not a guarantee of simultaneous installation.

CI authenticates to the dedicated cloud project with short-lived workload
identity credentials. Mirror release bytes to create-only Storage objects keyed
by version/digest, verify exact GitHub bytes, then transactionally publish the
release record/channel target. Existing release artifacts cannot be overwritten;
changed code requires a new release. Failed publication leaves no partial target.

### Mixed-version lighting installations

Independent boots cannot provide an atomic fleet upgrade. Preserve a compatible
ESP-NOW wire format for routine OTA releases. Manifest compatibility includes
send/receive versions and feature support; the dashboard shows mismatches.
For a future breaking protocol, first ship consumers able to receive both formats,
then migrate producers, then retire the old format in a later release. Devices
can be pinned while staging that migration. Add a canary producer/consumer pair
and packet fixtures to release checks. Never assume “all follow latest” makes
partial RF upgrades safe. The current v2-to-v3 Spectrum migration is a USB
rollout and precedes this OTA system.

## Firebase app and device API

A separate Firebase app provides:

- Fleet list: device ID/name, board, producer/consumer role, current **reported**
  app/base/interpreter versions, desired version, last check-in timestamp,
  update phase/result/error, protocol compatibility and last reported RF counters.
- Release list: version/commit, supported hardware/API/protocol, hashes and channel.
- Admin actions: follow latest, pin release, pause/resume, assign rollback,
  disable/revoke a device; audit every change. Names and placement labels may be
  edited without altering physical role or wiring automatically.
- Clear “awaiting report”, “trial”, “confirmed”, “rolled back”, and “stale report”
  states. Assignment is not installation, and a successful send is not LED or
  microphone verification.

Use Google Authentication and server-enforced admin access. App Check protects
browser calls; device REST calls use device credentials instead. Browser clients
never receive device tokens or Storage credentials; Firestore denies direct
client reads/writes, with authorized Functions returning bounded views.

Proposed server-owned collections:

| Collection | Purpose |
| --- | --- |
| `devices/{id}` | identity, token hash, enabled state, channel/pin, latest reported state |
| `releases/{version}` | immutable validated manifest and private object references |
| `channels/{name}` | target release and deployment sequence |
| `deployments/{id}` | explicit pins/rollbacks and monotonic sequence |
| `admins/{id}`, `audit/{id}` | access and administrative audit trail |

Proposed HTTPS endpoints (bounded ordinary JSON, not the callable SDK protocol):

- `POST /device-api/v1/check-in`: authenticate, record running versions and boot
  outcome, return selected compatible manifest or no update.
- `GET /device-api/v1/artifacts/{digest}/{file}`: stream only a manifest-approved
  object permitted for the authenticated device; no arbitrary URL proxy.
- `POST /device-api/v1/report`: record trial/confirmed/rollback/download failure.

Use `Authorization: Bearer ...` and device ID headers, no tokens in URLs.
Rate-limit and bound bodies; use a boot session ID and sequence to deduplicate
reports and prevent retries overwriting newer reports. Server timestamps express
when a report arrived, not an assumed device clock. Do not cache authenticated
API traffic or firmware responses in the web service worker. Use zero minimum
function instances; bound concurrency and retention rather than writing each
audio frame to Firestore.

## Device credentials and transport choice

Example of the future device file (placeholder values only):

```toml
OTA_ENABLED = "1"
OTA_WIFI_SSID = "openwireless.org"
OTA_API_BASE = "https://<digirdu-project>.firebaseapp.com/device-api/v1"
OTA_DEVICE_ID = "<stable-full-hardware-id>"
OTA_DEVICE_TOKEN = "<random-per-device-token>"
OTA_CHANNEL = "stable"
```

No Wi-Fi password is needed. Keep the source template public and each populated
file ignored, owner-readable on the host, and preserved by deployment. Provision
an unpredictable 256-bit token per board over USB, binding its ID to the full
hardware identity; store only its hash server-side. Token scopes allow that
device to read approved artifacts and report its own state, not administer the
fleet or publish releases. Support explicit revoke/rotation without exposing
secrets in logs. Physical USB access can read these credentials; this is the same
practical limitation as Gate, not tamper-resistant credential storage.

**REST is recommended** because check-in/download/report are short boot-time
transactions. MQTT would add a broker, TLS session/reconnect work, credentials
and topic policy while leaving HTTP downloads necessary. Consider MQTT only if
we later want sustained remote controls or online telemetry and have solved
Wi-Fi/ESP-NOW channel coexistence. ESP-NOW remains the live lighting transport.

The open SSID does not authenticate the access point; TLS authenticates the
update service. Require certificate-chain and hostname verification, tested
trusted roots and a validated clock strategy where required by the TLS stack.
Test cold boots with an unset RTC; an unauthenticated time hint must never allow
unverified code. Verify SHA-256 against the HTTPS-authenticated manifest. This
trusts Firebase/release publishers; independent signed manifests are a possible
later addition, not a security feature provided by hashes alone.

## Implementation stages and acceptance criteria

1. **Bootstrap prototype, USB only:** module slots, ownership/recovery, per-board
   pin audit, watchdog, size/heap measurements and version reporting. Confirm
   mic pins, ESP-NOW, all effects and numbered HUD behave unchanged.
2. **Offline update engine:** simulated interrupted writes at every journal step,
   incomplete bundles, bad hashes/syntax/imports, unknown manifest keys/paths,
   full storage, stale sequence, incompatible board/base/protocol, failed trial,
   hangs and unavailable producers. Verify old app remains bootable.
3. **Cloud in emulators:** isolated Firebase project/config; authenticated REST,
   browser admin app, token scopes/revocation, immutable import, default latest,
   pins/pause/rollback, status ordering, audit and deny-all direct database rules.
4. **End-to-end bench:** enroll the two boards; publish a canary GitHub release;
   observe download, native trial, confirmed version report and matching LED
   effects. Repeat with AP on a different channel and no AP/internet. Test actual
   power removal during writes/trial, not just soft reset. Verify physical recovery
   and TLS trust failures on both FeatherS2 and ESP32 V2.
5. **Release tooling and rollout:** proposed `make firmware-build`,
   `firmware-release`, `firmware-import`, `ota-enroll`, `ota-provision`,
   `ota-status`, `web-test`, `web-deploy`. Bootstrap once by USB, then default
   enrolled devices to the newest stable application. Keep a canary pair before
   a fleet-wide release; preserve documented USB repair.

Each stage records actual hardware results separately from simulation. Measure
boot/update latency, free heap/flash and post-update FFT/render timings; the
producer already has some 64 ms processing-budget overruns. No TLS/download
processing belongs in its audio loop for this first version.

## Review decisions

Recommended approval covers REST, a separate Firebase project, application-only
two-slot updates, per-device TOML credentials, follow-latest stable by default,
and boot/post-update check-ins with no online interruptions during normal playing.
The visible tradeoffs are startup delay, a brief post-update reporting pause,
stale fleet status between boots, and one initial USB visit per device.

Cloud project ID/region and the physical maintenance input will be finalized
before provisioning and field activation, respectively. No cloud resources,
credentials, release workflow or OTA firmware are created by this proposal.
