# Echo Glow consumer

## Revision 8 overrides and document workflow

Current release: `revision-8/`; local archive `revision-8/Echo-Glow-consumer-revision-8.f3d`.
The ongoing Fusion document remains **Echo Glow consumer v6**, in Echo Glow,
lineage `urn:adsk.wipprod:dm.lineage:kBcKv3PwQ5maxenDyZNRHw`, saved cloud version 5.
Reuse this document and save new versions for future changes. Do not create a
new document for each revision. Preserve numbered disk releases v1-v8.
Read revision-8/README.md and revision-7/DESIGN.md before editing.

- Keep the domed three-button breakaway rail and Ø2 reset pinhole. Flat rails,
  separate plungers, reset plungers, and four-button carriers were removed from
  the current document and revision 8 print kit. Revision 7 and earlier remain
  historical records. Case, snap, board, and battery meshes match revision 7.
- Keep F3D/STL/PNG assets ignored locally and publish complete, hashed ZIPs at
  explicit hardware tags according to `../RELEASES.md`.

## Revision 7 geometry baseline (historical)

- Direct onboard USB-C replaces the wired panel socket. Case X11.2..143:
  **131.8 x36.46 x23.8 mm**, 15 mm shorter. Boards and battery stay in place.
- Local end seam center Z3.865 matches the USB mouth face Z2.26..5.47; the
  modeled full body center Z3.37 includes lower anchors. Main seam stays Z8.2.
  Front step ends Z3.765; rear tab starts Z3.965. Step width20.86; tab side gap0.2.
- Socket relief9.54 x4.8; plug recess16.94 x12.2 x1.2, corresponding to4 mm
  surround around the full USB body. Remaining recess wall0.8. Socket front
  X12.287 projects0.113 past recess back X12.4, but is1.087 behind outer X11.2.
- Snaps13.5 mm wide at X60..73.5, beam1.3, wall-backed roots. Blind pockets1 mm
  deep leave1 mm exterior skin; no outside release windows. Preserve rounded
  case exterior and regenerate coupon snapshots after changing snaps.
- Board-end M2x16 screw moved to (14.6,26.16); far screw (139.5,-3.3). All v6
  board supports, magnet slots, battery cradles and tie clearances are preserved.
  Actual cable fit and snap release force are untested.
- Parameters use v7_ for new geometry; v5_case_x/length and snap dimensions are
  updated in place. Hidden V6 fit/coupon references preserve superseded snapshots.
  Current fit component: `Fit envelopes - zip ties and direct USB approach`.
- Revision 7 CAD health, connectivity, plug approach, vertical USB insertion,
  interference, snap skins, meshes, native archive and bundle hashes passed.
  Its root make check had 111 tests at the time.

## Revision 6 baseline (historical)

Current release: `revision-6/`; Fusion `Echo Glow consumer v6`, archive `revision-6/Echo-Glow-consumer-v6.f3d`. Preserve v1–v5. Read v6 README and DESIGN before editing; v5/v4 notes below are historical where superseded.

- Two magnets, one per half on SAME negative-Y side. Slots are open at the SEAM, closed inward; load vertically with each half flat for printing. Opening 60.2 ×2.95 mm, depth10.2 mm, 0.2 mm mouth chamfer. Previous inward loading floors/lanes are suppressed. Exterior stays23.8 mm deep.
- Two matching Ø19.6 mm battery saddles in EACH half. Front open tie grooves3.2 mm; tie heads and their new front notches on positive-Y, opposite magnets. Preserve strap/head clearance.
- Wide TFT shoulders raised0.5 mm to2.7 mm high, seatZ0.7. Header-connected board stack raised0.5 mm together; rear supports shortened0.5 mm. Nominal PCB-face gap remains11 mm. Printed button geometry and seating planes unchanged.
- New parameters v6_tft_support_raise and v6_magnet_*; inherited shell dimensions retain v5_ names. Snapshot board moves, references and coupons require regeneration after changes.
- Keep seven unchanged button variants, both covers, diffuser, regenerated snap coupons, native archive and verification. Physical snugness, button behavior and snap retention require testing.


## Revision 5 overrides

Current model: `Echo Glow consumer v5`; archive `revision-5/Echo-Glow-consumer-v5.f3d`. Read revision-5/README.md and DESIGN.md. The v4 notes below are historical where superseded.

- Exterior remains 146.8 × 36.46 × 23.8 mm. Seam Z8.2; nominal cavity 10.2 mm per half.
- Two magnets total: ONE full rectangular pocket in EACH half, SAME negative-Y narrow side. Openings 60.4 ×10.2 mm; depth 4.15 mm; inner-face loading. Local floor relief leaves 0.8 mm front and 1.4 mm rear. Do not revert to opposite-side magnets or partial end tabs. Physical anti-flip retention needs a print trial.
- Boards, openings, controls, diffuser, battery and ties shift +13.5 mm X. Battery X69.5..138.5, Y11.43, Z8.55. USB moves to board end. Preserve 11 mm header gap.
- Two M2 ×16 screws; centers (−0.4,26.16), (139.5,−3.3); engagement 6 mm, tip clearance 0.7 mm.
- Reset Ø2 at (57.95,11.43); no reset plunger. Rails 2.5 ×0.4 mm, brim-down, temporary and fully removed. Preserve all seven variants.
- Snaps 1.3 mm thick ×3 mm wide, wall-backed root Z10.2..18.4. Effective free length 5.35 mm; detent 0.25 mm. Regenerate coupons after snap changes.
- New shell parameters v5_; rail dimensions v5_rail_width/v5_rail_thickness. Hide V3/V4 reference and V5 intermediate components. CAD checks do not establish print fit.

