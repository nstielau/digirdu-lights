# Echo Glow producer support-free lip implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the unreleased revision 4 rear locating lip and end tab printable without designed supports while preserving the front/rear fit.

**Architecture:** Continue the active Echo Glow producer v1 Fusion document. Add parametric, 45-degree-or-steeper underside ramps to the rear shell before the existing floating inset lip and end tab begin in print orientation. Re-export the local revision 4 source and mesh, verify it, and update the release metadata.

**Tech Stack:** Autodesk Fusion API, Fusion F3D/STL export, Python trimesh, `hardware/tools/release_bundle.py`, `make check`.

---

### Task 1: Preserve and measure the baseline

**Files:**
- Read: `hardware/producer/echo-glow/revision-4/verification.json`
- Save ignored backup: `hardware/producer/echo-glow/backups/Echo-Glow-producer-r4-before-support-ramp.f3d`

- [ ] Verify the active Fusion document and rear/front feature health and volumes against the current verification record.
- [ ] Export a complete backup F3D and verify its archive integrity before changing geometry.
- [ ] Inspect the rear STL at print Z = 11.1 and 13.8 mm, record unsupported faces and relevant wall/lip coordinates, and compare the front mating profile.

### Task 2: Add support ramps in Fusion

**Files:**
- Edit in Fusion: `Echo Glow producer v1` → `Rear solid cover`

- [ ] Build additive 45-degree ramps from the existing rear wall to the inset lip underside along the long sides and end runs, trimming at corners, screw posts, and openings.
- [ ] Build a ramp or equivalent angled transition under the smaller end tab without narrowing the USB connector throat.
- [ ] Recompute the design; verify healthy feature states, one rear solid, unchanged exterior envelope, and zero positive-volume interference with the front shell, battery, and Feather reference geometry.

### Task 3: Export and verify print geometry

**Files:**
- Replace ignored: `hardware/producer/echo-glow/revision-4/Echo-Glow-producer-r4.f3d`
- Replace ignored: `hardware/producer/echo-glow/revision-4/plain-rear-cover.stl`
- Update ignored preview: `hardware/producer/echo-glow/revision-4/solid-rear-preview.png`
- Modify: `hardware/producer/echo-glow/revision-4/verification.json`
- Modify: `hardware/producer/echo-glow/revision-4/README.md`
- Modify: `hardware/producer/echo-glow/revision-4/bundle-manifest.json`

- [ ] Save the Fusion document. Verify a new cloud version if available; otherwise record the exact offline state and preserve the local F3D.
- [ ] Export the complete F3D and rear mesh, orient the outside face to print Z = 0, and leave unchanged front and button rail hashes intact.
- [ ] Verify F3D archive entries, rear mesh connectivity/watertightness/winding, envelope and volume, 45-degree growth under the lip and end tab, and fit/interference checks.
- [ ] Refresh the README, verification record, preview and SHA-256 manifest; run `release_bundle.py verify` and rebuild/verify the deterministic local ZIP.

### Task 4: Integrate the records

**Files:**
- Commit the spec, plan, revision README, verification JSON, and manifest; leave F3D/STL/ZIP ignored until a hardware release.

- [ ] Run `make check` and `git diff --check`, inspect the outputs, and review the changed records.
- [ ] Commit the tracked changes on `codex/producer-support-free-lip`, push a PR, enable squash auto-merge, and verify required checks and merge.
- [ ] Publish a hardware tag and ZIP only after Fusion cloud save is confirmed and the merged records match the verified local bundle.
