# Local USB Maintenance Shortcut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enter USB maintenance on one Reverse TFT node by holding all three buttons, with orange progress cues and automatic exit on the next full reset.

**Architecture:** `TFTControls` recognizes a debounced chord before individual gestures. The app raises a local control exception after hardware cleanup. A base-owned helper stores a one-use NVM marker, and `boot.py` consumes it to choose USB ownership; boot display and matrix code show the orange maintenance state.

**Tech Stack:** CircuitPython 10.3.1, Python host `unittest`, existing `make check` and native USB deployment.

---

### Task 1: One-use boot request

**Files:** `hardware.py`, `boot.py`, `tests/test_hardware.py`, `tests/test_boot_screen.py`

- [ ] Add failing host tests for marker isolation from OTA bytes 0–4, one-time consumption, short NVM failure, and boot selection.
- [ ] Run the focused tests and confirm failures are caused by missing request/consume behavior.
- [ ] Add the base helper and boot selection, preserving physical D0 entry.
- [ ] Rerun focused tests and confirm they pass.

### Task 2: Chord and countdown

**Files:** `effects.py`, `lights_app.py`, `dashboard.py`, `tests/test_sleep.py`, `tests/test_tft_activity.py`

- [ ] Add failing tests for all-three hold, release cancellation, suppression of individual actions and radio commands, trial blocking, and local reset after cleanup.
- [ ] Run focused tests to see the expected failures.
- [ ] Implement the chord state and reuse the sleep overlay layout for the orange USB countdown.
- [ ] Rerun focused tests and confirm they pass.

### Task 3: Orange startup cues

**Files:** `boot.py`, `hardware.py`, `ota_bootstrap.py`, `tests/test_boot_screen.py`, `tests/test_ota_bootstrap.py`

- [ ] Add failing tests for orange moving matrix pixel, 2 px TFT border, and pin cleanup before app handoff.
- [ ] Run focused tests to see the expected failures.
- [ ] Implement the startup cues while leaving normal blue and cyan indications intact.
- [ ] Rerun focused tests and confirm they pass.

### Task 4: Versioning, documentation, and verification

**Files:** `ota_manifest.py`, `app_version.py`, `README.md`, `docs/ota-operations.md`, `AGENTS.md`

- [ ] Bump base to 1.1.5 and app to 1.1.4, retaining app minimum base 1.1.0 with the old-base fallback.
- [ ] Document entry, exit, read-only ownership, version requirements, and physical test limits.
- [ ] Run `make check` and inspect `git diff --check` and the deployment file list.
- [ ] Commit and push the reviewed branch; open a PR against `feature/reverse-tft`.
