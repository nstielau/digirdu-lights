# Producer CAD workflow

## Continue editing

1. Read `../AGENTS.md` and the latest revision README. Open the current Fusion
   document or import the complete F3D archive. Confirm the document and components
   before making changes; the original document name was `DidgeLights enclosure v3`.
2. Work in a new revision. Preserve the last released files. Keep intermediate
   exports and safety copies in ignored `work/` or `backups/` directories.
3. Edit the parametric covers and named dimensions. Regenerate patterned-cover
   partitions after cover changes and carrier copies after button changes.
   The hidden carrier components are optional prints, not extra installed parts.
4. Check feature health and relevant fit, button travel, screw and peg clearance.
   For carriers, verify insertion before the PCB and independent buttons after
   frame removal. Physical feedback is distinct from CAD checks.
5. Export the complete F3D, both covers and color regions, every button variant,
   preview images and verification records. Orient print files on the bed in mm;
   keep each cover's color regions aligned. Update the assembly instructions.
6. Generate a manifest for the new revision, verify it, build an ignored print-kit
   ZIP, then run `make check` from the repository root and commit the release files.

The Fusion file contains the current native design; there is no supported script
that reconstructs every historical revision from scratch. Local one-off scripts
were deliberately not imported as a reusable build system.

If using a local Fusion MCP connection, discover its current tools and establish
a fresh session. The original endpoint was `http://127.0.0.1:27182/mcp`; it is a
local service, not a hosted project dependency. Use one Fusion request at a time
and inspect its returned success/error data, not merely the shell exit code.
Do not commit session IDs or assume the original endpoint is still running.

## Verify and package Revision 11

Run this from the repository root. It checks every imported file against the
original manifest before creating a bundle under ignored `hardware/producer/dist/`.
The archive contains the same files as the delivered kit; ZIP metadata/compression
may differ, so the ZIP file's own hash need not match the original.

```sh
python3 - <<'PY'
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

release = Path('hardware/producer/revision-11')
manifest = json.loads((release / 'bundle-manifest.json').read_text())
names = [entry['file'] for entry in manifest['files']]
assert len(names) == len(set(names)), 'Duplicate manifest entries'
for entry in manifest['files']:
    data = (release / entry['file']).read_bytes()
    assert len(data) == entry['bytes'], entry['file']
    assert hashlib.sha256(data).hexdigest() == entry['sha256'], entry['file']
names.append('bundle-manifest.json')
assert set(names) == {
    path.relative_to(release).as_posix()
    for path in release.rglob('*') if path.is_file()
}, 'Unlisted or missing release files'
dest = Path('hardware/producer/dist/DidgeLights-v11-print-kit.zip')
dest.parent.mkdir(parents=True, exist_ok=True)
with ZipFile(dest, 'w', ZIP_DEFLATED) as archive:
    for name in names:
        archive.write(release / name, 'DidgeLights-v11-print-kit/' + name)
with ZipFile(dest) as archive:
    assert archive.testzip() is None
    for name in names:
        assert archive.read('DidgeLights-v11-print-kit/' + name) == (release / name).read_bytes()
print(f'Verified and packaged {len(names)} files: {dest}')
PY
```

The manifest proves release-file identity. Geometric and mesh results are in
`revision-11/verification.json`; unchanged earlier checks are in its
`baseline-verification/` directory. Future geometry changes require new checks,
not just new hashes.
