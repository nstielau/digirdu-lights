# Echo Glow consumer button rail and pinhole reset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create and release Echo Glow consumer revision 3 with flat and domed three-button center-rail carriers and a 1.5 mm reset pinhole while preserving revision 2 and all legacy button assets.

**Architecture:** Start from the saved Fusion consumer v2 document in a new v3 document so the v2 cloud design remains untouched. Modify only the front housing reset access and add two temporary three-button carrier components; export the unchanged rear/diffuser assets and carried-forward button files into a new verified revision bundle.

**Tech Stack:** Autodesk Fusion MCP API through `work/fusion_rpc.py`, Fusion `adsk` scripts, STL exports, Python standard-library mesh/hash/ZIP checks, Markdown documentation, and the repository's `make check` suite.

---

### Task 1: Establish the v3 working document

**Files:**
- Create: `work/consumer-v3/PLAN.md`
- Create: `work/consumer-v3/create.py`
- Create: `work/consumer-v3/create-result.json`
- Create: `work/consumer-v3/save-status.json`

- [ ] **Step 1: Record the source and release invariants**

  Write `PLAN.md` with the source cloud file name `Echo Glow consumer v2`, target file name `Echo Glow consumer v3`, target project `Echo Glow`, the two button center coordinates, rail width/thickness, pinhole diameter, and the rule that revision 2 is never mutated.

- [ ] **Step 2: Create a new Fusion document from v2 references**

  In `create.py`, use the Fusion API to create a new document and copy the v2 front/rear/diffuser/button reference components into it as independent occurrences. Preserve all source component names, parameters, and appearances. Do not modify the open v2 document.

- [ ] **Step 3: Save the new cloud document**

  Save as `Echo Glow consumer v3` in the `Echo Glow` project, then write `save-status.json` containing `is_saved`, `is_modified`, `source_is_modified`, cloud version, and the data-file name. Stop if the source document is modified or the save is incomplete.

- [ ] **Step 4: Verify the document baseline**

  Run `python3 work/fusion_rpc.py script work/consumer-v3/create.py` and inspect the JSON result. Expected: target document exists, source is unmodified, target is saved, and all v2 reference bodies are present.

### Task 2: Replace the reset interface with the pinhole

**Files:**
- Create: `work/consumer-v3/reset_pinhole.py`
- Create: `work/consumer-v3/reset-result.json`
- Modify: the v3 Fusion front-housing component only

- [ ] **Step 1: Add named reset parameters**

  Add or update `reset_pinhole_diameter = 1.5 mm`, `reset_center_x = 44.45 mm`, and `reset_center_y = 11.43 mm` in the v3 parameter table. Keep the producer/reference coordinates in PCB-local millimeters and convert to centimeters only at API boundaries.

- [ ] **Step 2: Remove the preferred reset plunger recess**

  Replace the existing v2 reset-plunger access geometry on the front housing with a straight cylindrical cut through the front wall centered at `(44.45, 11.43)`. The cut diameter is 1.5 mm, has no countersink or chamfer, and leaves the exterior face flush. Preserve the legacy reset-plunger component as a hidden reference only.

- [ ] **Step 3: Validate switch alignment and cover clearance**

  In `reset_pinhole.py`, measure the hole axis, diameter, front-face intersection, and distance to the Feather reset-switch reference. Assert the hole does not intersect the TFT aperture, button pockets, board body, or front support solids. Write `reset-result.json` with those measured values and feature-health results.

- [ ] **Step 4: Save the v3 design after the reset change**

  Run the mutation script once against v3, save, and assert the v2 document remains unmodified. Expected: a 1.5 mm nominal opening and no reset plunger in the preferred front assembly.

### Task 3: Build the temporary three-button rail carriers

**Files:**
- Create: `work/consumer-v3/build_button_rails.py`
- Create: `work/consumer-v3/button-rail-result.json`
- Create: `work/consumer-v3/button-rail-flat.stl`
- Create: `work/consumer-v3/button-rail-domed.stl`

- [ ] **Step 1: Define the rail geometry from existing buttons**

  Copy the v2 flat and domed main-button solids without changing their cap, stem, brim, or placement. Keep centers at `(7.62, 4.445)`, `(7.62, 11.430)`, and `(7.62, 18.415)` mm. Add one vertical rail at `x = 7.62 mm`, 0.4 mm wide in XY and 0.2 mm thick in Z, joining only adjacent button brims. Do not create a TFT-surrounding frame, pull tab, reset branch, or permanent support.

- [ ] **Step 2: Check carrier topology and fit**

  Measure each carrier as one connected solid with one lump, three button instances, two rail spans, and no positive-volume overlap with the front housing, Feather PCB, TFT aperture, or button pockets. Verify the rail lies in the first printed layer and that removing it leaves the original three button solids unchanged.

