# Echo Glow consumer button rail and pinhole reset

## Status

Approved design. This work becomes consumer mechanical revision 3 and starts
from the saved Echo Glow consumer v2 design. Revision 2 remains unchanged.

## Scope

The consumer enclosure keeps its standard removable Feather header stack,
opposite-facing TFT and NeoPixel displays, centered cylindrical battery handle,
plain covers, and optional diffuser. This revision changes only the front-side
button installation aids and reset access.

## Button configuration

The existing three-button positions are retained at x = 7.62 mm and y =
4.445, 11.430, and 18.415 mm for D0, D1, and D2. Two new printable carriers
are added:

- `button-rail-flat.stl` uses the existing flat main-button geometry.
- `button-rail-domed.stl` uses the existing domed main-button geometry.

Each carrier contains only the three main buttons. A single vertical rail follows
their centerline at x = 7.62 mm. The rail is 0.4 mm wide and 0.2 mm thick,
so it prints as a one-layer temporary connection between adjacent button
brims. There is no TFT-surrounding frame, pull tab, reset branch, or permanent
connection. After inserting the three buttons together, the two short rail
segments are cut and the ends are trimmed flush.

The revision bundle also carries forward the five existing producer button
assets: separate flat plungers, separate domed plungers, the flush reset
plunger, and the two legacy four-button carriers. Those remain available for
reproducing earlier assemblies and are labelled legacy; the new rail carriers
are the preferred consumer configuration.

## Reset access

The reset plunger is removed from the preferred consumer assembly. At the
existing Feather reset-switch center, x = 44.45 mm and y = 11.43 mm, the front
housing has a straight 1.5 mm through-hole. The surrounding outside face stays
flush, with no chamfer and no printed insert. A paperclip or approximately
1 mm probe can press the board's own reset switch through the opening.

The legacy `reset-plunger-flush.stl` remains in the bundle for compatibility
with earlier covers. It is not included in the new rail-carrier installation
sequence.

## Deliverables

Create and save `Echo Glow consumer v3` in the `Echo Glow` Fusion project,
leaving v2 unchanged. Export the revised front housing, unchanged rear cover
and diffuser, both rail carriers, all carried-forward button assets, the native
F3D archive, previews, assembly notes, parts list, and verification records.
Striped covers remain deferred.

## Verification

The checks must establish:

1. the pinhole is 1.5 mm nominal and aligned with the Feather reset switch;
2. both rail carriers contain three intended buttons, one connected solid, and
   no positive-volume interference with the front cover or board reference;
3. all exported STLs are closed, consistently wound, nondegenerate, and the
   rail is a connected one-layer-thick temporary bridge;
4. the Fusion archive is complete and saved, and the bundle manifest hashes
   every release file; and
5. the documentation clearly distinguishes the preferred rail/pinhole assembly
   from the carried-forward legacy button options.

Physical print fit, probe feel, breakaway behavior, header stack height, and
reset-switch alignment remain first-print checks and must not be represented as
CAD verification results.
