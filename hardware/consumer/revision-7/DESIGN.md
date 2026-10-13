# Consumer revision 7 design

Continue editing the existing **Echo Glow consumer v6** document in **Echo Glow**;
save a new Fusion version, not a new document. Preserve revision 6 on disk and
checkpoint the saved native model before edits.

The board's own USB-C replaces the wired panel socket. Remove the 15 mm end bay
by moving the shell's board end from X=-3.8 to X=11.2 while retaining the battery
end at X=143. The resulting shell is 131.8 × 36.46 × 23.8 mm. Keep the board,
battery, magnets, supports and buttons in their existing positions. Move only
the board-end case screw to X=14.6, Y=26.16; preserve the two M2×16 screws.

Split only the middle 20.86 mm of the end wall at actual USB mouth center Z=3.865. Front wall
ends at Z=3.765 and rear mating tab begins at Z=3.965. Side clearance of the tab is
0.2 mm per side. The main perimeter seam stays at Z=8.2. A 9.54 ×4.8 mm socket
opening gives 0.3 mm clearance around the imported 8.94 ×4.2 mm USB body.

Provide a shallow 16.94 ×12.2 mm cable-body recess: 4 mm around each side of the
USB body, interpreted as open plug space. Recess depth 1.2 mm leaves 0.8 mm wall
at its back. The socket's front at X=12.287 projects 0.113 mm beyond the recess
back at X=12.4. It is still recessed 1.087 mm from the case's outer end plane.
The cable housing can enter that recess without contacting the case.

Widen each existing 3 mm latch to 13.5 mm, located X=60..73.5 between alignment
keys and magnet frames. Retain 1.3 mm beam thickness, wall-backed roots and
0.25 mm nominal detent engagement. Replace exterior release windows with blind
inside pockets 1 mm deep, leaving 1 mm exterior skin. Symmetric detent ramps
allow prototype pull-apart release; no exterior tool holes remain.

Regenerate both snap coupons from the edited shells, preserving print direction.
Include both covers, optional diffuser, all seven unchanged button variants,
complete native archive, previews, parts list and verification in the release.
Verify solid connectivity, healthy features, dimensional changes, PCB/USB
vertical insertion, plug approach, screw clearance, snaps, magnets and meshes.
Physical snap force and cable fit still require a print trial.

The imported connector body includes lower mounting anchors. Its full body center
is Z=3.37, but the actual mouth front face spans Z=2.26..5.47. The local split
uses that face center, Z=3.865. Body clearance retains the larger full envelope.
