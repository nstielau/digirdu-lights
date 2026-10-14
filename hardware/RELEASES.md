# Hardware release workflow

Git tracks design notes, version references, verification, and SHA-256 manifests.
The large Fusion archives, print meshes, slicer projects, and previews are local
working files and **GitHub Release assets**, not Git blobs. GitHub associates
each Release with a Git tag. Names such as `hardware-echo-glow-producer-v3` are
our proposed convention for identifying numbered kits, not a GitHub requirement.
Download the ZIP attached to the Release for the complete printable kit and
editable F3D source. A tag without its matching asset is not a complete hardware
release.

Current local prototypes:

| Suggested Release tag | Local bundle | Fusion cloud document |
| --- | --- | --- |
| `hardware-didgelights-producer-v11` | `producer/revision-11/` | DidgeLights enclosure |
| `hardware-echo-glow-producer-v2` | `producer/echo-glow/revision-2/` | Echo Glow producer v1, version 3 |
| `hardware-echo-glow-producer-v3` | `producer/echo-glow/revision-3/` | Echo Glow producer v1, version 4 |
| `hardware-echo-glow-producer-v4` | `producer/echo-glow/revision-4/` | Echo Glow producer v1, compact case, softened edges and support ramps; cloud version 5 |
| `hardware-echo-glow-consumer-v7` | `consumer/revision-7/` | Echo Glow consumer v6, version 4 |
| `hardware-echo-glow-consumer-v8` | `consumer/revision-8/` | Echo Glow consumer v6, version 5 |

The cloud version is a convenience pointer. The F3D inside the release ZIP is
the portable editable snapshot. Revision 4's ramped model was confirmed as
**Echo Glow producer v1** cloud version 5 and its F3D was re-exported and
verified on October 14, 2026. Historical local numbered directories remain
intact, including their retired button options. New Echo Glow kits use only the
domed three-button rail and reset pinhole.

The [producer revision 4 release](https://github.com/nstielau/digirdu-lights/releases/tag/hardware-echo-glow-producer-v4)
is tagged at `caaabbdd1864f16f129bd26342cc3cd16043729d`. Its downloaded
`Echo-Glow-producer-r4-print-kit.zip` matched the local kit byte for byte;
SHA-256 is `ad55fe80446feddcdc2d94bd14b20ef273b90a635207eb917ee10b1daa039311`.

## Prepare a release

1. Save the existing Fusion document as a new cloud version. Export a complete
   F3D into a new numbered directory. Export meshes in millimeters with their
   print face on Z = 0. Include assembly notes, preview images, and a verification
   record. Check the model's feature health, dimensions, fits, and mesh closure.
   Record what was physically printed separately.
2. Put the intended files directly under that numbered directory. Generate and
   verify its manifest, then build the deterministic ZIP:

   ```sh
   python3 hardware/tools/release_bundle.py update-manifest hardware/consumer/revision-8
   python3 hardware/tools/release_bundle.py verify hardware/consumer/revision-8
   python3 hardware/tools/release_bundle.py package hardware/consumer/revision-8 \
     --output hardware/consumer/dist/Echo-Glow-consumer-r8-print-kit.zip
   ```

3. Run `make check`, review the notes and manifest, and commit those **text**
   files. Choose a tag for that commit and publish a GitHub Release with the
   verified ZIP attached. The example creates an annotated tag using our
   suggested naming convention:

   ```sh
   git tag -a hardware-echo-glow-consumer-v8 -m 'Echo Glow consumer revision 8'
   git push origin hardware-echo-glow-consumer-v8
   gh release create hardware-echo-glow-consumer-v8 \
     hardware/consumer/dist/Echo-Glow-consumer-r8-print-kit.zip \
     --title 'Echo Glow consumer revision 8' --notes-file hardware/consumer/revision-8/README.md
   ```

4. Download or inspect the published asset, verify its ZIP CRC and the manifest
   hashes, and record the release URL and ZIP SHA-256. Never rewrite a published
   tag or replace its asset; make a new revision for a correction.

The manifest hashes every file inside the directory except itself. The ZIP
packs the manifest too, with fixed timestamps and sorted paths. The packager
refuses missing, extra, or changed files. Keep local `work/`, `backups/`, `dist/`,
machine G-code, and credentials outside the release directory.
