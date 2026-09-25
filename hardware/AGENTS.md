# Hardware workflow

## Current baseline

- `producer/revision-11/` is the complete imported DidgeLights enclosure release.
- `producer/revision-11/DidgeLights-enclosure-v11.f3d` is the editable native source,
  including board references, original parametric covers, patterned cover solids,
  individual plungers, and optional flat/domed carrier components.
- The user reported saving the model in Fusion on 2026-09-24. Its working document
  was `DidgeLights enclosure v3`; inspect the current document before editing.
- This enclosure targets Adafruit's ESP32-S3 Reverse TFT Feather, product 5691.
  Do not substitute generic Feather hole spacing or the FeatherS2 firmware board.
- CAD and mesh checks passed. Carrier bed removal and breakaway behavior have not
  been independently verified by a physical print.

Keep new parts in their own descriptive subdirectories under `hardware/`.
Keep released revisions intact; export future producer changes to a new numbered
revision. Save both the current Fusion document and a complete local F3D archive.
The native model is the source of truth; one-off scripts from the original design
session are not a supported rebuild pipeline. Never replay old mutation scripts
blindly against a newer document.

## All button variants in every enclosure bundle

- `button-plunger-flat.stl`: three separate flat main buttons.
- `button-plunger-domed.stl`: three separate domed main buttons.
- `reset-plunger-flush.stl`: one short reset with either separate main-button set.
- `button-carrier-flat.stl`: one flat set, already containing three main buttons
  and one flush reset.
- `button-carrier-domed.stl`: one domed set, already containing three main buttons
  and one flush reset.

Carry every existing variant forward and include new variants; do not retire any
without a user request. Also include both covers (plain and patterned options),
the complete native Fusion model, assembly instructions, previews, and verification.
Use clear quantities: one carrier replaces all four separate plungers.

The carrier is temporary: 0.2 mm thick frame, 1.2 mm rails, 0.6 mm links, and a pull
tab. Cut links flush to the brim, remove the entire frame, fully seat the buttons,
then install the PCB. Never treat it as a permanently linked button assembly.

## CAD and print checks

Pink/purple cover partitions and carrier button copies are geometry snapshots.
Regenerate them after editing the source covers or buttons. Do not export stale
snapshots. Preserve the original parametric covers and ribbon tools.

Use millimeters for print exports; Fusion API native lengths are centimeters.
Keep color-region meshes registered as parts of one cover object. Verify feature
health, dimensions, fit/interference, solid connectivity, and exported mesh
closure/winding. Color regions may contain separate islands; complete covers and
carrier assemblies must remain connected. Separate CAD evidence from physical
print observations. Include file hashes and preserve baseline verification.

The user handles Bambu Studio and printing. Do not operate the app or modify its
projects unless asked. The bundled previous Bambu project is an unchanged
Revision 10 reference and does not contain the carriers.

## Repository hygiene

Track intentional F3D, STL, 3MF, PNG, Markdown, and verification JSON release assets.
Keep scratch exports, backups, machine-specific G-code, logs, and ZIP bundles in
ignored locations. Rebuild ZIPs from tracked release files instead of committing
duplicate archives. Do not bring credentials, recordings, board backups, or local
MCP session identifiers into hardware assets. See `producer/WORKFLOW.md` for checks
and packaging commands. Run the root-required `make check` before committing.
