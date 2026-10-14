# Echo Glow producer — revision 4

This compact producer fits the Adafruit ESP32-S3 Reverse TFT Feather and the
**user-measured Ø19 × 69 mm cylindrical battery**. The 4×8 NeoPixel wing and
its rear window, diffuser, supports, and interior height allowance are gone.
The rear is a solid opaque cover. Overall modeled height is **31.7 mm**, down
from revision 3's 35.4 mm. The modeled battery begins at X = 1 mm, runs along
X, and has 0.5 mm radial clearance below the 2 mm rear roof. The cell envelope
does not specify chemistry, capacity, wrapped-cell tolerance, or lead space.
The handled outer front and rear perimeter has a **0.8 mm fillet**. Selected
exposed screen, button and USB opening edges have **0.3 mm chamfers**. Mating and
internal fit edges retain their original shape.

The rear inset locating lip and battery-end tab now rise from the side wall on
angled underside ramps for printing with the outside face on the bed. The long
lip previously began as approximately 242 mm² of flat underside at print
Z = 11.1 mm; the revised mesh has approximately 11.8 mm² of narrow residual
strips there. The end tab's flat start at Z = 13.8 mm fell from 18.5 to
0.75 mm². The ramps add material above the mating seam while keeping the lip's
fit edge, battery clearance and USB opening. A slicer preview with supports
disabled and a physical print are still needed to confirm print behavior.

| Print file | Quantity |
| --- | ---: |
| `plain-front-housing.stl` | 1 |
| `plain-rear-cover.stl` | 1 |
| `button-rail-domed.stl` | 1, yielding three buttons |

Each STL is in millimeters with its print face at Z = 0. The rear mesh is
exported from the ramped parametric model; the front shell and domed button
rail remain byte-identical to the previous revision 4 kit. The old diffuser
and patterned rear snapshots are deliberately excluded.
`rear-lip-section-preview.png` compares actual before/after STL sections at
X = 40 mm; `solid-rear-preview.png` shows the unchanged exterior.

## Assembly

1. Print the three parts. Cut the temporary links from the button rail and
   seat its buttons separately in the front shell; each must move freely.
2. Lower the Reverse TFT Feather onto its supports and locating pegs. Align
   its onboard USB-C with the stepped end opening. Install the measured cell
   on the two saddles, leaving its leads clear of the seam and screw posts.
3. Close the solid rear cover over the Feather and battery. Its local end tab
   surrounds the USB connector; the rear stop remains beyond the battery end.
   Secure with two M2 × 20 mm socket-cap screws.
4. Use a narrow nonconductive tool through the 2 mm reset pinhole. Check the
   real USB plug, button travel, wrapped battery and leads, seam closure, and
   screw fit and the feel of the softened edges on the first print.

`Echo-Glow-producer-r4.f3d` is the complete editable Fusion snapshot from the
existing **Echo Glow producer v1** lineage, including the six support ramps.
Fusion's data panel and API confirmed cloud version **5** on October 14, 2026;
this F3D was re-exported from that version and archive-checked. See
`verification.json` for CAD and mesh measurements. Physical print and fit
qualification has not been performed.
