# Reverse TFT Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Run shared producer/consumer firmware on Reverse TFT Feathers with explicit setup, live telemetry, presence and local wake.

**Architecture:** USB-base profiles/state are shared with isolated app slots. Pure models drive optional TFT rendering and separately versioned presence. Schema-selected contracts preserve installed legacy rollback slots.

**Tech Stack:** CircuitPython 10.3.1 built-ins, Python unittest, Firebase Node tests.

**Spec:** `docs/superpowers/specs/2026-09-23-reverse-tft-design.md`

## Global constraints

Preserve old board wiring, protocol v3/sleep packets, brightness, filesystem ownership, credentials and OTA trial/rollback. No automatic producer election. Bare connected S3 has no mic or wing yet: physical audio/LED tests require later wiring. Inline execution with fresh final reviewer.

## Interfaces

`hardware.profile(board_id)` returns pure pin/capability dict, shared by host/base/app. `node_state.resolve(board_id, overrides, path)` merges defaults, saved JSON, explicit overrides; `save` validates and atomically writes only when device owns FS. `dashboard` owns pure snapshot/rates and lazy CP backend; `device_setup` owns bounded mic assessment and explicit setup. `radio_protocol` owns presence codec/registry; `wireless` retains one pending send and bounded drain. `lights_app` composes them. Schema 1 = historical ten files/two boards; schema 2 = twelve files/three boards/base1.1.0.

### Task 1: Profiles, battery and saved identity

Files: create `hardware.py`, `node_state.py`, `tests/test_hardware.py`, `tests/test_node_state.py`; modify `battery.py`, `config.py`, `tests/test_battery.py`.

- [x] Write failing tests for three profiles, reserved pin conflicts, MAX17048 version/voltage/SOC/lock timeout, strict state validation/corruption/precedence/host ownership/enrollment locking.
  ```python
  assert profile('adafruit_feather_esp32s3_reverse_tft')['wing'] == 'D6'
  assert resolve('adafruit_feather_esp32s3_reverse_tft', {'radio_role':'producer'}, missing_path)['radio_role'] == 'producer'
  ```
- [x] Run new test modules using `.venv/bin/python -m unittest discover -s tests -p 'test_hardware.py'` and matching state/battery patterns. Expected: new behaviors fail.
- [x] Implement pure profiles, bounded JSON persistence, explicit profile precedence, lazy sensor reads. Unknown/absent gauge reports unavailable; report retains voltage/status only, local TFT uses actual SOC.
- [x] Run `make check`. Expected: all suites pass. Commit `Add shared board profiles and explicit saved identity`.

### Task 2: Compatible OTA and deployment

Files: `ota_manifest.py`, `tools/bundle.py`, `app_version.py`, `ota_bootstrap.py`, `boot.py`, `tools/board.py`, `tools/ota_provision.py`, `Makefile`, `firebase/functions/contract.cjs`, `tools/firmware_admin.cjs`, OTA/deploy/cloud tests.

- [x] Write failures for both exact schema contracts, mixed/unknown files, schema2 minbase1.1.0, legacy rollback, S3 native USB identity/preservation, verified host config/source selection.
  ```python
  expected_files = LEGACY_APP_FILES if manifest['schema'] == 1 else APP_FILES
  assert set(f['name'] for f in manifest['files']) == set(expected_files)
  ```
- [x] Run `make check` and cloud contract tests. Expected: newly introduced cases fail.
- [x] Implement schema dispatch/base preloads/1.1.0 versions/native USB routing and `make configure-node ROLE=consumer LEADER_MAC=...`. Leave new S3 unconfigured without explicit profile. Base boot screen uses base helper only; preserve firmware backup and loader checks.
- [x] Run `make check` and cloud tests. Expected: both schemas/rollback pass. Commit `Support Reverse TFT deployment and compatible OTA schema 2`.

### Task 3: Bounded ESP-NOW consumer presence

Files: `radio_protocol.py`, `wireless.py`, `config.py`, radio/wireless tests.

- [x] Write failures for presence codec length/type/MAC/group/sessions/duplicates/wrap/expiry/capacity, recent valid source requirement, jitter, sleep suspension, native completion gate and eight-packet drain.
  ```python
  assert SIZE == 51
  assert SLEEP_SIZE == 17
  ```
- [x] Run radio/wireless unittest modules. Expected: new presence tests fail.
- [x] Implement separate magic/version, intended producer MAC, producer session, consumer session/sequence, last accepted audio sequence. Bounded32 registry expires10s; broadcasts3s±.5 initial jitter; keep one pending TX and legacy packets unchanged.
- [x] Run `make check`. Expected: existing protocol and presence tests pass. Commit `Track recently seen consumers over ESP-NOW`.

### Task 4: TFT and explicit microphone setup

Files: create `dashboard.py`, `device_setup.py`, `tests/test_dashboard.py`, `tests/test_device_setup.py`; modify `lights_app.py`, `config.py`, `ota_bootstrap.py`.

- [x] Write failures for producer dBFS versus consumer percent, all health states, counter wrap/reset, left labels, legacy no-display path, 5Hz refresh/failure isolation, flat/clipped/variable/deadline mic checks, confirmation and host-owned setup.
  ```python
  assert snapshot['level_units'] == ('dBFS' if role == 'leader' else '%')
  ```
- [x] Run new unittest modules. Expected: new UI/setup cases fail.
- [x] Implement pure snapshots, reused built-in font/tilegrid backend, dim manual refresh, budget skipping. Resolve setup before Config/OTA identity; never stall trial; user confirms role, saved once. Add live producer/consumer statistics and timing.
- [x] Run `make check`. Expected: all suites pass. Commit `Add TFT telemetry and guided microphone setup`.

### Task 5: Controls, sleep and local wake

Files: `lights_app.py`, `effects.py`, `hardware.py`, `tests/test_sleep.py`, new `tests/test_controls.py`.

- [x] Write failures for D0 active-low page, D1 active-high release-only next/no sleep, consumer FOLLOW, D2 hold3s sleep, trial suppression, stable release before alarm and waking-press suppression. Check display/power teardown and old controls.
- [x] Run control/sleep tests. Expected: new behavior fails.
- [x] Implement profile controls/countdown/release text, blank/release display, held power rails/wingLOW and D2 HIGH PinAlarm. No timer; reset remains wake. Preserve deferred Wing sleep issue.
- [x] Run `make check`. Expected: new/legacy controls pass. Commit `Add TFT controls and release-before-wake sleep`.

### Task 6: Integration, hardware and documentation

Files: README, AGENTS, operations notes and integration fixes.

- [x] Run `make check`, `make web-test`, `make web-test-emulator`, immutable bundle validation. Expected: all pass.
- [ ] Inspect USB identity/firmware/loader; backup before firmware install. Bring up bare-board consumer with explicit source. Verify readback, TFT orientation, sensor/buttons/radio/lost link; record hardware unavailable tests.
- [ ] When mic/wing available compare display off/on timing: FPS, mean/max work, 64ms misses, capture discontinuities. Never infer measurements from host tests.
- [x] Document wiring, commands, state/setup/enrollment, TFT fields, presence semantics, controls, compatible OTA rollout and deferred issues. Run `make check`. Expected: green; docs reflect actual observations. Commit `Document Reverse TFT setup and verification`.

## Review focus

Boot import isolation; legacy journals/rollback; FS ownership and role credentials; absent mic/DMA stalls; I2C release; native display/pin-reset sleep behavior; stale/saturated presence; counter wrap; capture budget; old-board memory. Mocks cannot prove electrical behavior, native API semantics or acoustic response.
