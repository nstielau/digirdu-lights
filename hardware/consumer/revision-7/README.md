# Echo Glow consumer — revision 7

Direct access to the Reverse TFT Feather's USB-C socket, a shorter case, and
wider snap latches with closed exterior walls. This release edits the existing
**Echo Glow consumer v6** Fusion document in **Echo Glow** and saves a new cloud
**version 4**. The document name deliberately stays the same; revision numbers on
disk identify print bundles.

## Changes

- The wired panel USB socket and its empty end bay are removed. Case length
  decreases **15 mm**, from 146.8 to **131.8 mm**. Width and depth stay
  **36.46 ×23.8 mm**. Boards, buttons, battery, magnets and taller v6 supports
  keep their positions and clearances.
- A **local stepped seam** crosses the USB-C socket's center, with a lower front
  notch and a matching rear tab. The rest of the perimeter seam stays in place.
  This lets the Feather lower vertically onto its locating pegs while its USB
  connector enters the open notch.
- The socket has a **9.54 ×4.8 mm** relief opening (0.3 mm around its modeled
  body) inside a **16.94 ×12.2 mm**, 1.2 mm deep cable-body recess. The outer
  recess provides **4 mm around each side** of the modeled USB body. Its back
  wall is 0.8 mm thick; the socket projects approximately 0.11 mm beyond that
  wall, while remaining approximately 1.09 mm behind the outer case end plane.
- Both latches are **13.5 mm wide**, up from 3 mm, with their existing 1.3 mm
  beams and wall-backed roots. Inside receiver pockets leave **1 mm of the
  2 mm exterior wall intact**. There are no exterior release holes. Their ramps
  support prototype pull-apart release; verify actual release force with the
  regenerated snap coupons.
- Both **M2×16 mm** case screws remain. The board-end screw moves into the new
  end corner. Its engagement, recess and head clearance are unchanged.

## Print choices

| File | Quantity / use |
| --- | --- |
| plain-front-housing.stl | 1; TFT face, stepped USB notch and blind snap pockets |
| plain-rear-cover.stl | 1; LED face, matching USB tab and wider snaps |
| diffuser.stl | 1 optional, translucent |
| snap-coupon-receiver.stl and snap-coupon-spring.stl | 1 each; test the new snaps first |
| button-rail-flat.stl **or** button-rail-domed.stl | 1 temporary carrier for three main buttons |
| button-plunger-flat.stl **or** button-plunger-domed.stl | Alternatively 3 individual main buttons |
| reset-plunger-flush.stl | Legacy only; not installed in the consumer |
| button-carrier-flat.stl, button-carrier-domed.stl | Legacy four-button alternatives; remove reset for consumer use |

All seven button variants are carried forward unchanged. Choose one main-button
arrangement. Cut temporary links flush to the brims and remove the entire rail
or surrounding frame before installing the PCB. Never operate linked buttons.

STLs are in millimeters, with exterior faces or button brims on the bed. The
USB end now has a deeper rear tab, and the blind snap pockets have small roofs;
inspect these in the slicer. No Bambu Studio project is supplied or changed.

## Assembly

1. Print and test the snap coupons in the intended material. Wider snaps can
   require more force; actual retention and repeated-release behavior remain
   unqualified.
2. Install one magnet into each shell's existing seam-loading slot, both on the
   same narrow side when closed.
3. Install three plungers and remove their temporary connectors. Lower the
   Reverse TFT Feather straight onto its taller v6 supports and pegs, with its
   onboard USB-C in the front end notch. Fit the Wing using the existing headers.
4. Secure the battery with two zip ties. Place the heads opposite the magnets,
   aligned with the v6 reliefs. Route leads clear of the seam, snaps and cradles.
5. Lower the rear half so its end tab closes around USB-C and the latches engage.
   Check that all three buttons release freely and that the USB plug seats fully.
6. Use the two M2×16 socket-cap screws for final closure. For prototype opening,
   remove the screws and ease the seam apart; the old exterior push-release holes
   are gone. Do not substitute the producer's 20 mm screws.

Reset remains a **2 mm pinhole**; no reset plunger is installed. Battery saddles,
magnet slots, opposing supports and button seats retain revision 6 geometry.

The complete native archive is `Echo-Glow-consumer-revision-7.f3d`. See
`DESIGN.md`, `PARTS.md`, previews, `verification.json` and `bundle-manifest.json`.
CAD checks do not establish physical cable fit, print behavior or snap durability.
