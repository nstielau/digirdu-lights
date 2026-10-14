# Echo Glow producer edge softening implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Soften hand-contact edges on the unreleased compact producer revision 4 and save a verified Fusion cloud version and print kit.

**Architecture:** Edit the existing parametric front and rear shell components in Echo Glow producer v1. Add selective finishing features after the current solid features, preserving the mating and internal fit geometry. Export updated native and mesh assets into the existing revision 4 kit and update the tracked verification and manifest records.

**Tech Stack:** Autodesk Fusion API, Fusion cloud versions, F3D/STL export, `hardware/tools/release_bundle.py`, repository `make check`.

---

### Task 1: Baseline and edge selection

**Files:**
- Read: `hardware/producer/echo-glow/revision-4/verification.json`
- Read: `docs/superpowers/specs/2026-10-13-echo-glow-producer-no-wing-design.md`

- [ ] Confirm the active Fusion document lineage, cloud version, feature health, component volumes and bounds against the revision 4 verification record.
- [ ] Enumerate exterior edge candidates on the front and rear shells by geometry. Identify hand-contact perimeter and opening lips, excluding seam, registration, fastener and internal fit edges.
- [ ] Preserve a complete pre-edit F3D backup outside the numbered release directory.

### Task 2: Parametric edge features

**Files:**
- Edit in Fusion: `Echo Glow producer v1` front and rear shell components

- [ ] Apply a 0.8 mm target fillet to selected exterior perimeter edges. If an edge fails or risks wall/feature interference, use a smaller local radius and record it.
- [ ] Apply a 0.3 mm target 45-degree chamfer to selected exposed screen, button and USB opening lips, with local reductions recorded where needed.
- [ ] Recompute the timeline and confirm no feature warnings/errors, one solid per shell, unchanged internal fit surfaces and no new positive-volume interference with the Feather or Ø19 × 69 mm battery.

### Task 3: Save and export

**Files:**
- Replace local ignored files: `hardware/producer/echo-glow/revision-4/Echo-Glow-producer-r4.f3d` and affected `*.stl`
- Update: `hardware/producer/echo-glow/revision-4/README.md`
- Update: `hardware/producer/echo-glow/revision-4/verification.json`
- Update: `hardware/producer/echo-glow/revision-4/bundle-manifest.json`
- Update: `hardware/producer/echo-glow/README.md`, `hardware/RELEASES.md` if cloud pointer changes

- [ ] Save the Fusion document and verify `latestVersionNumber` increments above 4 with the new edge features present. If Fusion remains offline, preserve the local F3D but do not claim a cloud save.
- [ ] Export the complete F3D and refreshed affected STL meshes in millimeters with print faces on Z = 0; leave unaffected rail byte-identical to its baseline.
- [ ] Verify F3D entries, mesh connectivity/closure/winding, dimensions and fit checks. Record actual feature sizes and any exceptions.
- [ ] Regenerate and verify the SHA-256 manifest and deterministic revision 4 ZIP.

### Task 4: Repository integration

**Files:**
- Commit tracked Markdown and JSON records; keep F3D/STL/ZIP assets ignored and local until hardware release.

- [ ] Run `make check` and `git diff --check`; inspect output and record any limitations.
- [ ] Commit the spec, plan, documentation and verification records on `codex/producer-edge-softening`.
- [ ] Push a PR to `main` with squash auto-merge enabled and verify the required `check` status. Publish the hardware release only after the Fusion cloud save and merged records are confirmed.
