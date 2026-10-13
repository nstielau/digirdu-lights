# Echo Glow producer — revision 4

This compact producer fits the Adafruit ESP32-S3 Reverse TFT Feather and the
**user-measured Ø19 × 69 mm cylindrical battery**. The 4×8 NeoPixel wing and
its rear window, diffuser, supports, and interior height allowance are gone.
The rear is a solid opaque cover. Overall modeled height is **31.7 mm**, down
from revision 3's 35.4 mm. The modeled battery begins at X = 1 mm, runs along
X, and has 0.5 mm radial clearance below the 2 mm rear roof. The cell envelope
does not specify chemistry, capacity, wrapped-cell tolerance, or lead space.

| Print file | Quantity |
| --- | ---: |
| `plain-front-housing.stl` | 1 |
| `plain-rear-cover.stl` | 1 |
| `button-rail-domed.stl` | 1, yielding three buttons |

Each STL is in millimeters with its print face at Z = 0. The front and domed
button rail are byte-identical to revision 3. The rear is newly exported from
the revised parametric cover. The old diffuser and patterned rear snapshots
are deliberately excluded.

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
   screw fit on the first print.

`Echo-Glow-producer-r4.f3d` is the complete editable Fusion snapshot from the
existing **Echo Glow producer v1** lineage. Fusion accepted a local save on
October 13, 2026, but reported an offline outage; cloud version 4 remains the
last confirmed version. The release F3D and STL files were exported and
verified locally. See `verification.json` for CAD and mesh measurements.
Physical print and fit qualification has not been performed.