## Historical v4 baseline

Read ../AGENTS.md as well. Latest release is revision-5/; preserve revisions 1 through 4.

- Current design: Echo Glow consumer v4 in Echo Glow project; local native
  archive revision-4/Echo-Glow-consumer-v4.f3d. Check cloud-save status before
  assuming the open document is the saved latest version.
- User changed the design to standard removable Feather headers. Both boards
  share XY: Reverse TFT faces front, 4×8 NeoPixel Wing faces rear. Battery is
  beyond the short edge, not in the board footprint and not an end-to-end PCB
  arrangement. Cell Ø19×69, x 56..125, y 11.43, z 8.55 (lowered 1.28 toward rear).
- Nominal socket height 8.5 + male spacer 2.5 =11 mm facing-PCB gap. This is an
  assumption to check against actual headers, not a universal Feather standard.
  PCB/Wing body envelopes are included; individual pins/solder are not.
- Envelope 146.8×36.46×23.8 mm; head/grip both 36.46 mm wide. Two M2×16 socket screws; no board
  screws. Ø1.8 blind pilots, Ø2.3 clearance, Ø4.4×2.2 head recesses. Do not reuse
  producer M2×20 without redesigning pilots. Board capture allowance 0.2 mm.
- Two rear saddles Ø19.6 with OPEN 3.2 mm-wide tie grooves to z=19.2,
  leaving 1.2 mm rear floor. Use 2.5×1.0 ties. Full 1.1 mm radial wrap and
  angled head envelopes checked; actual strap threading remains untested.
- End USB opening 14.2×5.4 through 2 mm wall. Assumed body 14×15.5×8 mm fits;
  real clips/cable unmeasured. No onboard USB-C plug clearance; panel socket
  uses existing wired arrangement. Handle end bay 16 mm clear before rear wall.
- User explicitly deferred striped versions. Include plain halves, optional
  diffuser, all FIVE carried-forward producer button variants, both v3
  three-button rail variants, native F3D, CAD previews, BOM, assembly
  instructions and verification/hashes in every revision bundle.
- V3 uses a straight 1.5 mm reset pinhole at x 44.45 mm, y 11.43 mm and hides
  the legacy reset-plunger occurrence. Do not install a printed reset plunger;
  use a pin only when a reset is required.
- V3 rail carriers are a 0.4 mm wide × 0.2 mm thick center rail connecting the
  three D0/D1/D2 plungers. They are temporary installation aids: cut both
  spans flush with the button brims and remove the entire rail before seating
  the PCB. The old four-button carriers remain legacy compatibility assets.
- The original FIVE producer button assets are unchanged. V4 rotates the two
  three-button rail meshes brim-down, correcting their v3 print orientation.
  Geometry is unchanged; the 0.2 mm rail starts at the bed.
- Both outer faces are flat. R4 grip blends meet 1.5 mm bed-edge chamfers;
  four magnet-stop braces slope at 45 degrees. Inspect port bridges in the
  slicer; CAD checks are not a physical support-free print qualification.
- Two 60×10×2.75 magnets sit on the NARROW handle sides, faces normal to Y,
  perpendicular to TFT/LED windows. Never move them onto broad front/rear faces.
  Pockets 60.4×10.4×3.15; open-seam loading, rear rails/stops and front captures;
  2 mm exterior side walls. Magnetic holding force is unmeasured.
- Two releasable snaps near USB end; retain screw closure. Beams 3×0.9, free
  length about 12.6, required deflection 0.5 mm. Include both exact-geometry
  snap coupon STLs. No printed fatigue/force qualification is claimed.
- Electronics grouped for hide/show. Header/battery/fit references are envelopes.
  Official Wing Eagle has FOUR drills: near platedØ2.5 and far unplatedØ2.54.
  v1 reference mistakenly omitted near plated holes; v2 corrects them. Preserve
  earlier release evidence rather than silently replacing historical files.
- Feather vendor copper placeholders are drilled only in the consumer copy;
  source producer unchanged. Use actual Reverse TFT asymmetric mount spacing:
  USB pair 17.78; far pair 19.113; length 45.72 mm.
- Covers have constrained sketches. Imported electronics/buttons and saddle/
  fit-envelopes are snapshots; regenerate affected solids after editing params.
- Installed button visibility must be set on root occurrence childOccurrences,
  not merely native component occurrences, then asserted isVisible. Verify
  actual previews; meshes alone do not prove assembled view correctness.
- CAD checks are not physical print qualification. Preserve all prior releases.

- V4 shell parameters are prefixed v4_. Old V3 reference components stay hidden.
  Battery/strap/magnet references, fixed snap ramps and coupon solids are
  snapshots: regenerate after related geometry changes. Recorded snap size
  parameters alone do not rebuild all fixed profile geometry.
