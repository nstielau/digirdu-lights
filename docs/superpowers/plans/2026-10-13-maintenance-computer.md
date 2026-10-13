# USB Maintenance Computer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the approved raised pixel computer to the USB maintenance countdown.

**Architecture:** `dashboard.TFTBackend` draws the art directly into its existing back bitmap before overlay text. The title, digit, detail, border, and sleep dog keep their current paths.

**Tech Stack:** CircuitPython `bitmaptools.fill_region`, Python `unittest`, Makefile verification and USB deployment.

---

### Task 1: Test overlay art

**Files:** `tests/test_tft_activity.py`

- [ ] Add a test that prepares hold and ready overlays, checks cyan face pixels in the left artwork region, and ensures all artwork pixels stay clear of the title and detail text.
- [ ] Run `.venv/bin/python -m unittest discover -s tests -p test_tft_activity.py` and confirm the new test fails because the computer is absent.

### Task 2: Render the compact computer

**Files:** `dashboard.py`, `app_version.py`, `README.md`

- [ ] Draw the body, screen, face, slot, and feet with native filled rectangles using existing palette indices. Keep all rectangles within x=33..118 and y=37..105.
- [ ] Call the drawing method only for maintenance overlays, before drawing text and border.
- [ ] Advance `APP_VERSION` to `1.1.6` and document the new countdown art.
- [ ] Run the focused test and `make check`; both must pass.

### Task 3: Review and deliver

**Files:** all changed files

- [ ] Review the diff for layout, version, and memory impact; ensure no changes to sleep or running maintenance display.
- [ ] Commit and open a PR to `feature/reverse-tft`.
- [ ] If the current Reverse TFT is present in USB maintenance, deploy with `make deploy BOARD=adafruit_feather_esp32s3_reverse_tft`, verify all files and serial startup, and request a visual check.
