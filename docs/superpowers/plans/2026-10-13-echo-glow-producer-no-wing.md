# Compact Echo Glow Producer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing Echo Glow producer enclosure compact and solid-backed for a bare Reverse TFT Feather and the measured Ø19 × 69 mm battery, with no NeoPixel wing or LED opening.

**Architecture:** Continue the `Echo Glow producer v1` Fusion lineage at cloud version 4. Suppress wing-specific rear-cover features, lower the named rear-roof parameter, and correct the known battery-lip intrusion without disturbing the TFT/front controls or direct USB seam. Export a complete revision 4 archive and print kit, verify CAD and meshes, then integrate text records through a CI-gated PR.

**Tech Stack:** Fusion 360 parametric design and Fusion API via the local MCP endpoint; Python 3, `trimesh`, `hardware/tools/release_bundle.py`, GitHub Releases.

---

## File map

- Source of truth: Fusion document `Echo Glow producer v1`, lineage `urn:adsk.wipprod:dm.lineage:rV-ATT5yQr6LfZkcf5K2oQ`.
- Create: `hardware/producer/echo-glow/revision-4/README.md` (assembly and limits), `verification.json` (measured CAD/mesh evidence), `bundle-manifest.json` (release hashes).
- Export only, ignored by Git: `revision-4/Echo-Glow-producer-r4.f3d`, `plain-front-housing.stl`, `plain-rear-cover.stl`, `button-rail-domed.stl`, preview PNG, and `hardware/producer/dist/Echo-Glow-producer-r4-print-kit.zip`.
- Modify: `hardware/producer/echo-glow/README.md`, `hardware/producer/README.md`, and `hardware/RELEASES.md` to point to revision 4. Preserve revision 3 files.

### Task 1: Preserve and measure the Fusion baseline

- [ ] **Step 1:** Use a fresh local Fusion MCP session; confirm active document `Echo Glow producer v1 v4`, unmodified state, and the lineage above. Read the existing `rear_outer_z = 32 mm`, `rear_thickness = 2 mm`, `battery_diameter = 19 mm`, `battery_length = 69 mm`, `battery_radial_gap = 0.5 mm`, and current shell bounds Z = −3.4..32.0 mm. Abort if another design is active.
- [ ] **Step 2:** Export a complete pre-edit F3D into ignored `hardware/producer/echo-glow/backups/` and verify it exists and can be opened as a ZIP archive. Do not alter the saved v4 cloud version.
- [ ] **Step 3:** Record the active rear features: `Open NeoPixel window`, `Recess removable diffuser`, both `Catch diffuser edge` features, four `Support wing PCB outside LED field` features, and two `Wing far-end locating pegs` features. Record bare Feather Z = −1.7..6.57 mm, battery Z = 6.8..25.8 mm, and wing Z = 26.3..29.0 mm.

### Task 2: Remove wing-dependent geometry and lower the rear roof

- [ ] **Step 1:** In one Fusion API edit, suppress the ten rear features named in Task 1 from latest to earliest. Keep their sketches and timeline history for reversibility. Hide the NeoPixel wing and optional diffuser occurrences in the active assembly.

```python
import adsk.core, adsk.fusion

def run(_context: str):
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    assert app.activeDocument.name.startswith('Echo Glow producer v1')
    root = design.rootComponent
    rear = next(o.component for o in root.occurrences if o.component.name == 'Rear LED cover')
    names = (
        'Wing far-end locating pegs 1', 'Wing far-end locating pegs 0',
        'Support wing PCB outside LED field 4', 'Support wing PCB outside LED field 3',
        'Support wing PCB outside LED field 2', 'Support wing PCB outside LED field 1',
        'Catch diffuser edge (1)', 'Catch diffuser edge',
        'Recess removable diffuser', 'Open NeoPixel window',
    )
    features = {rear.features.item(i).name: rear.features.item(i)
                for i in range(rear.features.count)}
    assert all(name in features for name in names)
    for name in names:
        features[name].isSuppressed = True
    for o in root.occurrences:
        if o.component.name == 'Optional translucent diffuser':
            o.isLightBulbOn = False
        if o.component.name == 'Electronics references - hide or show together':
            for child in o.component.occurrences:
                if child.component.name.startswith('NeoPixel FeatherWing'):
                    child.isLightBulbOn = False
    print('Suppressed wing geometry; hid wing and diffuser references')
```

