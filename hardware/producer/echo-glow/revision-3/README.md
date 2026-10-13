# Echo Glow producer — revision 3

This revision keeps revision 2's direct board USB-C opening, stepped end seam,
closed battery end, diffuser, and two M2 × 20 mm case screws. It replaces the
fourth printed button with a **2 mm reset pinhole** centered at assembly
X 44.45, Y 11.43 mm. The three main buttons use the **domed breakaway rail**.
Remove the rail and its links before installing the PCB; the buttons must move
independently. There is no printed reset plunger, flat button, or four-button
carrier in this kit.

| Print file | Quantity |
| --- | ---: |
| `plain-front-housing.stl` | 1 |
| `plain-rear-cover.stl` | 1 |
| `button-rail-domed.stl` | 1, yielding three buttons |
| `diffuser.stl` | 1 optional, translucent |

Place each STL as exported; its bottom is at Z = 0 mm. The front is an updated
Fusion export. The rear, diffuser, and rail are byte-for-byte copies of the
verified revision 2 or consumer revision 7 prints where their geometry did not
change. The rail solid is also present in the editable Fusion archive.

The old striped front color regions still have the larger reset opening, so
they are deliberately **not print files for revision 3**. The revision 2
striped design remains in its historical bundle. The current Fusion assembly
shows the updated plain front with the existing striped rear reference.

## Assembly

1. Print the front, rear, and rail. Cut the rail's temporary links and seat the
   three buttons separately in the front shell.
2. Lower the Reverse TFT Feather straight onto its supports and locating pegs;
   its onboard USB-C must pass into the open front notch. Fit the 4×8 NeoPixel
   Wing and the Ø19 × 69 mm cylindrical battery. Keep wires clear of the seam,
   USB opening, screws, and battery saddles.
3. Place the optional diffuser behind the LED window. Close the rear half so
   its local tab surrounds the top of the USB connector. Secure with two M2 ×
   20 mm socket-cap screws.
4. Press reset through the pinhole with a narrow nonconductive tool. Check the
   actual USB plug, free button travel, reset access, battery clearance, and
   closure before relying on this print.

Fusion source: `Echo-Glow-producer-r3.f3d`, exported from the existing
**Echo Glow producer v1** lineage, cloud version 4. See `verification.json`
for CAD and mesh checks. Physical print fit and reset operation remain untested.
