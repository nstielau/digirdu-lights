# Consumer revision 6 design

See [assembly notes](revision-6/README.md), [parts](revision-6/PARTS.md) and [verification](revision-6/verification.json).

Revision 6 replaces the inward-open magnet pockets with vertical seam-loading slots. Each opening is 60.2 ×2.95 mm, 10.2 mm deep, with a 0.2 mm lead-in chamfer. Both magnets remain on the same negative-Y narrow side. Four XY walls confine each magnet; front insertion is downward along −Z and rear insertion along +Z in assembly coordinates, both downward when printed exterior-face down. The previous local floor recesses and inward loading cuts are suppressed, restoring nominal floor thickness.

Two Ø19.6 mm front saddles oppose the rear saddles at X81.5 and118.5 mm (8 mm widths). Their 3.2 mm tie grooves are open. Tie heads move to positive-Y, away from the magnets; new front notches clear the modeled heads with 0.2 mm margin. Battery remains Ø19 ×69, X69.5..138.5, center Y11.43/Z8.55.

Wide TFT support height is 2.7 mm rather than 2.2. PCB seat moves from Z0.2 to0.7 mm. Both boards and the removable headers move +0.5 mm Z together; rear shoulder contact planes move to Z15.04, shortening those supports by 0.5 mm. The 11 mm facing-PCB header gap and button geometry remain unchanged.

Outside envelope stays 146.8 ×36.46 ×23.8 mm, seam Z8.2. USB remains at the board end. Reset Ø2, seven button variants, optional diffuser, snap geometry and two M2 ×16 screws are retained. Coupons are regenerated from the new shells. All geometry and mesh checks are distinct from physical fit/force qualification.

Inherited shell dimensions use v5_ parameters; v6_tft_support_raise drives v5_board_seat_z. New slot dimensions use v6_. Imported electronics and reference envelopes are snapshots; regenerate them and coupons after relevant changes. Prior revisions and producer remain unchanged.