- [ ] **Step 3: Export the two rail meshes**

  Export the flat carrier to `button-rail-flat.stl` and the domed carrier to `button-rail-domed.stl`, oriented with the temporary rail on the bed. Record Fusion/native and STL dimensions, volume, component count, winding, and degenerate-triangle counts in `button-rail-result.json`.

- [ ] **Step 4: Save after carrier creation**

  Save the v3 Fusion document and assert that both carrier components exist and are hidden by default in the assembled view. The legacy five button components remain present and unchanged.

### Task 4: Export the complete v3 release assets

**Files:**
- Create: `work/consumer-v3/export.py`
- Create: `work/consumer-v3/verify.py`
- Create: `work/consumer-v3/package.py`
- Create: `outputs/consumer/revision-3/`

- [ ] **Step 1: Export the v3 native archive and previews**

  Export the saved v3 Fusion archive, revised plain front housing, unchanged plain rear cover, diffuser, both new rail carriers, and actual-assembly PNG previews. Set visibility through root occurrence child occurrences and assert the rail carriers and reset pinhole are visible in the inspection views where expected.

- [ ] **Step 2: Carry forward every button variant**

  Copy the existing flat plunger, domed plunger, flush-reset plunger, flat four-button carrier, and domed four-button carrier into the v3 output with their established filenames. Add the two new rail filenames. Mark the five carried-forward assets as legacy in the README and do not overwrite revision-2 files.

- [ ] **Step 3: Write v3 assembly and parts documentation**

  Create `outputs/consumer/revision-3/README.md` and `PARTS.md`. Document the preferred rail-carrier workflow (insert three, snip two rail spans, trim ends), 1.5 mm reset-hole use with a probe, legacy alternatives, unchanged header/battery/USB assumptions, deferred striping, and the fact that physical fit remains untested.

- [ ] **Step 4: Run the complete CAD and mesh verification**

  `verify.py` must assert no front/rear/diffuser/electronics/button interference, healthy Fusion features, correct pinhole dimensions, one connected solid for each rail carrier, closed/wound/nondegenerate STLs, and unchanged source/v2 state. Write `verification.json` with measured evidence and explicit physical-test limitations.

- [ ] **Step 5: Build and verify the manifest and ZIP**

  `package.py` hashes every release file except the manifest before writing it, creates `Echo-Glow-consumer-v3-print-kit.zip`, tests ZIP CRCs, and rechecks every manifest hash from inside the ZIP. Expected: every listed byte count and SHA-256 matches exactly.

### Task 5: Mirror the release in the hardware repository

**Files:**
- Create: `/Users/nickstielau/depot/github.com/nstielau/digirdu-lights/hardware/consumer/revision-3/`
- Modify: `/Users/nickstielau/depot/github.com/nstielau/digirdu-lights/hardware/consumer/README.md`
- Modify: `/Users/nickstielau/depot/github.com/nstielau/digirdu-lights/hardware/consumer/AGENTS.md`
- Modify: `/Users/nickstielau/depot/github.com/nstielau/digirdu-lights/README.md`
- Modify: `/Users/nickstielau/depot/github.com/nstielau/digirdu-lights/hardware/README.md`

- [ ] **Step 1: Copy verified release files byte-for-byte**

  Mirror every tracked v3 release file except the ZIP into `hardware/consumer/revision-3/`, then compare SHA-256 hashes and byte counts between output and repository copies. Keep the ZIP in the ignored `hardware/consumer/dist/` directory.

- [ ] **Step 2: Update repository guidance**

  Make revision 3 the current consumer release, describe the 0.4 mm rail and 1.5 mm pinhole, retain the revision-2 link, and preserve the rule that all button variants travel with every bundle. Do not alter firmware guidance.

- [ ] **Step 3: Run repository verification**

  Run `make -C /Users/nickstielau/depot/github.com/nstielau/digirdu-lights check` and `git -C /Users/nickstielau/depot/github.com/nstielau/digirdu-lights diff --check`. Expected: 111 or more tests pass with zero failures and no whitespace errors.

### Task 6: Final review and handoff

- [ ] **Step 1: Review the release checklist**

  Confirm the Fusion document is saved as `Echo Glow consumer v3`, v2 is unchanged, the ZIP opens with passing CRCs, the manifest hashes match, all seven button assets are present, and the README identifies the rail carriers as preferred.

- [ ] **Step 2: Report the deliverables and limitations**

  Link the v3 ZIP, README, and PARTS file from `outputs/consumer/revision-3/`. State that CAD/export verification passed and that rail breakaway, probe feel, switch alignment, header seating, and USB/battery fit still require a physical print.
