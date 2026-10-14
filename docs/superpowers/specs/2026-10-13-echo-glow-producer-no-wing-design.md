# Compact Echo Glow producer without a pixel wing

## Status

The compact approach was approved on October 13, 2026 and implemented locally
as producer revision 4. Fusion reported an offline outage during the save, so
cloud version 4 remains the last confirmed version. The release F3D is the
verified editable snapshot pending cloud sync.

## Source and scope

Continue the existing **Echo Glow producer v1** Fusion document, currently cloud
version 4. Preserve that version and save the next edit as a new Fusion version.
The local producer revision 3 remains the historical print baseline; the new
geometry becomes producer revision 4.

The producer retains the Adafruit ESP32-S3 Reverse TFT Feather and its visible
TFT, the battery defined below, direct onboard USB-C access,
the domed three-button rail, the 2 mm reset pinhole, two M2 case screws, and
the established battery supports and board mounts. It has **no NeoPixel
FeatherWing**.

## Battery definition

Design around the intended, user-measured cylindrical cell envelope:
**19 mm diameter × 69 mm overall length**, with its long axis along the case's
X direction. In the existing producer model the battery begins approximately
at X = 1 mm, just beyond the rear-half stop at X = 0.8 mm. Preserve the two
battery saddles and a route for the cell leads. The enclosure must clear the
full Ø19 × 69 mm modeled cylinder; remove the approximately 6.82 mm³ rear-lip
intrusion recorded for revision 2 rather than carrying it into this revision.
The dimensions describe this particular measured cell and do not establish a
universal 18650 fit, chemistry, capacity, or lead/terminal tolerance. Confirm
the wrapped physical cell and lead exit in the first print.

## Enclosure geometry

Remove the wing from the active assembly. Replace the rear LED cover with a
continuous opaque shell: no LED window, diffuser seat, diffuser, or unused
interior allowance for the wing and its headers. Keep the exterior closed and
the two case halves printable as connected solids.

Lower the rear shell where the wing stack currently determines its height.
Measure the bare Feather, TFT, battery, USB connector, leads, fasteners, and
assembly path in the saved model before choosing the new roof position. Keep
the existing wall and fit clearances unless a measured constraint requires a
larger one. The resulting maximum enclosure height must be below revision 3's
35.4 mm; record the final dimension and the controlling clearance. The 69 mm
battery limits length reduction, so preserve the current length unless the
measured mounts and battery stop permit a safe reduction.

Retain the existing front housing geometry where it serves the TFT, buttons,
reset, board mounts, and USB seam. Preserve parametric source components and
the design timeline. Historical striped snapshots must not be exported as
current parts after the rear shape changes; regenerate them if they are offered
in this revision. Plain front and rear covers are sufficient for revision 4.

## Deliverables and verification

Save the new Fusion version and export a complete local F3D archive, plain
front and rear print meshes, and the existing domed three-button rail. Do not
include the old diffuser in the new assembly or print kit. Keep revision 3
assets intact. Document the new dimensions, assembly steps, and release-file
hashes under `hardware/producer/echo-glow/revision-4/`. Keep binary assets out
of Git; package them for an explicit hardware release tag using
`hardware/RELEASES.md`.

Before release, verify healthy Fusion features, single connected solids for
each shell and button rail, no positive-volume interference with the modeled
bare electronics or battery, usable USB and button/reset access, and closed,
consistently wound print meshes. Record the height reduction and demonstrate
that no wing opening or wing-only cavity remains. Run the repository checks.
Real USB-plug fit, battery tolerance, button travel, thermal behavior, and
print strength remain physical prototype checks, not CAD results.

## Exterior edge refinement (approved October 13, 2026)

Refine the still-unreleased revision 4 in the same Fusion document. Soften the
hand-contact exterior perimeter of both plain shells with modest fillets,
targeting a 0.8 mm radius where the existing wall and adjacent features allow
it. Add small 0.3 mm, 45-degree chamfers to exposed opening lips that a finger
can touch, including the screen and button openings and accessible USB edge.
Use a smaller local size if a specific edge fails or would intersect a nearby
feature, and record the actual sizes and selected edge groups.

Leave the shell mating seam, registration lips, screw seats and passages,
internal board and battery supports, button running surfaces, reset pinhole,
and USB connector clearance geometry unchanged. The fillets and chamfers must
not create new openings, split a shell, or reduce the documented 0.5 mm radial
battery-to-roof gap. Keep the overall case envelope and the model's existing
component clearances within the measured revision 4 dimensions.

Save this as a new cloud version of **Echo Glow producer v1** and export a fresh
editable F3D and affected STL meshes for the revision 4 kit. Update the
manifest, verification record, and assembly notes. Fusion cloud version 4 is
the last previously confirmed version; verify that the new version increments
and that the saved version contains the edge features before claiming cloud
save success. Recheck feature health, closed connected meshes, positive-volume
interferences, opening access, and baseline dimensions. Physical edge feel and
fit remain first-print checks.
