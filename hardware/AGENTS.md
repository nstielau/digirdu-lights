# Hardware workflow

## Current baseline

- `producer/revision-11/` is the imported DidgeLights enclosure revision 11.
- `producer/echo-glow/revision-3/` is the current Echo Glow producer prototype;
  its historical revision 2 is in the same producer tree.
- `consumer/revision-8/` is the current Echo Glow consumer prototype.
- `producer/revision-11/DidgeLights-enclosure-v11.f3d` is the editable native source,
  including board references, original parametric covers, patterned cover solids,
  individual plungers, and optional flat/domed carrier components.
- The user reported saving the model in Fusion on 2026-09-24. Its working document
  was `DidgeLights enclosure v3`; inspect the current document before editing.
- This enclosure targets Adafruit's ESP32-S3 Reverse TFT Feather, product 5691.
  Do not substitute generic Feather hole spacing or the FeatherS2 firmware board.
- CAD and mesh checks passed. Carrier bed removal and breakaway behavior have not
  been independently verified by a physical print.

Keep producer designs under `hardware/producer/` and consumer designs under
`hardware/consumer/`. Keep historical revisions intact; export changes to a new
numbered revision. Save both the current Fusion document and a complete local F3D archive.
The native model is the source of truth; one-off scripts from the original design
session are not a supported rebuild pipeline. Never replay old mutation scripts
blindly against a newer document.

## Current controls

Echo Glow producer revision 3 and consumer revision 8 use one domed
three-button breakaway rail and a 2 mm reset pinhole. Cut and remove the rail
links before installing the PCB; the three buttons must travel independently.
Do not carry flat buttons, separate plungers, flush reset plungers, or
four-button carriers into new Echo Glow bundles. Historical releases retain
those files as records. The DidgeLights revision 11 bundle is historical and
has not yet been converted to this control layout.

## CAD and print checks

Pink/purple cover partitions are geometry snapshots. Regenerate them after
editing source covers; do not export stale snapshots. Producer revision 3 has
plain covers only because its previous striped front retained the old reset hole.
Preserve the original parametric covers and ribbon tools.

Use millimeters for print exports; Fusion API native lengths are centimeters.
Keep color-region meshes registered as parts of one cover object. Verify feature
health, dimensions, fit/interference, solid connectivity, and exported mesh
closure/winding. Color regions may contain separate islands; complete covers and
button rails must remain connected. Separate CAD evidence from physical
print observations. Include file hashes and preserve baseline verification.

The user handles Bambu Studio and printing. Do not operate the app or modify its
projects unless asked. The bundled previous Bambu project is an unchanged
Revision 10 reference and does not contain the carriers.

## Repository hygiene

Track Markdown, source notes, bundle manifests, and verification JSON. Keep
F3D/STL/3MF/preview binaries and ZIP bundles ignored locally; attach complete,
hash-verified ZIPs to explicit hardware GitHub Release tags. Preserve old tags
and releases. See [release workflow](RELEASES.md) for verification and packaging.
Keep scratch exports, backups, machine-specific G-code, and logs ignored. Do not
bring credentials, recordings, board backups, or local MCP session identifiers
into hardware assets. Run the root-required `make check` before committing.
