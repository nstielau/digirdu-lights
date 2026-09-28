# Device Information Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement inline.

**Goal:** Fourth TFT page with actual app/base/UID and truthful boot-time base-block status.
**Architecture:** Server returns optional `update_status` metadata; a pure base-owned
`ota_status.py` validates and holds it in RAM. The app reads this optional interface
and renders bounded text through the existing dashboard strip renderer.
**Tech Stack:** CircuitPython10.3.1, Python unittest, Node22, Firestore emulator.
**Spec:** ../specs/2026-09-25-device-info-design.md

## Task 1: Server metadata
- [x] Add failing emulator cases for blocked release plus compatible fallback,
  pins, pause, revoked/current/other incompatibilities and no release.
- [x] Use this response shape alongside unchanged manifest/reason:
  `update_status: {schema:1, state:'checked', blocked:{version:'2.0.0', minimum_base:'2.0.0'}}`.
  `blocked:null` means no base-only block; state may also be paused/no_release.
- [x] Modify firebase/functions/service.cjs selection to retain the first/newest
  approved otherwise-compatible base-only block, even when selecting fallback.
  Filter relative to running version; never use metadata for artifact authorization.
- [x] Run make web-test-emulator; confirm original and new tests pass.

## Task 2: Base snapshot
- [x] Add tests/test_ota_status.py and bootstrap integration tests first. Run
  `.venv/bin/python -m unittest discover -s tests -p 'test_ota_status.py'` and
  observe missing feature failure.
- [x] Add ota_status.py with `reset(state)`, `accept(result, running_version)`,
  and `snapshot()`; accept validated versions and strict bounded metadata only.
  States: not_checked, disabled, maintenance, unavailable, checking, checked,
  paused, no_release. Invalid metadata maps to unavailable without blocking a
  compatible manifest. Confirm blocked.minimum_base exceeds BASE_VERSION.
- [x] Preload status in ota_bootstrap.py, reset at _main entry, set initial mode,
  set checking before network, accept check-in metadata, unavailable on failures.
  Report-only must not overwrite check status. Keep all manifest checks intact.
- [x] Add ota_status.py to tools/bundle.py BASE_FILES and Makefile compilation;
  bump BASE_VERSION to1.1.3; APP_MINIMUM_BASE stays1.1.0.
- [x] Run bootstrap/status tests; test incompatible manifests never stage/download.

## Task 3: Device page
- [x] Add failing tests for four-page cycle and full identity/long-version layout.
- [x] In dashboard.py add cached identity reader using app_version, ota_manifest,
  microcontroller.cpu.uid; optional ota_status import with older-base fallback.
- [x] Add device info to snapshots only on page3 in lights_app.py. Append page3,
  keep Brightness index2, use seven compact full-width text rows (x44,31 cells)
  under existing header/left labels. Wrap supported long IDs/versions; ensure
  all text fits the 240x135 display without scrolling or truncation.
- [x] Preserve sleep/banner priority and idle/budget gates. Test missing server,
  older base, disabled/maintenance and blocked states for both roles.
- [x] Run make check and render/native tests as available.

## Task 4: Verify and document
- [x] Review new changes independently; fix substantial findings with regression tests.
- [x] Document minimum-base compatibility, current-boot freshness, USB1.1.3
  requirement, server rollout, current device installation status, and controls.
- [x] Run make check, server unit/emulator tests and inspect layout artifact.
- [x] Check connected hardware identity; deploy if accessible using make deploy,
  verify readback/startup and request user visual confirmation separately.

## Execution ledger
- Existing feature/reverse-tft worktree is isolated; preserve all earlier uncommitted changes.
- Ruling: execute inline without another workflow-choice question; user approved implementation.
- Ruling: new small base module isolates status validation from hardware/rendering.
- Pre-flight: Task1 metadata is consumed by Task2; Task3 consumes Task2's optional snapshot.
- No cloud publish or fleet release during implementation; report deployment limits explicitly.

- Task1 complete: new emulator cases failed before implementation; all15 pass afterward.
- Task2 complete: five initial status tests failed before implementation; validation,
  failure reset, report-only preservation and manifest rejection now pass.
- Task3 complete: five initial page tests failed; page-cycle expectations updated;
  all206 firmware tests pass. Base1.1.3 deployed with24 file readbacks.
- Task4 complete: independent review found no substantive issues. Web3/API5/browser30/
  emulator15 pass. Native real renderer used12 bounded strips for each of current,
  simulated blocked and maximum-length screens; PNGs inspected and app restored.
- Hardware: UID468e33377e80, app1.1.0/base1.1.3; initial radio received0.
- Ruling: app version remains development1.1.0 until the separate1.1.1 publication.
- Server support is implemented and emulator-tested, not deployed to production.
  No fleet release/enrollment was performed. User visual check is pending.
