# Echo Glow consumer — revision 8

This release retains revision 7's 131.8 × 36.46 × 23.8 mm case, directly exposed
board USB-C, stepped end seam, 13.5 mm blind-pocket snaps, opposing battery
cradles, magnet slots, diffuser, and **2 mm reset pinhole**. The button choices
are simplified to a single **domed three-button breakaway rail**. Remove its
temporary links before fitting the Feather so each button moves independently.
No flat buttons, separate plungers, reset plunger, or four-button carriers are
included.

| Print file | Quantity |
| --- | ---: |
| `plain-front-housing.stl`, `plain-rear-cover.stl` | 1 each |
| `button-rail-domed.stl` | 1, yielding three buttons |
| `diffuser.stl` | 1 optional, translucent |
| `snap-coupon-receiver.stl`, `snap-coupon-spring.stl` | 1 each to test fit |

All six meshes are byte-for-byte carried from revision 7 because case geometry
and the domed rail did not change.

## Assembly

1. Print the snap coupons in the intended material and check engagement and
   release before committing to the shells.
2. Install one 60 × 10 × 2.75 mm magnet in each half's seam-loading slot, both
   on the same narrow side. Cut the button rail links and seat its three buttons
   separately in the front shell.
3. Lower the Reverse TFT Feather vertically onto the front supports and pegs,
   with its USB-C in the open front notch. Fit the Wing on removable headers.
   Secure the Ø19 × 69 mm battery with two zip ties; put their heads on the
   side opposite the magnets and route wires clear of the seam.
4. Fit the optional diffuser, close the rear tab around USB-C, engage the snaps,
   and use two M2 × 16 mm case screws. Check USB cable insertion, independent
   button travel, and reset access through the pinhole. The reset has no printed
   part. See [parts and fasteners](PARTS.md).

The complete source `Echo-Glow-consumer-revision-8.f3d` is from **Echo Glow
consumer v6**, cloud version 5. Retired button components were removed from
that current Fusion document; revision 7 and earlier archives preserve them.
CAD and mesh checks are in `verification.json`. Physical snap force, USB cable
fit, and button travel still need a printed trial.
