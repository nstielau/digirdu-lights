# DidgeLights revision 11 — four-button assembly carriers

Two new optional prints hold all four plungers in their correct positions on a removable rectangular frame around the TFT. Each print includes three main plungers plus the existing short flush reset. The frame is 0.2 mm thick, the rails are 1.2 mm wide, and four sacrificial links are 0.6 mm wide. A small lift tab helps remove the frame.

The covers, zebra pattern and individual button geometry are unchanged from revision 10.

## Choose one button arrangement

| File | Print quantity | Contents |
| --- | --- | --- |
| button-carrier-domed.stl | 1 | Three domed main buttons and one flush reset, joined by a removable frame |
| button-carrier-flat.stl | 1 | Three flat main buttons and one flush reset, joined by a removable frame |
| button-plunger-domed.stl | 3 | Separate domed main buttons, as before |
| button-plunger-flat.stl | 3 | Separate flat main buttons, as before |
| reset-plunger-flush.stl | 1 | Separate flush reset, for use with either separate main-button choice |

Use one carrier OR three separate main buttons plus one separate reset. A carrier already contains its reset button. Do not print extra plungers for the same assembly.

## Printing and installation

The carrier STLs are already oriented with the flat brims and frame on the bed and the button caps pointing up. Use a **0.2 mm first layer** so the entire carrier frame is one layer thick. Inspect the first-layer preview for all four connecting links. The frame and buttons should print as one connected piece. Peel it off carefully; this is a sacrificial assembly aid, not a durable handle.

1. Support the front cover face down with room beneath the holes for the raised main button caps. Leave the PCB out.
2. Insert all four stems together. The three main buttons go on one side of the TFT; the short reset goes on the opposite side. The carrier rests against the inside of the cover, holding the buttons approximately 0.2 mm above their final seats. Do not force them down while still connected.
3. Support the buttons in their holes and snip the four narrow links flush to the outer edges of the retaining brims. Avoid nicking the brim or stem.
4. Lift out the entire rectangular frame using its pull tab. Remove any loose offcuts and trim protruding link stubs flush. Fully seat each button in its pocket.
5. Install the board and finish the enclosure. Check that each button moves independently and the reset remains flush when unpressed.

**Remove the carrier before installing the board.** It intentionally occupies space needed for the buttons to settle into their final positions. It must not remain inside the assembled case or be left to break during use.

This is a first physical trial of the carrier. CAD checks pass, but survival during bed removal and breakaway behavior still need to be confirmed with your filament and print settings.

## Enclosure and Fusion files

- `DidgeLights-enclosure-v11.f3d`: complete current native assembly. The new `Button carrier - flat` and `Button carrier - domed` components are hidden by default so they do not overlap the regular assembly. Show either component and hide the covers/reference parts to inspect it.
- `front-patterned.3mf` and `rear-patterned.3mf`: unchanged multipart geometry for the pink/purple covers.
- `front-purple.stl` + `front-pink.stl`, and `rear-purple.stl` + `rear-pink.stl`: aligned color regions. Import each cover's pair as parts of one object; preserve their shared placement.
- `plain-front-housing.stl` and `plain-rear-cover.stl`: complete single-color cover alternatives.
- `previous-bambu-project/DidgeLights-v10-H2D.3mf`: unchanged reference copy from the revision 10 bundle. It still contains separate domed buttons, **not** a carrier. Replace those four loose plungers if you choose the carrier. Bambu Studio and printing remain user-controlled.

The carrier sketches are dimensioned and fully constrained. Frame thickness, rail width and link width are exposed as Fusion parameters. The carrier's plungers are exact solid copies of the existing variants; regenerate those copies if the source button geometry changes.

The pink/purple cover pattern remains a flush 0.8 mm exterior partition. Its original parametric plain covers and hidden ribbon tools are retained. Patterned covers are partition snapshots: regenerate them after changing the source covers, rather than exporting an old patterned snapshot.

## Checks

Each carrier is one connected solid, including its first-layer midsection. At 0.21 mm temporary stand-off it has no positive-volume interference with the front cover. Removing the added carrier material recovers the exact original four plungers. Active Fusion features are healthy. Exported carrier meshes are closed, consistently wound and nondegenerate, and native/archive integrity checks pass.

All previous standalone button meshes and patterned/plain cover files are byte-identical to the revision 10 bundle. Their earlier fit checks are carried in `baseline-verification/`. `verification.json` records this revision's checks; `bundle-manifest.json` contains file hashes.