- [ ] **Step 2:** Inspect returned `success` and feature health. Change `rear_outer_z` from `32 mm` to `28.3 mm` using the named user parameter. This equals battery top 25.8 + radial gap 0.5 + rear thickness 2.0 mm. Do not change `seam_z`, `wall`, battery placement, front housing, USB features, fasteners, or buttons.

```python
import adsk.core, adsk.fusion

def run(_context: str):
    design = adsk.fusion.Design.cast(adsk.core.Application.get().activeProduct)
    parameter = design.userParameters.itemByName('rear_outer_z')
    assert parameter and parameter.expression == '32 mm'
    parameter.expression = '28.3 mm'
    print('rear_outer_z =', parameter.expression)
```

- [ ] **Step 3:** Re-read the rear body. Expected roof Z = 28.3 mm, single solid, no through LED aperture, and total front-to-rear height about 31.7 mm versus 35.4 mm baseline. Check every unsuppressed timeline feature for health before proceeding; undo and repair a failing edit before adding geometry.

### Task 3: Clear the battery lip and verify the assembly

- [ ] **Step 1:** Compare the rear cover against the modeled Ø19 × 69 mm battery. Revision 2 recorded 6.82 mm³ intersection near battery X = 1.0..1.15 mm; verify the current overlap after roof edits. Keep the two battery saddles and rear-half stop at X = 0.8 mm.
- [ ] **Step 2:** If the overlap remains, add a narrowly bounded cut at the offending rear lip only: start at the battery X = 1.0 mm plane, use the measured battery cross-section centered Y = 11.43, Z = 16.3 mm, and limit the cut to the observed interference interval. Do not cut the long battery saddles or the stop. Repeat the interference check until the modeled cylinder has zero positive-volume overlap.
- [ ] **Step 3:** Verify the bare Feather, battery, USB connector, front/rear seam, M2 screws, three buttons, and reset pinhole still assemble without positive-volume interference. Inspect the saved graphics view from front, rear, USB end, and inside. The first print must still check real cell wrap/leads and plug/button feel.

### Task 4: Save, export, and verify revision 4

- [ ] **Step 1:** Save the existing Fusion document as its next cloud version; confirm the version increased from v4. Export the complete F3D and a preview PNG to `hardware/producer/echo-glow/revision-4/`. Do not export stale patterned-cover snapshots or the diffuser.
- [ ] **Step 2:** Export the front, revised rear, and existing domed three-button rail as mm STL files with print faces at Z = 0. Check each is one connected, closed, consistently wound solid; record triangle count, bounds, and volume. Verify the rear mesh has a closed roof and no LED opening.
- [ ] **Step 3:** Write `revision-4/README.md` with parts and assembly instructions, `verification.json` with measured bounds/feature health/interference/mesh evidence, and update the three producer release index documents. State that physical print fit remains unqualified.
- [ ] **Step 4:** Run:

```sh
python3 hardware/tools/release_bundle.py update-manifest hardware/producer/echo-glow/revision-4
python3 hardware/tools/release_bundle.py verify hardware/producer/echo-glow/revision-4
python3 hardware/tools/release_bundle.py package hardware/producer/echo-glow/revision-4 --output hardware/producer/dist/Echo-Glow-producer-r4-print-kit.zip
make check
git diff --check
```

Expected: manifest and ZIP verify every exported file; `make check` passes; no F3D/STL/ZIP is staged in Git.

### Task 5: Integrate and publish the prototype kit

- [ ] **Step 1:** Commit only text spec/plan, README, verification, and manifest changes on `codex/producer-no-wing`; push and open a PR to `main`. Enable squash auto-merge and wait for the required `check` job. If CI fails, fix and rerun it before integration.
- [ ] **Step 2:** Fetch merged `main`, create annotated tag `hardware-echo-glow-producer-v4` at the merged commit, push it, and publish the verified ZIP as a GitHub Release asset. Check the published ZIP CRC and each manifest hash. Record the URL/hash without rewriting the tag or historical files.
